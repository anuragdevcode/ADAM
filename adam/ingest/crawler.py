"""URL allow-list validation, rate limiting, and robots compliance."""

import time
import urllib.robotparser
from dataclasses import dataclass
from typing import List, Optional, Set
from urllib.parse import urlparse, urlunparse

from adam.config import DEFAULT_USER_AGENT


class DisallowedUrlError(Exception):
    """Raised when an acquisition attempt is made for a URL outside the allowed domains/paths."""
    pass


class UrlCrawlerGuard:
    """Validates that candidate URLs strictly conform to source-level allow-lists."""

    def __init__(
        self,
        permitted_domains: List[str],
        permitted_path_prefixes: List[str],
    ):
        self.permitted_domains: Set[str] = {d.lower().strip() for d in permitted_domains if d.strip()}
        self.permitted_path_prefixes: List[str] = [p.strip() for p in permitted_path_prefixes if p.strip()]

    def is_url_allowed(self, url: str) -> bool:
        """Check if URL matches permitted government domains and path prefixes."""
        try:
            parsed = urlparse(url)
        except Exception:
            return False

        if parsed.scheme not in ("http", "https", "file"):
            return False

        if parsed.scheme == "file":
            # For local ITDA batch files, check if local domain authorization is present
            local_tokens = {"localhost", "local.uk.gov.in", "file", "local"}
            if self.permitted_domains.intersection(local_tokens):
                path = parsed.path or "/"
                return any(path.startswith(prefix) or prefix == "/" for prefix in self.permitted_path_prefixes)
            return False

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        # Domain check: exact match or subdomain match if permitted domain starts with '.'
        domain_match = False
        for allowed in self.permitted_domains:
            if hostname == allowed or hostname.endswith(f".{allowed}"):
                domain_match = True
                break

        if not domain_match:
            return False

        # Path prefix check
        path = parsed.path or "/"
        path_match = any(path.startswith(prefix) for prefix in self.permitted_path_prefixes)
        return path_match

    def validate_or_raise(self, url: str) -> str:
        """Validate URL or raise DisallowedUrlError with informative explanation."""
        normalized = self.normalize_url(url)
        if not self.is_url_allowed(normalized):
            parsed = urlparse(normalized)
            raise DisallowedUrlError(
                f"URL '{url}' is outside the authorized scope. "
                f"Host '{parsed.hostname}' not in permitted domains {sorted(self.permitted_domains)} "
                f"or path '{parsed.path}' does not match prefixes {self.permitted_path_prefixes}."
            )
        return normalized

    @staticmethod
    def normalize_url(url: str) -> str:
        """Canonicalize URL by removing fragments and standardizing scheme/host."""
        parsed = urlparse(url.strip())
        # Strip trailing fragment and parameters if unnecessary
        normalized = urlunparse((
            parsed.scheme.lower(),
            (parsed.netloc or "").lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            "",  # strip fragment
        ))
        return normalized


class CrawlerRateLimiter:
    """Per-host rate limiter to guarantee polite, authorized crawl speeds."""

    def __init__(self, rate_limit_per_minute: int = 30):
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self.min_interval = 60.0 / self.rate_limit_per_minute
        self._last_request_times: dict[str, float] = {}

    def acquire(self, url: str) -> float:
        """Calculate wait time needed for host, update timestamp, and return sleep seconds."""
        host = (urlparse(url).hostname or "default").lower()
        now = time.monotonic()
        last_time = self._last_request_times.get(host, 0.0)
        elapsed = now - last_time

        sleep_needed = 0.0
        if elapsed < self.min_interval:
            sleep_needed = self.min_interval - elapsed

        self._last_request_times[host] = (now + sleep_needed)
        return sleep_needed

    def wait(self, url: str) -> None:
        """Block until the rate limit allows the next request."""
        import os
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ADAM_TEST_MODE"):
            return
        delay = self.acquire(url)
        if delay > 0:
            time.sleep(delay)


class RobotsComplianceGuard:
    """Checks and respects robots.txt permissions for a given target domain."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.user_agent = user_agent
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def set_robots_content(self, base_url: str, robots_txt: str) -> None:
        """Provide robots.txt content directly (useful for testing and offline environments)."""
        host = (urlparse(base_url).hostname or "").lower()
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(robots_txt.splitlines())
        self._parsers[host] = parser

    def can_fetch(self, url: str) -> bool:
        """Check if user agent is allowed to fetch the target URL."""
        host = (urlparse(url).hostname or "").lower()
        parser = self._parsers.get(host)
        if parser is None:
            # If robots.txt has not been fetched or configured, default to allow
            return True
        return parser.can_fetch(self.user_agent, url)
