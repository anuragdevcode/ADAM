"""Semantic chunking preserving order/section/paragraph hierarchy, provisos, and schedules.

Per Phase 03 specification:
- Create chunks by semantic structure (order/section/paragraph)
- Retain version_id, page range, section heading, language, dates, authority, department, classification, and review status
- Aim for 350–700 tokens with 10–15% overlap
- Never split an operative clause from its proviso or schedule
- Consume approved page blocks only (review_status in AUTO_APPROVED, REVIEWED, CORRECTED)
"""

import math
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session

from adam.db.models import (
    Document,
    DocumentVersion,
    DocumentPage,
    DocumentChunk,
    TextBlock,
    ExtractedTable,
)
from adam.vocabularies import ReviewStatus, LifecycleStatus

# Regular expressions for detecting provisos and attached schedules
PROVISO_PATTERN = re.compile(
    r"(?:"
    r"\b(?:provided\s+that|provided\s+further\s+that|provided\s+always\s+that|"
    r"subject\s+to\s+the\s+proviso\s+that|subject\s+to\s+the\s+condition\s+that)\b"
    r"|"
    r"(?:परन्तु\s+यह\s+कि|परन्तु\s+यह\s+भी\s+कि|प्रतिबन्ध\s+यह\s+है\s+कि|बशर्ते\s+कि|शर्त\s+यह\s+है\s+कि)"
    r")",
    re.IGNORECASE | re.UNICODE,
)

SCHEDULE_PATTERN = re.compile(
    r"(?:"
    r"\b(?:schedule|annexure|appendix|enclosure)\s*([A-Za-z0-9\-–]+)?"
    r"|"
    r"(?:अनुसूची|परिशिष्ट|संलग्नक)\s*([A-Za-z0-9\u0966-\u096f\-–]+)?"
    r")",
    re.IGNORECASE | re.UNICODE,
)

SECTION_HEADING_PATTERN = re.compile(
    r"^(?:"
    r"(?:खण्ड|अध्याय|प्रस्तर|भाग|धारा|नियम|अनुसूची|परिशिष्ट)\s*[:\-]?\s*[0-9A-Za-z\u0966-\u096f\(\)\/\-\._]+"
    r"|"
    r"(?:Section|Chapter|Part|Clause|Rule|Schedule|Annexure|Appendix)\s*[:\-]?\s*[0-9A-Za-z\(\)\/\-\._]+"
    r"|"
    r"(?:शासनादेश|विषय|अधिसूचना|आदेश|Notification|Subject|Order)"
    r")",
    re.IGNORECASE | re.UNICODE,
)


def estimate_tokens(text: str) -> int:
    """Estimate token count for bilingual Hindi/English administrative text.

    Uses a hybrid metric: Devanagari and English word boundaries combined with
    character-length heuristics to accurately approximate standard BPE tokenization.
    """
    if not text:
        return 0
    words = text.split()
    char_len = len(text)
    # Average ~1.3 tokens per word in Hindi / English administrative text, bounded by char/4
    return max(int(len(words) * 1.25), char_len // 4, 1)


@dataclass
class SemanticUnit:
    """An atomic semantic unit (block or bound operative-clause+proviso)."""
    text: str
    block_type: str
    page_number: int
    block_ids: List[str] = field(default_factory=list)
    bboxes: List[List[float]] = field(default_factory=list)
    is_heading: bool = False
    is_proviso: bool = False
    is_schedule: bool = False
    heading_text: Optional[str] = None
    token_count: int = 0

    def __post_init__(self):
        if not self.token_count:
            self.token_count = estimate_tokens(self.text)


class SemanticChunker:
    """Chunks approved document blocks into semantic chunks obeying all Phase 03 criteria."""

    MIN_TOKENS: int = 350
    TARGET_TOKENS: int = 500
    MAX_TOKENS: int = 700
    HARD_CEILING_TOKENS: int = 900  # Allowed only when binding provisos/schedules to operative clauses
    OVERLAP_RATIO: float = 0.12     # 10–15% overlap

    @classmethod
    def is_proviso(cls, text: str) -> bool:
        """Check if text contains or begins with a proviso qualification."""
        return bool(PROVISO_PATTERN.search(text))

    @classmethod
    def is_schedule(cls, text: str) -> bool:
        """Check if text represents an attached statutory schedule or annexure."""
        return bool(SCHEDULE_PATTERN.search(text))

    @classmethod
    def is_heading(cls, block_type: str, text: str) -> bool:
        """Check if block is structurally or semantically a heading."""
        if block_type == "HEADING":
            return True
        first_line = text.strip().split("\n")[0] if text else ""
        if len(first_line) < 120 and SECTION_HEADING_PATTERN.match(first_line):
            return True
        return False

    @classmethod
    def build_atomic_units(cls, blocks: List[Dict[str, Any]]) -> List[SemanticUnit]:
        """Convert approved raw blocks into atomic units, binding provisos and schedules
        directly to their preceding operative clause so they are never split across chunks.
        """
        raw_units: List[SemanticUnit] = []
        current_heading: Optional[str] = None

        for b in blocks:
            text = (b.get("text") or "").strip()
            if not text:
                continue

            b_type = b.get("block_type", "PARAGRAPH")
            page_no = b.get("page_number", 1)
            b_id = b.get("block_id")
            bbox = b.get("bbox")

            is_hdg = cls.is_heading(b_type, text)
            if is_hdg:
                current_heading = text.split("\n")[0][:250]

            is_prov = cls.is_proviso(text)
            is_sched = cls.is_schedule(text)

            unit = SemanticUnit(
                text=text,
                block_type=b_type,
                page_number=page_no,
                block_ids=[b_id] if b_id else [],
                bboxes=[bbox] if bbox else [],
                is_heading=is_hdg,
                is_proviso=is_prov,
                is_schedule=is_sched,
                heading_text=current_heading,
            )
            raw_units.append(unit)

        if not raw_units:
            return []

        # Second pass: Bind provisos and schedules to preceding operative clauses
        # "never split an operative clause from its proviso or schedule."
        bound_units: List[SemanticUnit] = []
        i = 0
        while i < len(raw_units):
            curr = raw_units[i]

            # Look ahead to see if the next unit is a proviso or schedule attached to this operative clause
            combined_text = curr.text
            combined_block_ids = list(curr.block_ids)
            combined_bboxes = list(curr.bboxes)
            last_page = curr.page_number
            heading = curr.heading_text

            j = i + 1
            while j < len(raw_units):
                nxt = raw_units[j]
                # If next unit is an explicit proviso ("Provided that...", "परन्तु यह कि...")
                # or an attached schedule ("Schedule A...", "अनुसूची..."):
                if nxt.is_proviso or nxt.is_schedule:
                    combined_text += "\n\n" + nxt.text
                    combined_block_ids.extend(nxt.block_ids)
                    combined_bboxes.extend(nxt.bboxes)
                    last_page = nxt.page_number
                    j += 1
                else:
                    break

            if j > i + 1:
                # Proviso or schedule was bound to the operative clause
                bound_unit = SemanticUnit(
                    text=combined_text,
                    block_type=curr.block_type,
                    page_number=curr.page_number,
                    block_ids=combined_block_ids,
                    bboxes=combined_bboxes,
                    is_heading=curr.is_heading,
                    is_proviso=False,
                    is_schedule=False,
                    heading_text=heading,
                    token_count=estimate_tokens(combined_text),
                )
                bound_units.append(bound_unit)
                i = j
            else:
                bound_units.append(curr)
                i += 1

        return bound_units

    @classmethod
    def chunk_units(
        cls,
        units: List[SemanticUnit],
        metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Group semantic units into overlapping chunks (350–700 tokens, 10–15% overlap)."""
        if not units:
            return []

        chunks: List[Dict[str, Any]] = []
        current_chunk_units: List[SemanticUnit] = []
        current_token_count = 0
        chunk_index = 0

        for unit in units:
            unit_tokens = unit.token_count

            # Split on semantic structure boundaries (e.g. order/section/paragraph on a new page)
            is_new_section = (
                unit.is_heading
                and current_chunk_units
                and (
                    unit.page_number != current_chunk_units[0].page_number
                    or current_token_count >= cls.MIN_TOKENS
                )
            )

            # If adding unit would exceed MAX_TOKENS and current chunk already meets MIN_TOKENS, or at new section:
            if is_new_section or (
                current_token_count + unit_tokens > cls.MAX_TOKENS
                and current_token_count >= cls.MIN_TOKENS
            ):
                # Flush current chunk
                chunk_dict = cls._assemble_chunk(current_chunk_units, chunk_index, metadata)
                chunks.append(chunk_dict)
                chunk_index += 1

                if is_new_section:
                    current_chunk_units = []
                    current_token_count = 0
                else:
                    # Calculate overlap units (10–15% of target tokens ~ 40–80 tokens)
                    overlap_units: List[SemanticUnit] = []
                    overlap_tokens = 0
                    target_overlap = int(cls.TARGET_TOKENS * cls.OVERLAP_RATIO)

                    for u in reversed(current_chunk_units):
                        # Do not carry forward heading-only units as overlap
                        if u.is_heading:
                            continue
                        overlap_units.insert(0, u)
                        overlap_tokens += u.token_count
                        if overlap_tokens >= target_overlap:
                            break

                    current_chunk_units = list(overlap_units)
                    current_token_count = overlap_tokens

            # Append current unit to chunk
            current_chunk_units.append(unit)
            current_token_count += unit_tokens

        # Flush final chunk if any units remain
        if current_chunk_units:
            chunk_dict = cls._assemble_chunk(current_chunk_units, chunk_index, metadata)
            chunks.append(chunk_dict)

        return chunks

    @classmethod
    def _assemble_chunk(
        cls,
        units: List[SemanticUnit],
        chunk_index: int,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assemble a list of SemanticUnits into a complete chunk dictionary with all metadata."""
        texts = [u.text for u in units]
        content = "\n\n".join(texts).strip()
        token_count = estimate_tokens(content)

        pages = [u.page_number for u in units]
        page_start = min(pages) if pages else metadata.get("page_start", 1)
        page_end = max(pages) if pages else metadata.get("page_end", 1)

        # Determine dominant or latest section heading
        section_heading = None
        for u in units:
            if u.heading_text:
                section_heading = u.heading_text

        all_block_ids: List[str] = []
        all_bboxes: List[List[float]] = []
        for u in units:
            all_block_ids.extend(u.block_ids)
            all_bboxes.extend(u.bboxes)

        sec_heading = section_heading or metadata.get("subject")
        subj = metadata.get("subject") or ""
        embed_input = f"{sec_heading or ''} {subj} {content}".strip()
        from adam.rag.retriever import MultilingualSemanticVectorizer
        emb = MultilingualSemanticVectorizer.embed_text(embed_input)

        return {
            "document_id": metadata["document_id"],
            "version_id": metadata["version_id"],
            "chunk_index": chunk_index,
            "content": content,
            "token_count": token_count,
            "page_start": page_start,
            "page_end": page_end,
            "section_heading": sec_heading,
            "language": metadata.get("language", "hi"),
            "department_id": metadata.get("department_id", "UNKNOWN"),
            "doc_type": metadata.get("doc_type", "UNKNOWN"),
            "classification": metadata.get("classification", "PUBLIC"),
            "authority": metadata.get("authority"),
            "order_date": metadata.get("order_date"),
            "effective_from": metadata.get("effective_from"),
            "effective_to": metadata.get("effective_to"),
            "go_number": metadata.get("go_number"),
            "gazette_number": metadata.get("gazette_number"),
            "source_url": metadata.get("source_url"),
            "sha256": metadata.get("sha256"),
            "review_status": metadata.get("review_status", ReviewStatus.AUTO_APPROVED.value),
            "block_ids_json": list(dict.fromkeys(all_block_ids)),
            "bbox_list_json": all_bboxes[:20],  # bounded sample for citation highlight coordinates
            "embedding": emb,
            "embedding_json": emb,
        }


def chunk_document_version(session: Session, version_id: str) -> List[DocumentChunk]:
    """Extract approved blocks for a document version, apply semantic chunking,
    and persist immutable DocumentChunk records.
    """
    version = session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    if not version:
        raise ValueError(f"DocumentVersion '{version_id}' not found.")

    doc = version.document
    attr = version.attributes

    # Check approved pages
    approved_statuses = {
        ReviewStatus.AUTO_APPROVED.value,
        ReviewStatus.REVIEWED.value,
        ReviewStatus.CORRECTED.value,
    }

    # Fetch approved page blocks
    from adam.extract.blocks import get_approved_blocks
    blocks = get_approved_blocks(session, version_id=version_id)

    # If no structured blocks, fallback to approved page texts
    if not blocks:
        pages = (
            session.query(DocumentPage)
            .filter(
                DocumentPage.version_id == version_id,
                DocumentPage.review_status.in_(approved_statuses),
            )
            .order_by(DocumentPage.page_number)
            .all()
        )
        for p in pages:
            text = p.selected_text or p.clean_text or p.ocr_text
            if text:
                # Split page into logical paragraphs
                paragraphs = [par.strip() for par in text.split("\n\n") if par.strip()]
                for idx, par in enumerate(paragraphs):
                    blocks.append({
                        "block_id": f"fb_{p.id}_{idx}",
                        "page_number": p.page_number,
                        "block_type": "PARAGRAPH",
                        "text": par,
                        "bbox": None,
                    })

    if not blocks:
        return []

    # Build metadata dictionary
    metadata = {
        "document_id": doc.id,
        "version_id": version.id,
        "language": doc.language or "hi",
        "department_id": doc.department_id,
        "doc_type": doc.doc_type,
        "classification": doc.classification,
        "authority": attr.issuing_authority_title if attr else doc.authority_level,
        "order_date": attr.order_date if attr and attr.order_date else version.issued_on,
        "effective_from": version.effective_from,
        "effective_to": version.effective_to,
        "go_number": attr.order_number if attr and attr.order_number else version.go_number,
        "gazette_number": version.gazette_number,
        "source_url": version.source_url,
        "sha256": version.sha256,
        "subject": attr.subject if attr else doc.title,
        "review_status": ReviewStatus.AUTO_APPROVED.value,
    }

    # 1. Convert to atomic units with proviso and schedule binding
    atomic_units = SemanticChunker.build_atomic_units(blocks)

    # 2. Group into chunks
    chunk_dicts = SemanticChunker.chunk_units(atomic_units, metadata)

    # 3. Clear previous chunks for idempotency
    session.query(DocumentChunk).filter(DocumentChunk.version_id == version_id).delete()

    created_chunks: List[DocumentChunk] = []
    for cd in chunk_dicts:
        chunk = DocumentChunk(
            document_id=cd["document_id"],
            version_id=cd["version_id"],
            chunk_index=cd["chunk_index"],
            content=cd["content"],
            token_count=cd["token_count"],
            page_start=cd["page_start"],
            page_end=cd["page_end"],
            section_heading=cd["section_heading"],
            language=cd["language"],
            department_id=cd["department_id"],
            doc_type=cd["doc_type"],
            classification=cd["classification"],
            authority=cd["authority"],
            order_date=cd["order_date"],
            effective_from=cd["effective_from"],
            effective_to=cd["effective_to"],
            go_number=cd["go_number"],
            gazette_number=cd["gazette_number"],
            source_url=cd["source_url"],
            sha256=cd["sha256"],
            review_status=cd["review_status"],
            block_ids_json=cd["block_ids_json"],
            bbox_list_json=cd["bbox_list_json"],
            embedding=cd.get("embedding"),
            embedding_json=cd.get("embedding_json"),
        )
        session.add(chunk)
        created_chunks.append(chunk)

    session.commit()
    return created_chunks


def chunk_all_approved_versions(session: Session) -> int:
    """Chunk all document versions with approved pages that have not been chunked yet."""
    versions = (
        session.query(DocumentVersion)
        .join(Document, DocumentVersion.document_id == Document.id)
        .filter(Document.lifecycle_status == LifecycleStatus.ACTIVE.value)
        .all()
    )
    total_chunked = 0
    for ver in versions:
        # Check if version has approved pages
        has_approved_pages = any(
            p.review_status in (ReviewStatus.AUTO_APPROVED.value, ReviewStatus.REVIEWED.value, ReviewStatus.CORRECTED.value)
            for p in ver.pages
        )
        if has_approved_pages:
            chunks = chunk_document_version(session, ver.id)
            total_chunked += len(chunks)
    return total_chunked
