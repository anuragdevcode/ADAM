"""Connector Registry resolving source types and custom connectors dynamically."""

import logging
from typing import Dict, Type, Optional, Any

from adam.connectors.base import BaseConnector
from adam.connectors.database import DatabaseConnector
from adam.connectors.generic_web import GenericWebsiteConnector
from adam.connectors.file_batch import FileBatchConnector
from adam.db.models import Source

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Registry and factory for pluggable ingestion connectors."""

    _CUSTOM_CONNECTORS: Dict[str, Type[BaseConnector]] = {}

    @classmethod
    def register_connector(cls, type_name: str, connector_cls: Type[BaseConnector]) -> None:
        """Register a custom connector class for a source type or connector ID."""
        cls._CUSTOM_CONNECTORS[type_name.lower()] = connector_cls
        logger.info("Registered custom connector: '%s' -> %s", type_name, connector_cls.__name__)

    @classmethod
    def resolve_connector(
        cls,
        source: Source,
        in_memory_files: Optional[Any] = None,
    ) -> BaseConnector:
        """Resolve the appropriate connector instance for a given Source and context."""
        stype = (source.source_type or "WEBSITE").upper()
        cfg = source.config_json or {}

        # 1. Direct file upload override if in-memory files provided
        if in_memory_files:
            return FileBatchConnector(in_memory_files=in_memory_files)

        # 2. Custom registered connector
        connector_id = cfg.get("connector_id", "").lower()
        if connector_id and connector_id in cls._CUSTOM_CONNECTORS:
            return cls._CUSTOM_CONNECTORS[connector_id]()

        # 3. Source type mapping
        if stype == "DATABASE":
            return DatabaseConnector(config=cfg)

        if stype in ("FILE_UPLOAD", "LOCAL_BATCH"):
            batch_dir = cfg.get("batch_dir")
            return FileBatchConnector(batch_dir=batch_dir)

        # 4. Website / Portal connectors
        source_id_lower = (source.id or "").lower()
        domains = [d.lower() for d in (source.permitted_domains or [])]

        if "ukrd" in source_id_lower or any("ukrd" in d for d in domains):
            from adam.connectors.ukrd import UkrdConnector
            return UkrdConnector()

        if "gazette" in source_id_lower or any("gazette" in d for d in domains):
            from adam.connectors.egazette import EGazetteConnector
            return EGazetteConnector()

        if "ekosh" in source_id_lower or any("ekosh" in d for d in domains):
            from adam.connectors.ekosh import EkoshTreasuryConnector
            return EkoshTreasuryConnector()

        if "itda" in source_id_lower:
            from adam.connectors.itda import ITDASampleBatchConnector
            batch_dir = cfg.get("batch_dir", "/tmp/itda_samples")
            return ITDASampleBatchConnector(batch_dir=batch_dir)

        # 5. Default Generic Website Crawler
        return GenericWebsiteConnector(
            rate_limit_per_minute=source.rate_limit_per_minute or 30,
        )
