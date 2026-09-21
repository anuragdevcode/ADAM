"""Connector Registry resolving source types and custom connectors dynamically."""

import logging
from typing import Dict, Type, Optional, Any, List

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
    def get_official_presets(cls) -> List[Dict[str, Any]]:
        """Return catalog of pre-defined official Uttarakhand state connectors."""
        return [
            {
                "preset_id": "ekosh",
                "name": "Uttarakhand Treasury / IFMS (eKosh)",
                "connector_id": "ekosh",
                "connector_class": "EkoshTreasuryConnector",
                "source_type": "WEBSITE",
                "department_id": "FINANCE_TREASURY",
                "department_name": "Finance & Treasury",
                "permitted_domains": ["ekosh.uk.gov.in", "s3waas.gov.in"],
                "permitted_path_prefixes": ["/government-orders/", "/document-category/rti-documents-manuals/"],
                "base_url": "https://ekosh.uk.gov.in",
                "description": "Acquires official Treasury Government Orders, financial sanctions, and RTI manuals from IFMS Uttarakhand.",
                "rate_limit_per_minute": 30,
                "refresh_cadence": "WEEKLY",
                "access_classification": "PUBLIC",
            },
            {
                "preset_id": "ukrd",
                "name": "Rural Development Department (UKRD)",
                "connector_id": "ukrd",
                "connector_class": "UkrdConnector",
                "source_type": "WEBSITE",
                "department_id": "RURAL_DEVELOPMENT",
                "department_name": "Rural Development",
                "permitted_domains": ["ukrd.uk.gov.in", "s3waas.gov.in"],
                "permitted_path_prefixes": ["/documents/", "/"],
                "base_url": "https://ukrd.uk.gov.in",
                "description": "Acquires official rural development policies, poverty alleviation circulars, and departmental schemes.",
                "rate_limit_per_minute": 25,
                "refresh_cadence": "WEEKLY",
                "access_classification": "PUBLIC",
            },
            {
                "preset_id": "egazette",
                "name": "Uttarakhand State Official e-Gazette",
                "connector_id": "egazette",
                "connector_class": "EGazetteConnector",
                "source_type": "WEBSITE",
                "department_id": "GENERAL_ADMINISTRATION",
                "department_name": "General Administration",
                "permitted_domains": ["gazettes.uk.gov.in", "uk.gov.in", "s3waas.gov.in"],
                "permitted_path_prefixes": ["/pages/go%27s-and-gazettes", "/"],
                "base_url": "https://gazettes.uk.gov.in",
                "description": "Acquires official state gazettes, legislative notifications, and statutory service rules.",
                "rate_limit_per_minute": 25,
                "refresh_cadence": "WEEKLY",
                "access_classification": "PUBLIC",
            },
            {
                "preset_id": "itda",
                "name": "ITDA Curated Representative GO Batch",
                "connector_id": "itda",
                "connector_class": "ITDASampleBatchConnector",
                "source_type": "FILE_UPLOAD",
                "department_id": "FINANCE_TREASURY",
                "department_name": "Finance & Treasury",
                "permitted_domains": ["itda.uk.gov.in", "local.batch"],
                "permitted_path_prefixes": ["/"],
                "base_url": "local://itda_samples",
                "description": "ITDA-curated verified departmental GO batch with companion sidecar metadata JSONs.",
                "rate_limit_per_minute": 60,
                "refresh_cadence": "WEEKLY",
                "access_classification": "PUBLIC",
                "batch_dir": "/tmp/itda_samples",
            },
            {
                "preset_id": "audit",
                "name": "Uttarakhand Audit Directorate",
                "connector_id": "audit",
                "connector_class": "GenericWebsiteConnector",
                "source_type": "WEBSITE",
                "department_id": "AUDIT_DIRECTORATE",
                "department_name": "Audit Directorate",
                "permitted_domains": ["uttarakhandaudit.uk.gov.in"],
                "permitted_path_prefixes": ["/document-category/government-orders/"],
                "base_url": "https://uttarakhandaudit.uk.gov.in",
                "description": "Local Fund Audit Directorate notifications and compliance audits.",
                "rate_limit_per_minute": 20,
                "refresh_cadence": "WEEKLY",
                "access_classification": "PUBLIC",
            },
            {
                "preset_id": "bor",
                "name": "Board of Revenue Uttarakhand",
                "connector_id": "bor",
                "connector_class": "GenericWebsiteConnector",
                "source_type": "WEBSITE",
                "department_id": "BOARD_OF_REVENUE",
                "department_name": "Board of Revenue",
                "permitted_domains": ["bor.uk.gov.in"],
                "permitted_path_prefixes": ["/documents/"],
                "base_url": "https://bor.uk.gov.in",
                "description": "Revenue department land records, circle rates, and tenancy governance.",
                "rate_limit_per_minute": 20,
                "refresh_cadence": "WEEKLY",
                "access_classification": "PUBLIC",
            },
        ]

    @classmethod
    def resolve_connector(
        cls,
        source: Source,
        in_memory_files: Optional[Any] = None,
    ) -> BaseConnector:
        """Resolve the appropriate connector instance for a given Source and context."""
        stype = (source.source_type or "WEBSITE").upper()
        cfg = source.config_json or {}
        connector_id = (cfg.get("connector_id") or "").lower()
        source_id_lower = (source.id or "").lower()
        domains = [d.lower() for d in (source.permitted_domains or [])]

        # 1. Direct file upload override if in-memory files provided
        if in_memory_files:
            return FileBatchConnector(in_memory_files=in_memory_files)

        # 2. Custom registered connector
        if connector_id and connector_id in cls._CUSTOM_CONNECTORS:
            return cls._CUSTOM_CONNECTORS[connector_id]()

        # 3. Dedicated Uttarakhand State Connectors
        if connector_id in ("itda", "itda_samples") or stype == "ITDA" or "itda" in source_id_lower:
            from adam.connectors.itda import ITDASampleBatchConnector
            batch_dir = cfg.get("batch_dir", "/tmp/itda_samples")
            return ITDASampleBatchConnector(batch_dir=batch_dir)

        if connector_id in ("ekosh", "ekosh_treasury") or stype == "EKOSH" or "ekosh" in source_id_lower or any("ekosh" in d for d in domains):
            from adam.connectors.ekosh import EkoshTreasuryConnector
            return EkoshTreasuryConnector()

        if connector_id in ("ukrd", "rural_development") or stype == "UKRD" or "ukrd" in source_id_lower or any("ukrd" in d for d in domains):
            from adam.connectors.ukrd import UkrdConnector
            return UkrdConnector()

        if connector_id in ("egazette", "gazette") or stype in ("EGAZETTE", "GAZETTE") or "gazette" in source_id_lower or any("gazette" in d for d in domains):
            from adam.connectors.egazette import EGazetteConnector
            return EGazetteConnector()

        # 4. Relational Database Connector
        if stype == "DATABASE":
            return DatabaseConnector(config=cfg)

        # 5. Local directory / file batch connector
        if stype in ("FILE_UPLOAD", "LOCAL_BATCH"):
            batch_dir = cfg.get("batch_dir")
            return FileBatchConnector(batch_dir=batch_dir)

        # 6. Default Generic Website Crawler
        return GenericWebsiteConnector(
            rate_limit_per_minute=source.rate_limit_per_minute or 30,
        )
