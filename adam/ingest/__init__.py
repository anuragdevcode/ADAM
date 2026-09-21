"""Ingestion engine and governance components."""

from adam.ingest.registry import SourceRegistry, SourceOnboardingSheet
from adam.ingest.crawler import UrlCrawlerGuard, CrawlerRateLimiter
from adam.ingest.validator import ContentValidator, ProvenanceGate
from adam.ingest.manifest import SignedInventory
from adam.ingest.pipeline import IngestionPipeline


def __getattr__(name: str):
    if name in ("IngestionControlPlane", "GLOBAL_INGESTION_CONTROL_PLANE"):
        from adam.ingest.control_plane import IngestionControlPlane, GLOBAL_INGESTION_CONTROL_PLANE
        if name == "IngestionControlPlane":
            return IngestionControlPlane
        return GLOBAL_INGESTION_CONTROL_PLANE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SourceRegistry",
    "SourceOnboardingSheet",
    "UrlCrawlerGuard",
    "CrawlerRateLimiter",
    "ContentValidator",
    "ProvenanceGate",
    "SignedInventory",
    "IngestionPipeline",
    "IngestionControlPlane",
    "GLOBAL_INGESTION_CONTROL_PLANE",
]

