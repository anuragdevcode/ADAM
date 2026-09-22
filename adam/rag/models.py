"""RAG domain models, evidence structures, citation representations, and response schemas."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any

from adam.vocabularies import Classification, DepartmentId, DocType


@dataclass
class UserContext:
    """Authentication and access governance context of the querying actor."""
    user_id: str = "anonymous"
    roles: List[str] = field(default_factory=lambda: ["PUBLIC"])
    department_id: Optional[str] = None
    clearance_level: str = Classification.PUBLIC.value
    permissions: List[str] = field(default_factory=list)
    can_access_web: bool = False
    allow_web_research: bool = False

    def is_admin(self) -> bool:
        return "ADMIN" in [r.upper() for r in self.roles] or self.clearance_level == "ADMIN"


@dataclass
class ParsedQuery:
    """Structured understanding of an administrative query with explicit filters."""
    raw_query: str
    clean_query: str
    department_id: Optional[str] = None
    doc_type: Optional[str] = None
    go_number: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    exact_date: Optional[date] = None
    is_high_risk: bool = False
    high_risk_category: Optional[str] = None  # LEGAL_ADVICE, SANCTION_APPROVAL, ELIGIBILITY, DISCIPLINARY_ACTION
    detected_language: str = "en"  # "hi" or "en"
    is_out_of_jurisdiction: bool = False
    has_unsupported_topic: bool = False
    is_greeting: bool = False
    is_system_introspection: bool = False
    introspection_subtopic: Optional[str] = None  # MODEL, TOOLS, SOURCES, HARNESS, LAST_EXECUTION, CURRENT_STATUS, GENERAL


@dataclass
class EvidencePassage:
    """A high-quality retrieved passage included in the evidence packet."""
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    department_id: str
    doc_type: str
    page_start: int
    page_end: int
    section_heading: Optional[str]
    content: str
    score: float = 0.0
    bm25_score: float = 0.0
    vector_score: float = 0.0
    go_number: Optional[str] = None
    gazette_number: Optional[str] = None
    order_date: Optional[date] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    source_url: Optional[str] = None
    sha256: Optional[str] = None
    bbox_list: List[Any] = field(default_factory=list)
    is_amending: bool = False
    is_superseding: bool = False
    has_conflict: bool = False
    conflict_notes: Optional[str] = None
    currency_status: str = "CURRENT"  # CURRENT, AMENDED, SUPERSEDED, UNCERTAIN
    is_external: bool = False
    provenance_type: str = "INTERNAL_REPOSITORY"
    external_url: Optional[str] = None
    external_domain: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "title": self.title,
            "department_id": self.department_id,
            "doc_type": self.doc_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section_heading": self.section_heading,
            "content": self.content,
            "score": round(self.score, 4),
            "go_number": self.go_number,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "source_url": self.source_url,
            "currency_status": self.currency_status,
            "is_external": self.is_external,
            "provenance_type": self.provenance_type,
            "external_url": self.external_url,
            "external_domain": self.external_domain,
        }


@dataclass
class EvidencePacket:
    """The strict evidence packet (3–8 highest-quality passages) provided to the generator."""
    query: ParsedQuery
    passages: List[EvidencePassage] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    amendments: List[Dict[str, Any]] = field(default_factory=list)
    currency_status: str = "CURRENT"
    currency_banner: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return len(self.passages) == 0


@dataclass
class Citation:
    """Exact citation contract exposing document metadata, coordinates, and currency banner.

    Contract:
    'Each answer citation exposes document title, department, GO/gazette number if known,
    version/hash, issue date, page, section, source URL, retrieval timestamp and a link to
    the original PDF page. A citation is a source pointer, not a claim of legal validity.'
    """
    document_title: str
    department: str
    document_id: Optional[str] = None
    go_number: Optional[str] = None
    gazette_number: Optional[str] = None
    version_hash: str = ""
    issue_date: Optional[str] = None
    page: int = 1
    section: Optional[str] = None
    source_url: str = ""
    retrieval_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pdf_page_link: str = ""
    bbox: Optional[List[float]] = None
    currency_banner: Optional[str] = None
    disclaimer: str = "A citation is a source pointer, not a claim of legal validity."
    is_external: bool = False
    provenance_type: str = "INTERNAL_REPOSITORY"
    external_url: Optional[str] = None
    external_domain: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_title": self.document_title,
            "department": self.department,
            "document_id": self.document_id,
            "go_number": self.go_number,
            "gazette_number": self.gazette_number,
            "version_hash": self.version_hash,
            "issue_date": self.issue_date,
            "page": self.page,
            "section": self.section,
            "source_url": self.source_url,
            "retrieval_timestamp": self.retrieval_timestamp,
            "pdf_page_link": self.pdf_page_link,
            "bbox": self.bbox,
            "currency_banner": self.currency_banner,
            "disclaimer": self.disclaimer,
            "is_external": self.is_external,
            "provenance_type": self.provenance_type,
            "external_url": self.external_url,
            "external_domain": self.external_domain,
        }


@dataclass
class RagResponse:
    """Complete RAG response schema including answer, citations, banners, and audit diagnostics."""
    answer: str
    citations: List[Citation] = field(default_factory=list)
    evidence_packet: Optional[EvidencePacket] = None
    currency_banners: List[str] = field(default_factory=list)
    is_no_answer: bool = False
    is_high_risk: bool = False
    is_research_brief: bool = False
    validation_passed: bool = True
    validation_errors: List[str] = field(default_factory=list)
    search_suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "currency_banners": self.currency_banners,
            "is_no_answer": self.is_no_answer,
            "is_high_risk": self.is_high_risk,
            "is_research_brief": self.is_research_brief,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
            "search_suggestions": self.search_suggestions,
            "evidence_count": len(self.evidence_packet.passages) if self.evidence_packet else 0,
        }
