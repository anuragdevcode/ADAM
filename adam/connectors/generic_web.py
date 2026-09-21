"""Generic Government Website and Portal Connector.

Crawls authorized web portals, sitemaps, and directory listings with strict domain allow-listing,
polite rate limiting, and recursive link extraction.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Iterator, Optional, Dict, Any, Tuple, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

from adam.config import DEFAULT_USER_AGENT, REQUEST_TIMEOUT_SECONDS
from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult, create_gov_http_client
from adam.db.models import Source
from adam.ingest.crawler import UrlCrawlerGuard, CrawlerRateLimiter
from adam.vocabularies import DocType, AuthorityLevel, Classification

logger = logging.getLogger(__name__)


class GenericWebsiteConnector(BaseConnector):
    """Acquires documents and web pages from authorized government portals."""

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        rate_limit_per_minute: int = 30,
        max_depth: int = 2,
    ):
        self.http_client = http_client
        self.rate_limiter = CrawlerRateLimiter(rate_limit_per_minute=rate_limit_per_minute)
        self.max_depth = max_depth
        self._discovery_completed_cleanly = False

    @property
    def supports_deletion_detection(self) -> bool:
        return self._discovery_completed_cleanly

    def _get_client(self) -> httpx.Client:
        if self.http_client:
            return self.http_client
        return create_gov_http_client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            user_agent=DEFAULT_USER_AGENT,
            follow_redirects=True,
        )

    def test_connection(self, source: Source) -> Tuple[bool, str]:
        """Test reachability of the permitted government domain(s)."""
        if not source.permitted_domains:
            return False, "No permitted domains configured for this source."

        domain = source.permitted_domains[0]
        test_url = f"https://{domain}"
        client = self._get_client()

        try:
            resp = client.get(test_url, timeout=10.0)
            if resp.status_code < 400 or resp.status_code in (401, 403):
                return True, f"Domain '{domain}' is reachable (HTTP {resp.status_code})."
            return False, f"Domain '{domain}' returned HTTP {resp.status_code}."
        except Exception as e:
            # Try HTTP fallback if HTTPS renegotiation failed
            try:
                resp = client.get(f"http://{domain}", timeout=10.0)
                if resp.status_code < 400:
                    return True, f"Domain '{domain}' is reachable via HTTP (HTTP {resp.status_code})."
            except Exception:
                pass
            return False, f"Failed to reach domain '{domain}': {str(e)}"

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        guard = UrlCrawlerGuard(
            permitted_domains=source.permitted_domains,
            permitted_path_prefixes=source.permitted_path_prefixes,
        )
        cfg = source.config_json or {}
        sitemap_url = cfg.get("sitemap_url")
        max_depth = int(cfg.get("max_depth", self.max_depth))

        seen_urls: Set[str] = set()
        client = self._get_client()

        try:
            # 1. Sitemap parsing if configured
            if sitemap_url:
                try:
                    self.rate_limiter.wait(sitemap_url)
                    resp = client.get(sitemap_url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for loc in soup.find_all("loc"):
                            url = loc.text.strip()
                            canonical = guard.normalize_url(url)
                            if canonical not in seen_urls and guard.is_url_allowed(canonical):
                                seen_urls.add(canonical)
                                yield self._build_item(canonical, source)
                except Exception as ex:
                    logger.warning("Sitemap crawl failed for %s: %s", sitemap_url, ex)

            # 2. Base paths crawl
            base_domains = source.permitted_domains or []
            prefixes = source.permitted_path_prefixes or ["/"]

            for domain in base_domains:
                for prefix in prefixes:
                    start_url = f"https://{domain}{prefix}"
                    if not guard.is_url_allowed(start_url):
                        continue

                    # Queue for BFS: (url, depth)
                    crawl_queue = [(start_url, 0)]
                    while crawl_queue:
                        curr_url, depth = crawl_queue.pop(0)
                        canonical_curr = guard.normalize_url(curr_url)
                        if canonical_curr in seen_urls:
                            continue
                        seen_urls.add(canonical_curr)

                        # Fetch index/page
                        try:
                            self.rate_limiter.wait(canonical_curr)
                            res = client.get(canonical_curr)
                            if res.status_code != 200:
                                continue

                            # Check if page itself is a document (PDF)
                            content_type = res.headers.get("content-type", "").lower()
                            if "pdf" in content_type or canonical_curr.lower().endswith(".pdf"):
                                yield self._build_item(canonical_curr, source)
                                continue

                            # Parse HTML links
                            soup = BeautifulSoup(res.text, "html.parser")
                            for a_tag in soup.find_all("a", href=True):
                                raw_href = a_tag["href"].strip()
                                if not raw_href or raw_href.startswith("#") or raw_href.startswith("javascript:"):
                                    continue

                                full_link = guard.normalize_url(urljoin(canonical_curr, raw_href))
                                if not guard.is_url_allowed(full_link) or full_link in seen_urls:
                                    continue

                                link_text = a_tag.get_text().strip() or "Untitled Document"
                                is_doc = full_link.lower().endswith((".pdf", ".doc", ".docx", ".xlsx"))

                                if is_doc:
                                    seen_urls.add(full_link)
                                    yield self._build_item(full_link, source, title=link_text)
                                elif depth < max_depth:
                                    crawl_queue.append((full_link, depth + 1))

                        except Exception as page_err:
                            logger.warning("Crawl error on %s: %s", canonical_curr, page_err)

            self._discovery_completed_cleanly = True

        except Exception as e:
            self._discovery_completed_cleanly = False
            logger.error("Generic website discovery terminated with error: %s", e)
            raise

    def _build_item(self, url: str, source: Source, title: Optional[str] = None) -> DiscoveredItem:
        if not title:
            parsed = urlparse(url)
            filename = parsed.path.rstrip("/").rsplit("/", 1)[-1]
            title = filename.replace("_", " ").replace("-", " ") if filename else source.name

        return DiscoveredItem(
            source_url=url,
            title=title,
            doc_type=DocType.GO.value,
            department_id=source.department_id,
            authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
            classification=source.access_classification or Classification.PUBLIC.value,
            metadata={"generic_web": True, "source_id": source.id},
        )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        client = self._get_client()
        self.rate_limiter.wait(item.source_url)
        resp = client.get(item.source_url)

        return FetchResult(
            source_url=item.source_url,
            data=resp.content,
            http_status=resp.status_code,
            http_headers=dict(resp.headers),
            retrieved_at=datetime.now(timezone.utc),
        )
