"""Remote API provider management with mandatory SSRF protection and protocol detection.

Security model:
- Every user-provided URL is treated as untrusted input.
- The SSRFGuard class is the mandatory first gate; no outbound request is made
  to a URL that has not passed the guard.
- API credentials are NEVER returned to the frontend — only sanitised metadata.
- Protocol detection uses minimal, safe probe requests; no user data is sent.

Supported protocols (auto-detected):
  openai_compatible   GET /models → { "object": "list", "data": [...] }
  gemini_compatible   GET /v1beta/models?key=... → { "models": [...] }
  unsupported         Anything else; ADAM will not send arbitrary payloads.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UnsafeEndpointError(ValueError):
    """Raised when a URL fails SSRF guard validation.

    The message must NOT contain the API key or internal network topology.
    """

class ProviderAuthenticationError(PermissionError):
    """Raised when a provider rejects the supplied credentials (401/403)."""

class UnsupportedProtocolError(ValueError):
    """Raised when protocol auto-detection cannot determine a compatible API format."""


# ---------------------------------------------------------------------------
# SSRF Guard — mandatory, enforced server-side
# ---------------------------------------------------------------------------

# RFC 1918 private ranges + loopback + link-local + cloud metadata
_BLOCKED_IPV4_NETWORKS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),         # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),       # link-local + AWS metadata
    ipaddress.IPv4Network("100.64.0.0/10"),        # shared address space
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("240.0.0.0/4"),          # reserved
    ipaddress.IPv4Network("198.18.0.0/15"),        # benchmark
    ipaddress.IPv4Network("192.0.0.0/24"),
    ipaddress.IPv4Network("192.0.2.0/24"),
    ipaddress.IPv4Network("198.51.100.0/24"),
    ipaddress.IPv4Network("203.0.113.0/24"),
]

_BLOCKED_IPV6_NETWORKS = [
    ipaddress.IPv6Network("::1/128"),              # loopback
    ipaddress.IPv6Network("fc00::/7"),             # unique local
    ipaddress.IPv6Network("fe80::/10"),            # link-local
    ipaddress.IPv6Network("fd00::/8"),             # EC2 metadata variant
    ipaddress.IPv6Network("::ffff:0:0/96"),        # IPv4-mapped
    ipaddress.IPv6Network("100::/64"),             # RFC 6666 blackhole
]

_ALLOWED_REMOTE_SCHEMES = {"https"}
_ALLOWED_LOCAL_SCHEMES = {"http", "https"}
_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript", "ssh", "ldap", "smtp"}

# Well-known metadata service IPs
_METADATA_IPS = {
    "169.254.169.254",   # AWS / GCP / Azure (IPv4)
    "fd00:ec2::254",     # AWS (IPv6)
    "169.254.0.1",
}

# Connection + response timeouts for SSRF validation probes
_SSRF_CONNECT_TIMEOUT = 5.0
_SSRF_READ_TIMEOUT = 10.0
_SSRF_TOTAL_TIMEOUT = 15.0
_MAX_PROBE_RESPONSE_BYTES = 512 * 1024  # 512 KB


def _is_ip_blocked(ip_str: str) -> bool:
    """Return True if the resolved IP is in any blocked range."""
    if ip_str in _METADATA_IPS:
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
        if isinstance(addr, ipaddress.IPv4Address):
            return any(addr in net for net in _BLOCKED_IPV4_NETWORKS)
        if isinstance(addr, ipaddress.IPv6Address):
            return any(addr in net for net in _BLOCKED_IPV6_NETWORKS)
    except ValueError:
        pass
    return False


class SSRFGuard:
    """Validates user-provided URLs before any outbound request is made.

    All SSRF protections are enforced server-side; frontend restrictions are
    advisory only and cannot substitute for this check.

    Usage::

        guard = SSRFGuard()
        guard.validate("https://api.example.com/v1")  # OK
        guard.validate("http://192.168.1.1/")          # raises UnsafeEndpointError
    """

    def validate(self, url: str, allow_local: bool = False) -> None:
        """Validate a URL against SSRF protection rules.

        Args:
            url: The raw, user-supplied endpoint URL.
            allow_local: Set True only for explicitly local runtime endpoints
                (Ollama at localhost).  When True, HTTP is permitted and loopback
                (127.x) is allowed, but all RFC 1918, link-local, and metadata
                addresses are still blocked.

        Raises:
            UnsafeEndpointError: On any violation.
        """
        if not url or not url.strip():
            raise UnsafeEndpointError("Endpoint URL must not be empty.")

        # 1. Parse URL — also catch ValueError from out-of-range ports
        try:
            parsed = urllib.parse.urlparse(url.strip())
            # Access .port here to trigger ValueError early for invalid port values
            port = parsed.port
        except ValueError as exc:
            raise UnsafeEndpointError(
                f"Port is outside the valid range 0-65535."
            ) from exc
        except Exception:
            raise UnsafeEndpointError("Endpoint URL could not be parsed.")

        scheme = (parsed.scheme or "").lower()
        hostname = (parsed.hostname or "").lower()

        # 2. Block explicitly unsafe schemes
        if scheme in _BLOCKED_SCHEMES:
            raise UnsafeEndpointError(
                f"Scheme '{scheme}' is not permitted. Use HTTPS for remote endpoints."
            )

        # 3. Require HTTPS for remote endpoints
        if not allow_local:
            if scheme not in _ALLOWED_REMOTE_SCHEMES:
                raise UnsafeEndpointError(
                    "Remote endpoints must use HTTPS. Plain HTTP is not permitted."
                )
        else:
            if scheme not in _ALLOWED_LOCAL_SCHEMES:
                raise UnsafeEndpointError(
                    f"Scheme '{scheme}' is not permitted even for local endpoints."
                )

        if not hostname:
            raise UnsafeEndpointError("Endpoint URL must include a valid hostname.")

        # 4. Block loopback for remote mode; allow it explicitly in local mode
        if not allow_local:
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                raise UnsafeEndpointError(
                    "Loopback addresses are not permitted for remote endpoints."
                )

        # 5. Resolve hostname and check all returned IPs
        try:
            resolved = socket.getaddrinfo(hostname, port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UnsafeEndpointError(
                "Hostname could not be resolved. DNS lookup failed."
            ) from exc

        for family, _type, _proto, _canonname, sockaddr in resolved:
            ip_str = sockaddr[0]
            # In local mode, loopback (127.x, ::1) is allowed
            if allow_local and ip_str in ("127.0.0.1", "::1", "0.0.0.0"):
                continue
            if _is_ip_blocked(ip_str):
                raise UnsafeEndpointError(
                    "The resolved IP address is in a restricted range "
                    "(private, loopback, link-local, or cloud metadata address). "
                    "Only publicly routable endpoints are permitted."
                )

        # 6. Validate port range (already caught ValueError above, just double-check)
        if port is not None and not (1 <= port <= 65535):
            raise UnsafeEndpointError(f"Port {port} is outside the valid range 1–65535.")


# ---------------------------------------------------------------------------
# Protocol detection
# ---------------------------------------------------------------------------

class ProtocolDetector:
    """Sends minimal safe probe requests to auto-detect the API protocol.

    Only GET requests are issued.  No user data, no generation prompts,
    no ADAM records are sent during detection.
    """

    PROBE_TIMEOUT = httpx.Timeout(
        connect=_SSRF_CONNECT_TIMEOUT,
        read=_SSRF_READ_TIMEOUT,
        write=5.0,
        pool=5.0,
    )

    def detect(
        self,
        endpoint_url: str,
        api_key: Optional[str] = None,
    ) -> str:
        """Return the detected protocol string.

        Returns:
            "openai_compatible" | "gemini_compatible" | "unsupported"
        """
        base = endpoint_url.rstrip("/")
        headers: Dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # ---- Try OpenAI-compatible: GET /models ----
        try:
            with httpx.Client(timeout=self.PROBE_TIMEOUT) as client:
                resp = client.get(f"{base}/models", headers=headers)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        # Both OpenAI and many clones return {"object": "list", "data": [...]}
                        if isinstance(data, dict) and (
                            data.get("object") == "list" or isinstance(data.get("data"), list)
                        ):
                            logger.debug("Protocol detected: openai_compatible for %s", base)
                            return "openai_compatible"
                    except Exception:
                        pass
                elif resp.status_code in (401, 403):
                    # Endpoint exists and uses OpenAI auth scheme but key is wrong
                    logger.debug(
                        "OpenAI-compatible endpoint detected (auth required) at %s", base
                    )
                    return "openai_compatible"
        except Exception:
            pass

        # ---- Try Gemini-compatible: GET /v1beta/models ----
        try:
            probe_url = f"{base}/v1beta/models"
            params = {}
            if api_key:
                params["key"] = api_key
            with httpx.Client(timeout=self.PROBE_TIMEOUT) as client:
                resp = client.get(probe_url, params=params)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and isinstance(data.get("models"), list):
                            logger.debug("Protocol detected: gemini_compatible for %s", base)
                            return "gemini_compatible"
                    except Exception:
                        pass
                elif resp.status_code in (400, 401, 403):
                    # Gemini returns 400 for bad/missing key, 403 for permission denied
                    logger.debug("Gemini-compatible endpoint detected at %s", base)
                    return "gemini_compatible"
        except Exception:
            pass

        logger.debug("Protocol detection failed for %s — returning unsupported.", base)
        return "unsupported"


# ---------------------------------------------------------------------------
# Remote provider data model
# ---------------------------------------------------------------------------

@dataclass
class RemoteProviderConfig:
    """Sanitised metadata for a user-registered remote API provider.

    IMPORTANT: The ``_api_key`` attribute is intentionally prefixed with an
    underscore and excluded from ``to_dict()`` so that credentials are never
    accidentally serialised into log lines or API responses.
    """
    provider_id: str
    name: str                        # user-supplied, sanitised
    endpoint_url: str                # validated HTTPS URL
    protocol: str                    # "openai_compatible" | "gemini_compatible" | "unsupported"
    display_name: str                # safe normalised label
    status: str = "checking"         # checking | active | unavailable | auth_failed
    registered_at: float = field(default_factory=time.time)
    last_checked: float = field(default_factory=time.time)
    model_ids: List[str] = field(default_factory=list)
    _api_key: Optional[str] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise provider metadata — credentials are NEVER included."""
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "display_name": self.display_name,
            "endpoint_url": self.endpoint_url,
            "protocol": self.protocol,
            "status": self.status,
            "registered_at": self.registered_at,
            "last_checked": self.last_checked,
            "model_count": len(self.model_ids),
        }


# ---------------------------------------------------------------------------
# Remote provider registry
# ---------------------------------------------------------------------------

class RemoteProviderRegistry:
    """In-memory store of registered remote API providers.

    Providers are keyed by ``provider_id`` (a short UUID).  A provider's API
    key is stored only in memory for the lifetime of the process; it is never
    written to disk, logs, or API responses.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, RemoteProviderConfig] = {}
        self._guard = SSRFGuard()
        self._detector = ProtocolDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        endpoint_url: str,
        display_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> RemoteProviderConfig:
        """Validate, probe, and register a remote provider.

        Steps:
        1. SSRF guard validates the URL.
        2. Protocol auto-detection.
        3. Build sanitised config (key stored in ``_api_key``; never in dict).
        4. Register and return.

        Raises:
            UnsafeEndpointError: If the URL fails SSRF guard.
            UnsupportedProtocolError: If protocol cannot be detected.
        """
        # 1. SSRF guard
        self._guard.validate(endpoint_url, allow_local=False)

        # 2. Sanitise display name
        safe_display = _sanitise_provider_name(display_name or name)

        # 3. Protocol detection (never sends user data)
        protocol = self._detector.detect(endpoint_url, api_key=api_key)

        # 4. Build config
        provider_id = f"provider_{uuid.uuid4().hex[:12]}"
        config = RemoteProviderConfig(
            provider_id=provider_id,
            name=_sanitise_provider_name(name),
            endpoint_url=endpoint_url.rstrip("/"),
            protocol=protocol,
            display_name=safe_display,
            status="active" if protocol != "unsupported" else "unavailable",
            _api_key=api_key,
        )
        self._providers[provider_id] = config
        logger.info(
            "Remote provider '%s' registered [id=%s, protocol=%s].",
            safe_display,
            provider_id,
            protocol,
        )
        return config

    def get(self, provider_id: str) -> Optional[RemoteProviderConfig]:
        return self._providers.get(provider_id)

    def remove(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            del self._providers[provider_id]
            return True
        return False

    def list_all(self) -> List[RemoteProviderConfig]:
        return list(self._providers.values())

    def get_api_key(self, provider_id: str) -> Optional[str]:
        """Return the stored key for internal use. Never call from API handlers."""
        config = self._providers.get(provider_id)
        return config._api_key if config else None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

# Shared provider registry — imported by the API router
REMOTE_PROVIDER_REGISTRY = RemoteProviderRegistry()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _sanitise_provider_name(raw: str) -> str:
    """Return an HTML-safe, printable provider display name."""
    if not raw:
        return "Custom API"
    cleaned = "".join(ch for ch in raw if ch >= " ")
    cleaned = re.sub(r"[<>&\"']", "", cleaned)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return "Custom API"
    return cleaned[:80]
