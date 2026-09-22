"""Server-Side Request Forgery (SSRF) protection and IP validation.

Enforces strict network security guardrails for external HTTP/HTTPS requests:
1. Protocol scheme restricted to http and https only.
2. DNS pre-resolution with comprehensive IP address range validation.
3. Blocks loopback (127.0.0.0/8, ::1), link-local (169.254.0.0/16, fe80::/10),
   private subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), carrier-grade NAT
   (100.64.0.0/10), broadcast/multicast (224.0.0.0/4, ff00::/8), and unspecified IPs.
4. Strictly blocks cloud metadata endpoints (169.254.169.254, metadata.google.internal).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import List, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFSecurityError(PermissionError):
    """Raised when an outbound URL violates SSRF security boundaries."""
    pass


class SSRFGuard:
    """Validates target URLs and hostnames against SSRF vulnerabilities."""

    ALLOWED_SCHEMES = {"http", "https"}

    BLOCKED_HOSTNAMES = {
        "localhost",
        "metadata.google.internal",
        "metadata.internal",
        "instance-data",
    }

    # Explicit cloud metadata IPs
    BLOCKED_IPS = {
        "169.254.169.254",
        "169.254.169.253",
        "fd00:ec2::254",
    }

    @classmethod
    def is_ip_private_or_reserved(cls, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Check if IP address is private, loopback, link-local, reserved, or multicast."""
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or str(ip) in cls.BLOCKED_IPS
        )

    @classmethod
    def is_forbidden_ip(cls, ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Check if IP address is forbidden, accepting string or ipaddress object."""
        if isinstance(ip, str):
            try:
                ip_obj = ipaddress.ip_address(ip.strip())
            except ValueError:
                return True
            return cls.is_ip_private_or_reserved(ip_obj)
        return cls.is_ip_private_or_reserved(ip)

    @classmethod
    def resolve_hostname_ips(cls, hostname: str, port: int = 443) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        """Resolve hostname to a list of ipaddress objects."""
        clean_host = hostname.strip().strip("[]").lower()

        # Check if already an IP literal
        try:
            ip_obj = ipaddress.ip_address(clean_host)
            return [ip_obj]
        except ValueError:
            pass

        try:
            addr_info = socket.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise SSRFSecurityError(f"DNS resolution failed for host '{clean_host}': {e}") from e

        resolved_ips = []
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                resolved_ips.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue

        if not resolved_ips:
            raise SSRFSecurityError(f"No IP addresses resolved for host '{clean_host}'.")

        return resolved_ips

    @classmethod
    def validate_url(cls, url: str) -> Tuple[str, str, List[str]]:
        """Validate target URL against SSRF boundaries.

        Returns:
            Tuple of (clean_url, hostname, list_of_validated_ip_strings)

        Raises:
            SSRFSecurityError: If URL fails scheme or IP destination checks.
        """
        if not url or not isinstance(url, str):
            raise SSRFSecurityError("URL must be a non-empty string.")

        try:
            parsed = urlparse(url.strip())
        except Exception as e:
            raise SSRFSecurityError(f"Malformed URL: {e}") from e

        scheme = (parsed.scheme or "").lower()
        if scheme not in cls.ALLOWED_SCHEMES:
            raise SSRFSecurityError(
                f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."
            )

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise SSRFSecurityError("URL contains no valid host identifier.")

        if hostname in cls.BLOCKED_HOSTNAMES:
            raise SSRFSecurityError(f"Access to blocked internal hostname '{hostname}' is denied.")

        port = parsed.port or (443 if scheme == "https" else 80)

        # Resolve IPs
        resolved = cls.resolve_hostname_ips(hostname, port)

        for ip in resolved:
            if cls.is_ip_private_or_reserved(ip):
                raise SSRFSecurityError(
                    f"SSRF Security Violation: Host '{hostname}' resolves to restricted IP {ip} "
                    "(private/loopback/link-local/cloud metadata address space)."
                )

        validated_ips = [str(ip) for ip in resolved]
        return url.strip(), hostname, validated_ips
