"""SQLAlchemy ORM models for Uttarakhand public records acquisition and governance."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    String,
    Text,
    BigInteger,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    event,
    select,
    desc,
)
from sqlalchemy.orm import relationship


try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy import JSON as Vector

from adam.db.session import Base
from adam.vocabularies import (
    DocType,
    DepartmentId,
    Classification,
    AuthorityLevel,
    LifecycleStatus,
    ProvenanceStatus,
    SourceStatus,
    RefreshCadence,
    ReviewStatus,
    ProcessingResult,
    ModelStatus,
    LicenseStatus,
    AgentState,
)


def _generate_id(prefix: str = "doc") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Phase 01: Multi-User Identity & Organization Models ─────────────────────



class User(Base):
    """User account record with server-side authentication credentials and clearance level."""
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("usr"))
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False, default="")
    department_id = Column(String(64), nullable=False, default=DepartmentId.UNKNOWN.value)
    clearance_level = Column(String(32), nullable=False, default=Classification.PUBLIC.value)
    roles_json = Column(JSON, nullable=False, default=lambda: ["PUBLIC"])
    is_active = Column(Boolean, nullable=False, default=True)
    is_superuser = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")

    @property
    def roles(self) -> List[str]:
        return self.roles_json or ["PUBLIC"]

    def to_user_context(self) -> Any:
        from adam.rag.models import UserContext
        from adam.auth.policy import get_role_policy
        policy = get_role_policy(self.roles)
        return UserContext(
            user_id=self.id,
            roles=self.roles,
            department_id=self.department_id,
            clearance_level=self.clearance_level,
            can_access_web=policy.can_access_web,
            allow_web_research=policy.allow_web_research,
        )


class Organization(Base):
    """Multi-tenant organization boundary."""
    __tablename__ = "organizations"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("org"))
    name = Column(String(255), nullable=False)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")


class Membership(Base):
    """User membership and role assignment within an organization."""
    __tablename__ = "memberships"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("mem"))
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(64), nullable=False, default="OFFICER")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")


class ApiKey(Base):
    """Machine-to-machine API key credential."""
    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("apk"))
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False, default="Default API Key")
    roles_json = Column(JSON, nullable=False, default=lambda: ["PUBLIC"])
    clearance_level = Column(String(32), nullable=False, default=Classification.PUBLIC.value)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    user = relationship("User", back_populates="api_keys")


class Source(Base):
    """Source onboarding registry and governance specification."""
    __tablename__ = "sources"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("src"))
    name = Column(String(255), nullable=False)
    department_id = Column(String(64), nullable=False, default=DepartmentId.UNKNOWN.value)
    owner_name = Column(String(255), nullable=False)
    owner_contact = Column(String(255), nullable=False)
    written_authority_ref = Column(String(255), nullable=False)
    permitted_domains = Column(JSON, nullable=False, default=list)
    permitted_path_prefixes = Column(JSON, nullable=False, default=list)
    access_classification = Column(String(32), nullable=False, default=Classification.PUBLIC.value)
    refresh_cadence = Column(String(32), nullable=False, default=RefreshCadence.WEEKLY.value)
    rate_limit_per_minute = Column(Integer, nullable=False, default=30)
    retention_policy = Column(String(64), nullable=False, default="PERMANENT")
    status = Column(String(32), nullable=False, default=SourceStatus.PENDING_APPROVAL.value)
    source_type = Column(String(32), nullable=False, default="WEBSITE")  # WEBSITE, DATABASE, FILE_UPLOAD, CUSTOM
    config_json = Column(JSON, nullable=True)  # Connector configuration parameters
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    ingestion_runs = relationship("IngestionRun", back_populates="source", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="source")

    def is_active(self) -> bool:
        return self.status == SourceStatus.APPROVED.value


class Document(Base):
    """Logical document record."""
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("doc"))
    source_id = Column(String(64), ForeignKey("sources.id"), nullable=True)
    department_id = Column(String(64), nullable=False, default=DepartmentId.UNKNOWN.value)
    doc_type = Column(String(64), nullable=False, default=DocType.UNKNOWN.value)
    title = Column(Text, nullable=False)
    language = Column(String(16), nullable=False, default="hi")
    authority_level = Column(String(64), nullable=False, default=AuthorityLevel.UNKNOWN.value)
    classification = Column(String(32), nullable=False, default=Classification.PUBLIC.value)
    current_version_id = Column(String(64), nullable=True)
    lifecycle_status = Column(String(32), nullable=False, default=LifecycleStatus.ACTIVE.value)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    source = relationship("Source", back_populates="documents")
    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        primaryjoin="Document.id == DocumentVersion.document_id",
    )
    access_grants = relationship("AccessGrant", back_populates="document")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    """Immutable version of a document fetched from a source."""
    __tablename__ = "document_versions"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("ver"))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    source_url = Column(Text, nullable=False)
    source_locator = Column(Text, nullable=True)
    issued_on = Column(Date, nullable=True)
    published_on = Column(Date, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    go_number = Column(String(128), nullable=True)
    gazette_number = Column(String(128), nullable=True)
    supersedes_version_id = Column(String(64), ForeignKey("document_versions.id"), nullable=True)
    sha256 = Column(String(64), nullable=False, index=True)
    mime_type = Column(String(128), nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    provenance_status = Column(String(32), nullable=False, default=ProvenanceStatus.PENDING_VERIFICATION.value)
    license_id = Column(String(64), nullable=True)
    original_object_key = Column(Text, nullable=False)
    http_headers = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="versions")
    supersedes = relationship("DocumentVersion", remote_side=[id], uselist=False)
    pages = relationship("DocumentPage", back_populates="version", cascade="all, delete-orphan", order_by="DocumentPage.page_number")
    precedent_references = relationship(
        "PrecedentReference",
        primaryjoin="DocumentVersion.id == PrecedentReference.source_version_id",
        back_populates="source_version",
        cascade="all, delete-orphan",
    )
    attributes = relationship("DocumentAttribute", back_populates="version", uselist=False, cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="version", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index")

    __table_args__ = (
        Index("idx_doc_ver_sha256", "sha256"),
        Index("idx_doc_ver_source_url", "source_url"),
        Index("idx_doc_ver_document_id", "document_id"),
        Index("idx_doc_ver_retrieved_at", "retrieved_at"),
    )


class DocumentPage(Base):
    """Clean structured text, OCR output, scan metrics, and review status for a single document page."""
    __tablename__ = "document_pages"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("page"))
    version_id = Column(String(64), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)  # 1-indexed
    clean_text = Column(Text, nullable=False, default="")  # born-digital extracted text
    raw_text = Column(Text, nullable=False, default="")  # page-faithful original transcript
    is_scanned = Column(Integer, nullable=False, default=0)  # 0 or 1 for portable boolean
    scan_quality_score = Column(Integer, nullable=True)  # estimated DPI or quality index
    detected_language = Column(String(16), nullable=False, default="hi")  # 'hi', 'en', 'bilingual'
    tables_json = Column(JSON, nullable=True)  # extracted structured tables (legacy, kept for compatibility)
    word_count = Column(Integer, nullable=False, default=0)
    # Phase 02 additions
    image_key = Column(Text, nullable=True)  # storage key for rendered page image (PNG)
    ocr_text = Column(Text, nullable=False, default="")  # OCR-produced text (separate from born-digital)
    selected_text = Column(Text, nullable=False, default="")  # final best text: auto-selected or reviewer-corrected
    text_confidence = Column(Float, nullable=True)  # 0.0–1.0 confidence score
    rotation = Column(Integer, nullable=False, default=0)  # detected page rotation in degrees
    review_status = Column(String(32), nullable=False, default=ReviewStatus.PENDING.value)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    version = relationship("DocumentVersion", back_populates="pages")
    blocks = relationship("TextBlock", back_populates="page", cascade="all, delete-orphan", order_by="TextBlock.reading_order")
    extracted_tables = relationship("ExtractedTable", back_populates="page", cascade="all, delete-orphan")
    annotations = relationship("ReviewAnnotation", back_populates="page", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_page_ver_num", "version_id", "page_number"),
        Index("idx_page_version_id", "version_id"),
    )


class PrecedentReference(Base):
    """Precedent citation reference between orders, acts, and statutory rules."""
    __tablename__ = "precedent_references"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("prec"))
    source_version_id = Column(String(64), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    raw_citation_text = Column(Text, nullable=False)
    cited_order_number = Column(String(128), nullable=True, index=True)
    cited_date = Column(Date, nullable=True)
    cited_act_or_rule = Column(String(255), nullable=True)
    target_document_id = Column(String(64), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    relation_type = Column(String(64), nullable=False, default="REFERS_TO")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    source_version = relationship("DocumentVersion", back_populates="precedent_references")
    target_document = relationship("Document", foreign_keys=[target_document_id])

    __table_args__ = (
        Index("idx_prec_source_version", "source_version_id"),
    )


class DocumentAttribute(Base):
    """Structured administrative attributes for filtering and precedent navigation."""
    __tablename__ = "document_attributes"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("attr"))
    version_id = Column(String(64), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, unique=True)
    subject = Column(Text, nullable=True)  # विषय
    issuing_authority_title = Column(String(255), nullable=True)  # e.g. "अपर मुख्य सचिव", "Secretary"
    signatory_name = Column(String(255), nullable=True)
    department_hierarchy = Column(JSON, nullable=True)
    order_number = Column(String(128), nullable=True, index=True)
    order_date = Column(Date, nullable=True)
    language_distribution = Column(JSON, nullable=True)  # {"hi_pct": 80, "en_pct": 20}
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    version = relationship("DocumentVersion", back_populates="attributes")


class IngestionRun(Base):
    """Audit record of a collector execution run."""
    __tablename__ = "ingestion_runs"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("run"))
    source_id = Column(String(64), ForeignKey("sources.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    collector_version = Column(String(32), nullable=False)
    count_found = Column(Integer, nullable=False, default=0)
    count_downloaded = Column(Integer, nullable=False, default=0)
    failures_json = Column(JSON, nullable=True)

    source = relationship("Source", back_populates="ingestion_runs")


class AccessGrant(Base):
    """Access control list entry for documents and classifications."""
    __tablename__ = "access_grants"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("acl"))
    subject_id = Column(String(128), nullable=False)  # User ID or Role ID
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    classification = Column(String(32), nullable=True)
    action = Column(String(32), nullable=False)  # READ, EXPORT, ADMIN
    expires_at = Column(DateTime(timezone=True), nullable=True)
    granted_by = Column(String(128), nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    document = relationship("Document", back_populates="access_grants")


class AuditEvent(Base):
    """Cryptographically chained, tamper-evident immutable audit log for governance and ingestion actions."""
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("aud"))
    sequence_num = Column(BigInteger, nullable=False, default=0, index=True)
    entity_type = Column(String(32), nullable=False)  # SOURCE, DOCUMENT, INGESTION_RUN, ACL, SYSTEM, USER
    entity_id = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)  # ONBOARD, APPROVE, PAUSE, REMOVE, INGEST, QUARANTINE, LOGIN
    actor = Column(String(128), nullable=False)
    details_json = Column(JSON, nullable=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=False, default="")
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_audit_seq", "sequence_num"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_timestamp", "timestamp"),
    )


def compute_audit_event_hash(
    sequence_num: int,
    timestamp_iso: Any,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    details_json: Any,
    prev_hash: Optional[str],
) -> str:
    """Compute cryptographic SHA-256 fingerprint for tamper-evident audit chaining."""
    if hasattr(timestamp_iso, "tzinfo") and timestamp_iso.tzinfo is not None:
        ts_str = timestamp_iso.astimezone(timezone.utc).isoformat()
    elif hasattr(timestamp_iso, "isoformat"):
        ts_str = timestamp_iso.replace(tzinfo=timezone.utc).isoformat()
    else:
        ts_str = str(timestamp_iso).strip().replace(" ", "T")
        if not ts_str.endswith("+00:00") and not ts_str.endswith("Z"):
            ts_str += "+00:00"

    if isinstance(details_json, str):
        try:
            details_obj = json.loads(details_json)
        except Exception:
            details_obj = details_json
    else:
        details_obj = details_json or {}

    details_str = json.dumps(details_obj, sort_keys=True, ensure_ascii=False)
    payload = f"{sequence_num}|{ts_str}|{entity_type}|{entity_id}|{action}|{actor}|{details_str}|{prev_hash or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()




@event.listens_for(AuditEvent, "before_insert")
def _audit_event_before_insert(mapper, connection, target: AuditEvent):
    """Derive sequence number and link cryptographic hash chain before persistence."""
    stmt = (
        select(AuditEvent.sequence_num, AuditEvent.entry_hash)
        .order_by(desc(AuditEvent.sequence_num))
        .limit(1)
    )
    res = connection.execute(stmt).first()
    if res and res[0] is not None:
        target.sequence_num = res[0] + 1
        target.prev_hash = res[1] or ("0" * 64)
    else:
        target.sequence_num = 1
        target.prev_hash = "0" * 64

    if not target.timestamp:
        target.timestamp = _utc_now()

    ts_iso = target.timestamp.isoformat() if hasattr(target.timestamp, "isoformat") else str(target.timestamp)
    target.entry_hash = compute_audit_event_hash(
        sequence_num=target.sequence_num,
        timestamp_iso=ts_iso,
        entity_type=target.entity_type,
        entity_id=target.entity_id,
        action=target.action,
        actor=target.actor,
        details_json=target.details_json,
        prev_hash=target.prev_hash,
    )


@event.listens_for(AuditEvent, "before_update")
def _audit_event_before_update(mapper, connection, target):
    """Enforce append-only immutability. Revoke UPDATE capability at ORM layer."""
    raise RuntimeError("AuditEvent records are immutable and append-only. Updates are strictly forbidden.")


@event.listens_for(AuditEvent, "before_delete")
def _audit_event_before_delete(mapper, connection, target):
    """Enforce append-only immutability. Revoke DELETE capability at ORM layer."""
    raise RuntimeError("AuditEvent records are immutable and append-only. Deletions are strictly forbidden.")



# ── Phase 02: Document Processing & OCR Models ──────────────────────────────


class TextBlock(Base):
    """Block-level text with bounding boxes for citation coordinate resolution."""
    __tablename__ = "text_blocks"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("blk"))
    page_id = Column(String(64), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)
    block_type = Column(String(32), nullable=False, default="PARAGRAPH")  # PARAGRAPH, HEADING, LIST_ITEM, IMAGE, TABLE, CAPTION, SEAL, SIGNATURE
    text = Column(Text, nullable=False, default="")
    bbox = Column(JSON, nullable=True)  # [x0, y0, x1, y1]
    reading_order = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=True, default=1.0)

    page = relationship("DocumentPage", back_populates="blocks")

    __table_args__ = (
        Index("idx_block_page", "page_id", "reading_order"),
    )


class ExtractedTable(Base):
    """Structured table extracted from a document page, stored as HTML/CSV in immutable storage."""
    __tablename__ = "extracted_tables"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("tbl"))
    page_id = Column(String(64), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)
    html_or_csv_key = Column(Text, nullable=True)  # storage key for serialized table content
    bbox = Column(JSON, nullable=True)  # [x0, y0, x1, y1]
    extraction_method = Column(String(32), nullable=False, default="PYMUPDF")  # PYMUPDF, PADDLEOCR, MANUAL
    review_status = Column(String(32), nullable=False, default=ReviewStatus.PENDING.value)
    table_data_json = Column(JSON, nullable=True)  # inline table data for quick access
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    page = relationship("DocumentPage", back_populates="extracted_tables")


class ProcessingRun(Base):
    """Audit record tracking a document processing/OCR execution."""
    __tablename__ = "processing_runs"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("prun"))
    version_id = Column(String(64), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    parser_version = Column(String(32), nullable=False)
    ocr_engine = Column(String(64), nullable=True)  # TESSERACT, PADDLEOCR, NONE
    model_version = Column(String(64), nullable=True)
    config_hash = Column(String(64), nullable=False)  # SHA-256 of processing config
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(String(32), nullable=False, default=ProcessingResult.SUCCESS.value)
    details_json = Column(JSON, nullable=True)

    version = relationship("DocumentVersion", backref="processing_runs")

    __table_args__ = (
        Index("idx_prun_version", "version_id"),
    )


class ReviewAnnotation(Base):
    """Versioned reviewer correction — never mutates original bytes or extracted text."""
    __tablename__ = "review_annotations"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("ann"))
    page_id = Column(String(64), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)
    reviewer = Column(String(128), nullable=False)
    corrected_text = Column(Text, nullable=False)
    annotation_type = Column(String(32), nullable=False, default="TEXT_CORRECTION")  # TEXT_CORRECTION, TABLE_CORRECTION, FLAG_RESOLUTION
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    page = relationship("DocumentPage", back_populates="annotations")
 
 
# ── Phase 03: Retrieval, RAG & Citation Models ──────────────────────────────
 
 
class DocumentChunk(Base):
    """Semantic chunk (order/section/paragraph) retaining provenance, coordinates, and metadata."""
    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("chk"))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(String(64), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    page_start = Column(Integer, nullable=False, default=1)
    page_end = Column(Integer, nullable=False, default=1)
    section_heading = Column(String(255), nullable=True)
    language = Column(String(16), nullable=False, default="hi")
    department_id = Column(String(64), nullable=False, default=DepartmentId.UNKNOWN.value)
    doc_type = Column(String(64), nullable=False, default=DocType.UNKNOWN.value)
    classification = Column(String(32), nullable=False, default=Classification.PUBLIC.value)
    authority = Column(String(255), nullable=True)
    order_date = Column(Date, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    go_number = Column(String(128), nullable=True, index=True)
    gazette_number = Column(String(128), nullable=True)
    source_url = Column(Text, nullable=True)
    sha256 = Column(String(64), nullable=True)
    review_status = Column(String(32), nullable=False, default=ReviewStatus.AUTO_APPROVED.value)
    block_ids_json = Column(JSON, nullable=True)
    bbox_list_json = Column(JSON, nullable=True)
    embedding = Column(Vector(128), nullable=True)
    embedding_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    document = relationship("Document", back_populates="chunks")
    version = relationship("DocumentVersion", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunk_version_idx", "version_id", "chunk_index"),
        Index("idx_chunk_document_id", "document_id"),
        Index("idx_chunk_dept_class", "department_id", "classification"),
        Index("idx_chunk_review_dept_class", "review_status", "department_id", "classification"),
        Index("idx_chunk_go_num", "go_number"),
        Index(
            "idx_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ── Phase 04: Model & Agent Architecture Models ─────────────────────────────


class ModelArtifactRecord(Base):
    """Pinned model release artifacts, quantization builds, checksums, and SBOM/license metadata."""
    __tablename__ = "model_artifacts"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("mdl"))
    name = Column(String(128), nullable=False)  # e.g. "Qwen/Qwen3-4B-Instruct"
    revision = Column(String(64), nullable=False)  # e.g. "v1.0.0"
    quantization = Column(String(32), nullable=False, default="Q4_K_M")
    model_format = Column(String(32), nullable=False, default="GGUF")
    checksum_sha256 = Column(String(64), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False, default=2850000000)
    license_id = Column(String(64), nullable=False)  # e.g. "Apache-2.0", "Gemma Terms"
    license_status = Column(String(32), nullable=False, default=LicenseStatus.APPROVED.value)
    context_window = Column(Integer, nullable=False, default=4096)
    serving_runtime = Column(String(64), nullable=False, default="llamacpp")
    prompt_template = Column(Text, nullable=False)
    is_primary = Column(Integer, nullable=False, default=0)
    is_fallback = Column(Integer, nullable=False, default=0)
    is_comparator = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default=ModelStatus.REGISTERED.value)
    sbom_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    promotions = relationship(
        "ModelPromotionRecord",
        back_populates="model",
        cascade="all, delete-orphan",
        order_by="ModelPromotionRecord.promoted_at.desc()",
    )

    __table_args__ = (
        Index("idx_model_name_rev", "name", "revision"),
        Index("idx_model_checksum", "checksum_sha256"),
    )


class ModelPromotionRecord(Base):
    """Audit record for formal governance promotion of a model after benchmark gate evaluation."""
    __tablename__ = "model_promotions"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("prom"))
    model_id = Column(String(64), ForeignKey("model_artifacts.id", ondelete="CASCADE"), nullable=False)
    promoted_by = Column(String(128), nullable=False)
    authority_order_ref = Column(String(255), nullable=False)
    gold_set_passed = Column(Integer, nullable=False, default=0)
    recall_at_10 = Column(Float, nullable=True)
    page_precision = Column(Float, nullable=True)
    no_answer_refusal_rate = Column(Float, nullable=True)
    acl_leak_count = Column(Integer, nullable=False, default=0)
    hindi_review_passed = Column(Integer, nullable=False, default=0)
    hindi_review_notes = Column(Text, nullable=True)
    latency_p95_ms = Column(Float, nullable=True)
    peak_memory_mb = Column(Float, nullable=True)
    unanswerable_abstention_rate = Column(Float, nullable=True)
    high_risk_compliance_rate = Column(Float, nullable=True)
    license_approved = Column(Integer, nullable=False, default=0)
    decision = Column(String(32), nullable=False, default="PROMOTED")  # PROMOTED, REJECTED, CONDITIONAL
    notes = Column(Text, nullable=True)
    promoted_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    model = relationship("ModelArtifactRecord", back_populates="promotions")

    __table_args__ = (
        Index("idx_prom_model", "model_id"),
        Index("idx_prom_date", "promoted_at"),
    )


class AgentExecutionAudit(Base):
    """Immutable audit record of bounded agent orchestration execution."""
    __tablename__ = "agent_execution_audits"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("agnt"))
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(128), nullable=False)
    user_role = Column(String(64), nullable=False, default="PUBLIC")
    department_id = Column(String(64), nullable=True)
    clearance_level = Column(String(32), nullable=False, default="PUBLIC")
    query_text = Column(Text, nullable=False)
    detected_intent = Column(String(64), nullable=True)
    model_id = Column(String(64), nullable=True)
    retrieval_pass_count = Column(Integer, nullable=False, default=0)
    answer_pass_count = Column(Integer, nullable=False, default=0)
    is_no_answer = Column(Integer, nullable=False, default=0)
    is_high_risk = Column(Integer, nullable=False, default=0)
    state_transitions_json = Column(JSON, nullable=False, default=list)
    tool_calls_json = Column(JSON, nullable=False, default=list)
    validation_passed = Column(Integer, nullable=False, default=1)
    validation_errors_json = Column(JSON, nullable=True)
    currency_banners_json = Column(JSON, nullable=True)
    latency_ms = Column(Float, nullable=False, default=0.0)
    memory_used_mb = Column(Float, nullable=False, default=0.0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    temperature_applied = Column(Float, nullable=False, default=0.0)
    redacted_audit_log = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_agent_session", "session_id"),
        Index("idx_agent_user", "user_id"),
        Index("idx_agent_date", "created_at"),
    )


# ── Phase 05: Conversation Memory Models ────────────────────────────────────


class ChatSession(Base):
    """User conversation session bounded by classification ceiling and TTL expiry."""
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("sess"))
    user_id = Column(String(128), nullable=False, index=True)
    classification_ceiling = Column(String(32), nullable=False, default=Classification.PUBLIC.value)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    turns = relationship("ChatTurn", back_populates="session", cascade="all, delete-orphan", order_by="ChatTurn.created_at")
    summary = relationship("SessionSummary", back_populates="session", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_chat_user_exp", "user_id", "expires_at"),
    )


class ChatTurn(Base):
    """Individual conversational interaction turn with encrypted content and retention schedule."""
    __tablename__ = "chat_turns"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("turn"))
    session_id = Column(String(64), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)  # user, assistant, system
    content_ciphertext = Column(Text, nullable=False)  # Encrypted at rest
    cited_chunk_ids = Column(JSON, nullable=True)  # List of cited chunk IDs
    retention_tag = Column(String(64), nullable=False, default="STANDARD")  # STANDARD, CLASSIFIED_PII_SHORT
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    session = relationship("ChatSession", back_populates="turns")

    __table_args__ = (
        Index("idx_turn_session_time", "session_id", "created_at"),
    )


class SessionSummary(Base):
    """Minimal, grounded per-session summary encrypted at rest with strict TTL."""
    __tablename__ = "session_summaries"

    session_id = Column(String(64), ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True)
    summary_ciphertext = Column(Text, nullable=False)  # Encrypted JSON representation of summary
    source_turn_ids = Column(JSON, nullable=False)  # Explicit list of turn IDs summarized
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    session = relationship("ChatSession", back_populates="summary")


class UserPreference(Base):
    """Persistent user preferences requiring explicit opt-in, purpose limitation, and user delete control."""
    __tablename__ = "user_preferences"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("pref"))
    user_id = Column(String(128), nullable=False, unique=True, index=True)
    opt_in = Column(Integer, nullable=False, default=0)  # 0 = not opted in, 1 = opted in
    purpose = Column(String(255), nullable=True)  # e.g., "UI display language and response formatting"
    preference_data_ciphertext = Column(Text, nullable=True)  # Encrypted preferences
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


# ── Phase 07: Backend & Gateway API Models ──────────────────────────────────


class AnswerReconstructionAudit(Base):
    """Provenance audit log enabling 100% reconstruction of answers without logging raw sensitive text."""
    __tablename__ = "answer_reconstruction_audits"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("recon"))
    request_hash = Column(String(64), nullable=False, index=True)  # SHA-256 of request query + user role
    trace_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    model_id = Column(String(64), nullable=False)
    model_revision = Column(String(64), nullable=True, default="1.0")
    prompt_version = Column(String(64), nullable=False, default="ADAM_OFFICER_PROMPT_V1")
    index_version_ids = Column(JSON, nullable=False, default=list)  # List of DocumentVersion IDs in evidence
    cited_chunk_ids = Column(JSON, nullable=False, default=list)    # List of chunk IDs cited in answer
    status = Column(String(32), nullable=False, default="answered")  # answered, abstained, needs_review
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_recon_trace", "trace_id"),
        Index("idx_recon_req_hash", "request_hash"),
    )


class FeedbackRecord(Base):
    """User feedback and correction signals stored strictly isolated from source documents."""
    __tablename__ = "feedback_records"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("fb"))
    trace_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)
    rating = Column(Integer, nullable=True)  # 1-5 scale
    feedback_type = Column(String(64), nullable=False, default="CORRECTION")  # CORRECTION, ACCURACY, etc.
    comment = Column(Text, nullable=True)
    correction_text = Column(Text, nullable=True)
    cited_chunk_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_feedback_trace", "trace_id"),
        Index("idx_feedback_user", "user_id"),
    )


class IdempotencyRecord(Base):
    """Idempotency cache ensuring write operations are safely repeatable without duplicate side effects."""
    __tablename__ = "idempotency_records"

    key = Column(String(128), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)
    endpoint = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class IngestionJob(Base):
    """Asynchronous and transactional ingestion run record ensuring retry-safe indexing."""
    __tablename__ = "ingestion_jobs"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("ingest"))
    source_id = Column(String(64), ForeignKey("sources.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="QUEUED")  # QUEUED, DISCOVERY, PROCESSING, DRAINING, PAUSED, CANCELLING, CANCELLED, COMPLETED, PARTIAL_SUCCESS, FAILED
    job_type = Column(String(32), nullable=False, default="FULL")  # FULL, INCREMENTAL, RETRY
    current_stage = Column(String(64), nullable=False, default="IDLE")
    idempotency_key = Column(String(128), nullable=True, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    collector_version = Column(String(32), nullable=False, default="v1.0.0")
    count_found = Column(Integer, nullable=False, default=0)
    count_ingested = Column(Integer, nullable=False, default=0)
    count_skipped = Column(Integer, nullable=False, default=0)
    count_failed = Column(Integer, nullable=False, default=0)
    progress_pct = Column(Float, nullable=False, default=0.0)
    checkpoint_json = Column(JSON, nullable=True)
    failures_json = Column(JSON, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    pause_requested = Column(Boolean, nullable=False, default=False)
    parent_job_id = Column(String(64), ForeignKey("ingestion_jobs.id"), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    source = relationship("Source")
    items = relationship("IngestionJobItem", back_populates="job", cascade="all, delete-orphan")


class IngestionJobItem(Base):
    """Normalized, item-level execution record within an ingestion job."""
    __tablename__ = "ingestion_job_items"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("item"))
    job_id = Column(String(64), ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    item_key = Column(String(512), nullable=False, index=True)
    title = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="PENDING", index=True)  # PENDING, PROCESSING, SUCCESS, SKIPPED, FAILED
    sha256 = Column(String(64), nullable=True, index=True)
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    version_id = Column(String(64), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    job = relationship("IngestionJob", back_populates="items")
    document = relationship("Document")
    version = relationship("DocumentVersion")


class RagTriadBenchmarkRecord(Base):
    """Sovereign RAG Triad benchmark evaluation record for continuous quality tracking."""
    __tablename__ = "rag_triad_benchmarks"

    id = Column(String(64), primary_key=True, default=lambda: _generate_id("triad"))
    model_id = Column(String(128), nullable=False, index=True)
    trigger_event = Column(String(64), nullable=False, default="MANUAL")  # MANUAL, POST_INGESTION, SCHEDULED
    total_queries = Column(Integer, nullable=False, default=0)
    passed_queries = Column(Integer, nullable=False, default=0)
    context_relevance = Column(Float, nullable=False, default=0.0)
    groundedness = Column(Float, nullable=False, default=0.0)
    answer_relevance = Column(Float, nullable=False, default=0.0)
    composite_score = Column(Float, nullable=False, default=0.0)
    zero_hallucination_rate = Column(Float, nullable=False, default=0.0)
    drift_detected = Column(Boolean, nullable=False, default=False)
    drift_notes_json = Column(JSON, nullable=True)
    department_scores_json = Column(JSON, nullable=True)
    language_scores_json = Column(JSON, nullable=True)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
