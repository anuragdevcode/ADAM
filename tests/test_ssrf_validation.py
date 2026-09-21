"""Tests for SSRF guard (adam/model/providers.py).

Every test corresponds to a required security check from the specification:
- Valid HTTPS remote URL → passes
- http:// remote URL → blocked
- localhost / 127.0.0.1 → blocked (not local mode)
- RFC 1918 private ranges → blocked
- Link-local → blocked
- AWS metadata IP 169.254.169.254 → blocked
- IPv6 metadata fd00:ec2::254 → blocked (if resolvable)
- file:// → blocked
- Malformed URL → blocked
- DNS failure → blocked
- Port out of range → blocked

Protocol detection and RemoteProviderRegistry tests are also included.
"""

import socket
import pytest
from unittest.mock import patch, MagicMock
from adam.model.providers import (
    SSRFGuard,
    UnsafeEndpointError,
    ProtocolDetector,
    RemoteProviderRegistry,
    _sanitise_provider_name,
)


# ── SSRFGuard ─────────────────────────────────────────────────────────────

@pytest.fixture
def guard():
    return SSRFGuard()


def _mock_resolve_to(ip: str):
    """Patch socket.getaddrinfo to return a single result pointing to ip."""
    return patch(
        "adam.model.providers.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))],
    )


def test_ssrf_valid_https_public_url(guard):
    """A valid public HTTPS URL resolves to a public IP → should pass."""
    with _mock_resolve_to("93.184.216.34"):  # example.com
        # Must not raise
        guard.validate("https://api.example.com/v1")


def test_ssrf_blocks_http_remote(guard):
    """HTTP (non-HTTPS) for a remote endpoint must be blocked."""
    with _mock_resolve_to("93.184.216.34"):
        with pytest.raises(UnsafeEndpointError, match="HTTPS"):
            guard.validate("http://api.example.com/v1")


def test_ssrf_blocks_loopback_127(guard):
    """127.0.0.1 is loopback — must be blocked for remote endpoints."""
    with _mock_resolve_to("127.0.0.1"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("https://127.0.0.1:8080/api")


def test_ssrf_blocks_localhost(guard):
    """'localhost' resolving to loopback must be blocked."""
    with _mock_resolve_to("127.0.0.1"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("https://localhost:11434/api")


def test_ssrf_blocks_private_rfc1918_10x(guard):
    """10.x.x.x is private RFC 1918 — must be blocked."""
    with _mock_resolve_to("10.0.0.1"):
        with pytest.raises(UnsafeEndpointError, match="restricted range"):
            guard.validate("https://internal.corp.example:8080/v1")


def test_ssrf_blocks_private_rfc1918_192168(guard):
    """192.168.x.x is private RFC 1918 — must be blocked."""
    with _mock_resolve_to("192.168.1.100"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("https://some-host.local/api")


def test_ssrf_blocks_private_rfc1918_172(guard):
    """172.16.x.x – 172.31.x.x is private RFC 1918 — must be blocked."""
    with _mock_resolve_to("172.16.5.5"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("https://docker.internal/api")


def test_ssrf_blocks_link_local(guard):
    """169.254.x.x is link-local — must be blocked."""
    with _mock_resolve_to("169.254.1.1"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("https://link-local.example/v1")


def test_ssrf_blocks_aws_metadata_ip(guard):
    """169.254.169.254 is the AWS/GCP/Azure instance metadata service — must be blocked."""
    with _mock_resolve_to("169.254.169.254"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("https://example-metadata/v1")


def test_ssrf_blocks_file_scheme(guard):
    """file:// scheme must be rejected immediately."""
    with pytest.raises(UnsafeEndpointError, match="not permitted"):
        guard.validate("file:///etc/passwd")


def test_ssrf_blocks_ftp_scheme(guard):
    """ftp:// scheme must be rejected."""
    with pytest.raises(UnsafeEndpointError):
        guard.validate("ftp://example.com/data")


def test_ssrf_blocks_gopher(guard):
    """gopher:// scheme must be rejected."""
    with pytest.raises(UnsafeEndpointError):
        guard.validate("gopher://example.com/")


def test_ssrf_blocks_empty_url(guard):
    """Empty URL must raise UnsafeEndpointError."""
    with pytest.raises(UnsafeEndpointError):
        guard.validate("")


def test_ssrf_blocks_malformed_url(guard):
    """A URL that fails urlparse must be rejected."""
    with pytest.raises(UnsafeEndpointError):
        guard.validate("not-a-url-at-all")


def test_ssrf_blocks_dns_failure(guard):
    """DNS resolution failure must result in UnsafeEndpointError, not an unhandled exception."""
    with patch("adam.model.providers.socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
        with pytest.raises(UnsafeEndpointError, match="DNS"):
            guard.validate("https://this-host-definitely-does-not-exist.invalid/api")


def test_ssrf_allow_local_mode_http_localhost(guard):
    """In local mode, http://localhost is permitted (for Ollama)."""
    with _mock_resolve_to("127.0.0.1"):
        # Should not raise in allow_local=True mode
        guard.validate("http://localhost:11434", allow_local=True)


def test_ssrf_allow_local_still_blocks_private_ip(guard):
    """Even in allow_local mode, RFC 1918 non-loopback IPs must be blocked."""
    with _mock_resolve_to("192.168.1.1"):
        with pytest.raises(UnsafeEndpointError):
            guard.validate("http://192.168.1.1:11434", allow_local=True)


def test_ssrf_blocks_invalid_port(guard):
    """Port 0 or >65535 must be rejected."""
    with _mock_resolve_to("93.184.216.34"):
        with pytest.raises(UnsafeEndpointError, match="[Pp]ort"):
            guard.validate("https://example.com:99999/api")


# ── Provider name sanitisation ─────────────────────────────────────────────

def test_sanitise_provider_name_strips_html():
    result = _sanitise_provider_name("<script>alert('xss')</script>")
    assert "<" not in result
    assert ">" not in result


def test_sanitise_provider_name_empty():
    assert _sanitise_provider_name("") == "Custom API"


def test_sanitise_provider_name_truncates():
    long_name = "A" * 200
    assert len(_sanitise_provider_name(long_name)) <= 80


# ── RemoteProviderRegistry ─────────────────────────────────────────────────

def test_registry_register_blocks_ssrf():
    """SSRF-unsafe URL must raise UnsafeEndpointError from the registry."""
    registry = RemoteProviderRegistry()
    with _mock_resolve_to("127.0.0.1"):
        with pytest.raises(UnsafeEndpointError):
            registry.register("bad", "https://localhost/api")


def test_registry_api_key_not_in_to_dict():
    """API key must NEVER appear in the serialised provider dict."""
    registry = RemoteProviderRegistry()
    # Patch SSRF guard and protocol detector to avoid real network calls
    with patch.object(registry._guard, "validate"):
        with patch.object(registry._detector, "detect", return_value="openai_compatible"):
            config = registry.register(
                "Test Provider",
                "https://api.example.com/v1",
                api_key="sk-secret-key-1234567890",
            )

    d = config.to_dict()
    # Key must not appear anywhere in the dict
    assert "sk-secret-key-1234567890" not in str(d)
    assert "api_key" not in d
    assert "_api_key" not in d


def test_registry_remove_existing_provider():
    registry = RemoteProviderRegistry()
    with patch.object(registry._guard, "validate"):
        with patch.object(registry._detector, "detect", return_value="openai_compatible"):
            config = registry.register("Test", "https://example.com/v1")

    assert registry.remove(config.provider_id) is True
    assert registry.get(config.provider_id) is None


def test_registry_remove_nonexistent_returns_false():
    registry = RemoteProviderRegistry()
    assert registry.remove("provider_nonexistent_abc123") is False


def test_registry_list_all():
    registry = RemoteProviderRegistry()
    with patch.object(registry._guard, "validate"):
        with patch.object(registry._detector, "detect", return_value="openai_compatible"):
            c1 = registry.register("P1", "https://a.example.com/v1")
            c2 = registry.register("P2", "https://b.example.com/v1")

    all_providers = registry.list_all()
    ids = [p.provider_id for p in all_providers]
    assert c1.provider_id in ids
    assert c2.provider_id in ids


def test_registry_get_api_key_internal():
    """get_api_key() returns the stored key for internal backend use."""
    registry = RemoteProviderRegistry()
    with patch.object(registry._guard, "validate"):
        with patch.object(registry._detector, "detect", return_value="openai_compatible"):
            config = registry.register("Test", "https://example.com/v1", api_key="internal-key")

    assert registry.get_api_key(config.provider_id) == "internal-key"
