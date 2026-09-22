"""Controlled vocabularies for Uttarakhand records acquisition and governance."""

from enum import Enum
from typing import Optional, Set


class StrEnum(str, Enum):
    """String Enum base class for JSON and database compatibility."""
    def __str__(self) -> str:
        return str(self.value)


class DocType(StrEnum):
    """Controlled vocabulary for document types."""
    GO = "GO"
    RTI_MANUAL = "RTI_MANUAL"
    RULES = "RULES"
    ACT = "ACT"
    NOTIFICATION = "NOTIFICATION"
    CIRCULAR = "CIRCULAR"
    AUDIT_REPORT = "AUDIT_REPORT"
    GAZETTE = "GAZETTE"
    INTERNAL_RECORD = "INTERNAL_RECORD"
    DEPARTMENTAL_DOCUMENT = "DEPARTMENTAL_DOCUMENT"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def validate_or_preserve(cls, value: Optional[str]) -> str:
        if not value:
            return cls.UNKNOWN.value
        normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
        for item in cls:
            if item.value == normalized:
                return item.value
        # Preserve original value if not recognized to avoid inventing fake categories
        return value.strip()


class DepartmentId(StrEnum):
    """Controlled vocabulary for departments."""
    FINANCE_TREASURY = "FINANCE_TREASURY"
    RURAL_DEVELOPMENT = "RURAL_DEVELOPMENT"
    AUDIT_DIRECTORATE = "AUDIT_DIRECTORATE"
    BOARD_OF_REVENUE = "BOARD_OF_REVENUE"
    OPEN_GOVERNMENT_DATA = "OPEN_GOVERNMENT_DATA"
    GENERAL_ADMINISTRATION = "GENERAL_ADMINISTRATION"
    LEGAL_AFFAIRS = "LEGAL_AFFAIRS"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def validate_or_preserve(cls, value: Optional[str]) -> str:
        if not value:
            return cls.UNKNOWN.value
        normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
        for item in cls:
            if item.value == normalized:
                return item.value
        return value.strip()


class Classification(StrEnum):
    """Controlled vocabulary for document classification and access security."""
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._value2member_map_


class AuthorityLevel(StrEnum):
    """Controlled vocabulary for legal authority level."""
    STATE_CABINET = "STATE_CABINET"
    DEPARTMENTAL_SECRETARY = "DEPARTMENTAL_SECRETARY"
    HEAD_OF_DEPARTMENT = "HEAD_OF_DEPARTMENT"
    DIRECTORATE = "DIRECTORATE"
    DISTRICT_MAGISTRATE = "DISTRICT_MAGISTRATE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def validate_or_preserve(cls, value: Optional[str]) -> str:
        if not value:
            return cls.UNKNOWN.value
        normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
        for item in cls:
            if item.value == normalized:
                return item.value
        return value.strip()


class LifecycleStatus(StrEnum):
    """Controlled vocabulary for document lifecycle status."""
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REPEALED = "REPEALED"
    QUARANTINED = "QUARANTINED"
    ARCHIVED = "ARCHIVED"


class ProvenanceStatus(StrEnum):
    """Controlled vocabulary for provenance verification status."""
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    QUARANTINED = "QUARANTINED"
    FAILED_VALIDATION = "FAILED_VALIDATION"


class SourceStatus(StrEnum):
    """Controlled vocabulary for source connector governance status."""
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"


class RefreshCadence(StrEnum):
    """Controlled vocabulary for source crawl frequency."""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    MANUAL = "MANUAL"


class AccessAction(StrEnum):
    """Controlled vocabulary for access actions."""
    READ = "READ"
    EXPORT = "EXPORT"
    ADMIN = "ADMIN"


class ReviewStatus(StrEnum):
    """Controlled vocabulary for page-level human QA review status."""
    PENDING = "PENDING"
    AUTO_APPROVED = "AUTO_APPROVED"
    FLAGGED = "FLAGGED"
    REVIEWED = "REVIEWED"
    CORRECTED = "CORRECTED"


class ProcessingResult(StrEnum):
    """Controlled vocabulary for processing run outcomes."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


# ── Phase 04: Model & Agent Architecture Vocabularies ───────────────────────


class ModelStatus(StrEnum):
    """Lifecycle and governance status of a pinned model artifact."""
    REGISTERED = "REGISTERED"
    EVALUATED = "EVALUATED"
    PROMOTED = "PROMOTED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


class LicenseStatus(StrEnum):
    """License compliance and procurement review status."""
    APPROVED = "APPROVED"                  # e.g., Apache-2.0
    GATED_PENDING_REVIEW = "GATED_PENDING_REVIEW"  # e.g., Gemma Terms requiring legal review
    RESTRICTED = "RESTRICTED"              # e.g., Llama Community license
    REJECTED = "REJECTED"


class EnvironmentProfileType(StrEnum):
    """Target hardware and resource budget environments."""
    MACBOOK_AIR_8GB = "MACBOOK_AIR_8GB"
    DEV_SERVER = "DEV_SERVER"
    GOV_PRODUCTION = "GOV_PRODUCTION"


class AgentState(StrEnum):
    """Linear stages and problem-solving states for bounded agent orchestration state machine."""
    AUTHENTICATE = "AUTHENTICATE"
    CLASSIFY_REQUEST = "CLASSIFY_REQUEST"
    PLAN = "PLAN"
    RETRIEVE = "RETRIEVE"
    EXECUTE_STEP = "EXECUTE_STEP"
    VERIFY_INTERMEDIATE = "VERIFY_INTERMEDIATE"
    EVIDENCE_CURRENCY_CHECKS = "EVIDENCE_CURRENCY_CHECKS"
    GENERATE_OR_ABSTAIN = "GENERATE_OR_ABSTAIN"
    SYNTHESIZE = "SYNTHESIZE"
    VALIDATE_CITATIONS = "VALIDATE_CITATIONS"
    AUDIT = "AUDIT"
    COMPLETED = "COMPLETED"
    ABSTAINED = "ABSTAINED"
    FAILED = "FAILED"


class AgentToolName(StrEnum):
    """Whitelisted read-only and analytical tools available to the model agent."""
    SEARCH = "search"
    OPEN_CITED_SOURCE = "open_cited_source"
    LIST_AUTHORISED_COLLECTIONS = "list_authorised_collections"
    INSPECT_SYSTEM = "inspect_system"
    LOOKUP_PRECEDENTS = "lookup_precedents"
    EXECUTE_PYTHON_SANDBOX = "execute_python_sandbox"
    VERIFY_CLAIM = "verify_claim"
    DATABASE_QUERY = "database_query"
    COMPARE_SOURCES = "compare_sources"
    WEB_SEARCH = "web_search"
    FETCH_WEB_PAGE = "fetch_web_page"

