"""Secure, domain-aware, rate-limited, and SSRF-safe web research client.

Provides:
- SSRF-hardened URL fetching with BeautifulSoup markdown extraction.
- Host-based polite rate limiting and timeout enforcement.
- Domain-aware external search engine with provenance tagging.
- Clear distinction between official government domains and general web sources.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx

from adam.security.ssrf import SSRFGuard, SSRFSecurityError

logger = logging.getLogger(__name__)


@dataclass
class WebSearchResultItem:
    """Individual organic search result item with provenance."""
    title: str
    url: str
    snippet: str
    domain: str
    is_gov_domain: bool = False
    published_date: Optional[str] = None
    provenance_type: str = "EXTERNAL_WEB"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "domain": self.domain,
            "is_gov_domain": self.is_gov_domain,
            "published_date": self.published_date,
            "provenance_type": self.provenance_type,
        }


@dataclass
class WebPageResult:
    """Structured extraction of a fetched web page."""
    url: str
    domain: str
    title: str
    content: str
    status_code: int
    fetched_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_gov_domain: bool = False
    provenance_type: str = "EXTERNAL_WEB"
    char_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "content": self.content,
            "status_code": self.status_code,
            "fetched_at_utc": self.fetched_at_utc,
            "is_gov_domain": self.is_gov_domain,
            "provenance_type": self.provenance_type,
            "char_count": self.char_count,
        }


class WebRateLimitExceeded(Exception):
    """Raised when an external domain rate limit is exceeded."""
    pass


class WebRateLimiter:
    """Per-domain thread-safe sliding window rate limiter."""

    def __init__(
        self,
        max_requests_per_minute: int = 20,
        min_interval_seconds: float = 0.5,
        window_seconds: float = 60.0,
        max_per_window: Optional[int] = None,
    ):
        self.max_requests_per_minute = max_per_window or max(1, max_requests_per_minute)
        self.min_interval = min_interval_seconds
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._history: Dict[str, List[float]] = {}
        self._last_access: Dict[str, float] = {}

    def check_and_record(self, domain: str, raise_on_exceeded: bool = True) -> bool:
        """Immediate non-blocking rate limit verification."""
        clean_domain = domain.strip().lower()
        with self._lock:
            now = time.time()
            window = self._history.setdefault(clean_domain, [])
            self._history[clean_domain] = [t for t in window if now - t < self.window_seconds]
            if len(self._history[clean_domain]) >= self.max_requests_per_minute:
                if raise_on_exceeded:
                    raise WebRateLimitExceeded(f"Rate limit exceeded for domain {clean_domain}")
                return False
            self._history[clean_domain].append(now)
            self._last_access[clean_domain] = now
            return True

    def acquire(self, domain: str, timeout: float = 5.0) -> bool:
        """Block until access is permitted under rate limits or timeout occurs."""
        start_wait = time.perf_counter()
        clean_domain = domain.strip().lower()

        while (time.perf_counter() - start_wait) < timeout:
            with self._lock:
                now = time.time()
                window = self._history.setdefault(clean_domain, [])
                self._history[clean_domain] = [t for t in window if now - t < self.window_seconds]

                last_t = self._last_access.get(clean_domain, 0.0)
                if len(self._history[clean_domain]) < self.max_requests_per_minute and (now - last_t) >= self.min_interval:
                    self._history[clean_domain].append(now)
                    self._last_access[clean_domain] = now
                    return True

            time.sleep(0.05)

        return False


# Global default rate limiter
GLOBAL_WEB_RATE_LIMITER = WebRateLimiter(max_requests_per_minute=20, min_interval_seconds=0.5)


class SecureWebFetcher:
    """SSRF-hardened web page fetcher and markdown extractor."""

    MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MB ceiling
    DEFAULT_TIMEOUT_SECONDS = 5.0

    USER_AGENT = "ADAM-GovResearch/1.0 (+https://uk.gov.in/adam-bot; polite public records research)"

    GOV_DOMAIN_SUFFIXES = (
        ".gov.in",
        ".nic.in",
        ".ac.in",
        ".res.in",
        ".edu.in",
        "gov.in",
        "nic.in",
    )

    def __init__(
        self,
        rate_limiter: Optional[WebRateLimiter] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.rate_limiter = rate_limiter or GLOBAL_WEB_RATE_LIMITER
        self.timeout_seconds = timeout_seconds

    @classmethod
    def is_gov_domain(cls, domain: str) -> bool:
        """Check if domain represents an official Indian government / public authority portal."""
        d = domain.lower().strip()
        return any(d.endswith(suffix) or d == suffix.lstrip(".") for suffix in cls.GOV_DOMAIN_SUFFIXES)

    def fetch(self, url: str, extract_tables: bool = True) -> WebPageResult:
        """Fetch URL content with strict SSRF validation and clean text extraction.

        Raises:
            SSRFSecurityError: If destination resolves to restricted IP ranges.
            httpx.HTTPError: If connection or HTTP transfer fails.
        """
        # 1. SSRF Pre-flight validation
        clean_url, hostname, _ = SSRFGuard.validate_url(url)
        is_gov = self.is_gov_domain(hostname)

        # 2. Polite rate limiting
        acquired = self.rate_limiter.acquire(hostname, timeout=self.timeout_seconds)
        if not acquired:
            raise TimeoutError(f"Rate limit exceeded for host '{hostname}'. Request throttled.")

        # 3. HTTP Request with stream inspection
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        }

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=False,  # Inspect each redirect step for SSRF
            headers=headers,
        ) as client:
            current_url = clean_url
            response = None

            for _ in range(3):  # Max 3 redirects
                # Validate current URL before request
                SSRFGuard.validate_url(current_url)

                resp = client.get(current_url)
                if resp.is_redirect:
                    redir_target = resp.headers.get("Location")
                    if not redir_target:
                        break
                    # Resolve relative redirect URLs
                    from urllib.parse import urljoin
                    current_url = urljoin(current_url, redir_target)
                    continue
                else:
                    response = resp
                    break

            if response is None:
                raise httpx.HTTPError(f"Failed to fetch content from {clean_url}: redirect loop or empty response.")

            if response.status_code >= 400:
                return WebPageResult(
                    url=clean_url,
                    domain=hostname,
                    title=f"Error {response.status_code}",
                    content=f"External server responded with HTTP status {response.status_code}.",
                    status_code=response.status_code,
                    is_gov_domain=is_gov,
                    char_count=0,
                )

            # Enforce size ceiling
            content_bytes = response.content[: self.MAX_RESPONSE_BYTES]

        # 4. Clean HTML & Markdown extraction
        parsed_title, extracted_text = self._parse_html(content_bytes, extract_tables=extract_tables)

        return WebPageResult(
            url=clean_url,
            domain=hostname,
            title=parsed_title or hostname,
            content=extracted_text,
            status_code=response.status_code,
            is_gov_domain=is_gov,
            char_count=len(extracted_text),
        )

    def _parse_html(self, content_bytes: bytes, extract_tables: bool = True) -> Tuple[str, str]:
        """Strip boilerplate and extract clean content using BeautifulSoup."""
        try:
            soup = BeautifulSoup(content_bytes, "html.parser")
        except Exception:
            text = content_bytes.decode("utf-8", errors="replace")
            return "", text[:5000]

        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""

        # Remove non-content tags
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form"]):
            tag.decompose()

        # Handle tables if requested
        if extract_tables:
            for table in soup.find_all("table"):
                md_table = self._table_to_markdown(table)
                if md_table:
                    table.replace_with(f"\n\n{md_table}\n\n")

        # Extract body text
        body = soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True)

        # Collapse excessive newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", text)
        return title, cleaned[:15000]

    def _html_to_clean_markdown(self, html_content: str | bytes) -> str:
        """Convenience method to convert HTML string or bytes to markdown."""
        content_bytes = html_content.encode("utf-8") if isinstance(html_content, str) else html_content
        _, md = self._parse_html(content_bytes)
        return md

    def _table_to_markdown(self, table_soup: Any) -> str:
        """Convert HTML table to GitHub-flavored markdown table."""
        rows = table_soup.find_all("tr")
        if not rows:
            return ""

        table_data = []
        for row in rows:
            cols = row.find_all(["th", "td"])
            col_texts = [re.sub(r"\s+", " ", col.get_text().strip()) for col in cols]
            if any(col_texts):
                table_data.append(col_texts)

        if not table_data:
            return ""

        # Normalize column counts
        max_cols = max(len(r) for r in table_data)
        normalized = [r + [""] * (max_cols - len(r)) for r in table_data]

        headers = normalized[0]
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * max_cols) + " |"

        data_lines = []
        for row in normalized[1:]:
            data_lines.append("| " + " | ".join(row) + " |")

        return "\n".join([header_line, sep_line] + data_lines)


class SecureWebSearchEngine:
    """Domain-aware external search engine with SSRF validation and provenance."""

    _search_mock_handler: Optional[Callable[[str, Optional[str], int], List[WebSearchResultItem]]] = None

    def __init__(self, fetcher: Optional[SecureWebFetcher] = None):
        self.fetcher = fetcher or SecureWebFetcher()

    @classmethod
    def set_mock_handler(
        cls,
        handler: Optional[Callable[[str, Optional[str], int], List[WebSearchResultItem]]],
    ) -> None:
        """Inject custom search handler for testing or offline environments."""
        cls._search_mock_handler = staticmethod(handler) if handler is not None else None

    def register_mock_result(self, query_prefix: str, items: List[Dict[str, Any]]) -> None:
        """Convenience method to register mock search results for unit tests."""
        converted = [
            WebSearchResultItem(
                title=it.get("title", ""),
                url=it.get("url", ""),
                snippet=it.get("snippet", ""),
                domain=it.get("domain", ""),
                is_gov_domain="gov.in" in it.get("domain", "") or "nic.in" in it.get("domain", ""),
            )
            for it in items
        ]
        self.set_mock_handler(lambda q, df, mx: converted[:mx])

    def search(
        self,
        query: str,
        domain_filter: Optional[str] = None,
        max_results: int = 5,
    ) -> List[WebSearchResultItem]:
        """Perform domain-aware web search, returning verified results.

        Prioritizes official public authority domains (.gov.in, .nic.in).
        """
        clean_q = query.strip()
        if not clean_q:
            return []

        # Use mock handler if configured (e.g. during offline unit tests)
        if self._search_mock_handler is not None:
            return self._search_mock_handler(clean_q, domain_filter, max_results)

        # Live search via DuckDuckGo Lite API / HTML parser
        results: List[WebSearchResultItem] = []
        search_domain = "lite.duckduckgo.com"

        try:
            SSRFGuard.validate_url(f"https://{search_domain}")
            headers = {"User-Agent": self.fetcher.USER_AGENT}
            q_param = f"{clean_q} site:{domain_filter}" if domain_filter else clean_q

            with httpx.Client(timeout=4.0, headers=headers) as client:
                resp = client.post(
                    f"https://{search_domain}/lite/",
                    data={"q": q_param},
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, "html.parser")
                    # Parse result links from DuckDuckGo Lite
                    links = soup.find_all("a", class_="result-link")
                    snippets = soup.find_all("td", class_="result-snippet")

                    for idx, link in enumerate(links[:max_results * 2]):
                        raw_url = link.get("href", "")
                        title = link.get_text().strip()
                        snippet = snippets[idx].get_text().strip() if idx < len(snippets) else ""

                        if not raw_url.startswith("http"):
                            continue

                        try:
                            # Verify URL passes SSRF checks
                            valid_url, hostname, _ = SSRFGuard.validate_url(raw_url)
                            is_gov = self.fetcher.is_gov_domain(hostname)

                            results.append(
                                WebSearchResultItem(
                                    title=title or hostname,
                                    url=valid_url,
                                    snippet=snippet,
                                    domain=hostname,
                                    is_gov_domain=is_gov,
                                )
                            )
                        except SSRFSecurityError:
                            continue

                        if len(results) >= max_results:
                            break
        except Exception as e:
            logger.warning(f"Live web search failed: {e}")

        # Sort to prioritize official government domains first
        results.sort(key=lambda r: (not r.is_gov_domain, r.domain))
        return results[:max_results]
