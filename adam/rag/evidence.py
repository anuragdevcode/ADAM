"""Evidence packet builder selecting 3–8 highest-quality passages with precedent and amendment resolution.

Per Phase 03 specification:
- '4. Build an evidence packet from 3–8 highest-quality passages, including conflicting/amending records.'
- 'For amendments/repeals, show a currency banner: "Applicable status not conclusively determined"
   unless the corpus has an approved relationship and effective-date record. Never infer supersession
   from similar language alone.'
"""

import re
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session

from adam.db.models import (
    Document,
    DocumentVersion,
    DocumentChunk,
    PrecedentReference,
)
from adam.rag.models import (
    ParsedQuery,
    EvidencePassage,
    EvidencePacket,
    UserContext,
)
from adam.vocabularies import ReviewStatus, LifecycleStatus


class EvidencePacketBuilder:
    """Builds a curated evidence packet of 3–8 passages including conflicting and amending records."""

    MIN_PASSAGES: int = 3
    MAX_PASSAGES: int = 8
    MIN_SCORE_THRESHOLD: float = 0.05  # Filter out irrelevant noise

    def __init__(self, session: Session, retrieval_settings=None):
        self.session = session
        # Apply RetrievalSettings overrides if provided (from AdvancedSettingsBundle)
        if retrieval_settings is not None:
            self._min_passages = getattr(retrieval_settings, "min_passages", self.MIN_PASSAGES)
            self._max_passages = getattr(retrieval_settings, "max_passages", self.MAX_PASSAGES)
            self._min_score_threshold = getattr(retrieval_settings, "min_score_threshold", self.MIN_SCORE_THRESHOLD)
        else:
            self._min_passages = self.MIN_PASSAGES
            self._max_passages = self.MAX_PASSAGES
            self._min_score_threshold = self.MIN_SCORE_THRESHOLD

    def build_packet(
        self,
        query: ParsedQuery,
        retrieved_passages: List[EvidencePassage],
        user_context: Optional[UserContext] = None,
    ) -> EvidencePacket:
        """Assemble the evidence packet from top passages and incorporate precedent relationships."""
        # 1. Filter out passages below minimum relevance threshold
        if not retrieved_passages:
            return EvidencePacket(query=query, passages=[])

        top_score = retrieved_passages[0].score if retrieved_passages else 0.0
        filtered = [
            p for p in retrieved_passages
            if p.score >= max(self._min_score_threshold, top_score * 0.40)
            or (query.go_number and p.go_number and query.go_number.lower() in p.go_number.lower())
        ]

        if not filtered:
            return EvidencePacket(query=query, passages=[])

        # 2. Select initial top passages (bounded by _max_passages)
        selected_passages: List[EvidencePassage] = filtered[: self._max_passages]
        seen_chunk_ids: Set[str] = {p.chunk_id for p in selected_passages}
        seen_doc_ids: Set[str] = {p.document_id for p in selected_passages}

        conflicts: List[Dict[str, Any]] = []
        amendments: List[Dict[str, Any]] = []
        seen_conflict_keys: Set[Tuple[str, Optional[str], str]] = set()
        seen_amend_keys: Set[Tuple[str, Optional[str], str]] = set()
        seen_currency_notes: Set[str] = set()
        has_unverified_supersession = False
        approved_currency_notes: List[str] = []

        # 3. Check precedent references (amendments, supersessions, continuations)
        for passage in list(selected_passages):
            # A. Incoming references: Documents that supersede or amend this document
            incoming_precedents = (
                self.session.query(PrecedentReference)
                .filter(
                    (PrecedentReference.target_document_id == passage.document_id)
                    | (
                        PrecedentReference.cited_order_number == passage.go_number
                        if passage.go_number
                        else False
                    )
                )
                .all()
            )

            for prec in incoming_precedents:
                if prec.relation_type in ("SUPERSEDES", "AMENDS"):
                    # Found a newer order amending/superseding this order
                    amending_version = prec.source_version
                    amending_doc = amending_version.document if amending_version else None

                    # Check if the corpus has an approved relationship and effective-date record
                    has_approved_rel = bool(
                        amending_version
                        and amending_doc
                        and amending_doc.lifecycle_status == LifecycleStatus.ACTIVE.value
                    )
                    has_effective_date = bool(
                        amending_version and amending_version.effective_from
                    )

                    if has_approved_rel and has_effective_date:
                        eff_date_str = amending_version.effective_from.isoformat()
                        go_str = amending_version.go_number or "Subsequent Order"
                        note = f"Approved amendment/supersession by GO {go_str} effective {eff_date_str}."
                        if note not in seen_currency_notes:
                            seen_currency_notes.add(note)
                            approved_currency_notes.append(note)
                        passage.currency_status = prec.relation_type
                    else:
                        # Missing approved relationship or effective date -> must flag currency uncertainty
                        has_unverified_supersession = True
                        passage.currency_status = "UNCERTAIN"

                    # Record amendment relationship (deduplicated)
                    amend_key = (passage.document_id, amending_doc.id if amending_doc else None, prec.relation_type)
                    if amend_key not in seen_amend_keys:
                        seen_amend_keys.add(amend_key)
                        amendments.append({
                            "original_doc_id": passage.document_id,
                            "original_go": passage.go_number,
                            "amending_doc_id": amending_doc.id if amending_doc else None,
                            "amending_go": amending_version.go_number if amending_version else None,
                            "relation_type": prec.relation_type,
                            "has_approved_rel": has_approved_rel,
                            "has_effective_date": has_effective_date,
                        })

                    # If space allows, include an amending chunk in the evidence packet
                    if len(selected_passages) < self.MAX_PASSAGES and amending_version:
                        amending_chunk = (
                            self.session.query(DocumentChunk)
                            .filter(
                                DocumentChunk.version_id == amending_version.id,
                                DocumentChunk.review_status.in_([
                                    ReviewStatus.AUTO_APPROVED.value,
                                    ReviewStatus.REVIEWED.value,
                                    ReviewStatus.CORRECTED.value,
                                ]),
                            )
                            .first()
                        )
                        if amending_chunk and amending_chunk.id not in seen_chunk_ids:
                            seen_chunk_ids.add(amending_chunk.id)
                            selected_passages.append(
                                EvidencePassage(
                                    chunk_id=amending_chunk.id,
                                    document_id=amending_chunk.document_id,
                                    version_id=amending_chunk.version_id,
                                    title=amending_doc.title if amending_doc else "Amending Order",
                                    department_id=amending_chunk.department_id,
                                    doc_type=amending_chunk.doc_type,
                                    page_start=amending_chunk.page_start,
                                    page_end=amending_chunk.page_end,
                                    section_heading=amending_chunk.section_heading,
                                    content=amending_chunk.content,
                                    score=passage.score * 0.95,
                                    go_number=amending_chunk.go_number,
                                    order_date=amending_chunk.order_date,
                                    effective_from=amending_chunk.effective_from,
                                    effective_to=amending_chunk.effective_to,
                                    source_url=amending_chunk.source_url,
                                    sha256=amending_chunk.sha256,
                                    is_amending=(prec.relation_type == "AMENDS"),
                                    is_superseding=(prec.relation_type == "SUPERSEDES"),
                                    currency_status="CURRENT",
                                )
                            )

            # B. Outgoing references: If this passage's version supersedes or amends an earlier document
            outgoing_precedents = (
                self.session.query(PrecedentReference)
                .filter(PrecedentReference.source_version_id == passage.version_id)
                .all()
            )
            for prec in outgoing_precedents:
                if prec.relation_type in ("SUPERSEDES", "AMENDS"):
                    passage.is_amending = (prec.relation_type == "AMENDS")
                    passage.is_superseding = (prec.relation_type == "SUPERSEDES")

                    # Record conflict / superseded relationship (deduplicated)
                    conflict_key = (passage.document_id, prec.cited_order_number, prec.relation_type)
                    if conflict_key not in seen_conflict_keys:
                        seen_conflict_keys.add(conflict_key)
                        conflicts.append({
                            "source_doc_id": passage.document_id,
                            "source_go": passage.go_number,
                            "cited_order": prec.cited_order_number,
                            "relation_type": prec.relation_type,
                            "notes": f"This order {prec.relation_type.lower()} prior order {prec.cited_order_number or 'N/A'}.",
                        })

        # 4. Currency banner calculation:
        # "For amendments/repeals, show a currency banner: 'Applicable status not conclusively determined'
        #  unless the corpus has an approved relationship and effective-date record. Never infer supersession
        #  from similar language alone."
        currency_banner = None
        overall_currency_status = "CURRENT"

        if has_unverified_supersession:
            currency_banner = "Applicable status not conclusively determined"
            overall_currency_status = "UNCERTAIN"
        elif approved_currency_notes:
            currency_banner = "; ".join(approved_currency_notes)
            overall_currency_status = "AMENDED"
        elif any(p.is_amending or p.is_superseding for p in selected_passages):
            overall_currency_status = "SUPERSEDING"

        # 5. Check numeric / rate conflicts between passages if multiple passages exist
        if len(selected_passages) >= 2:
            self._detect_content_conflicts(selected_passages, conflicts)

        return EvidencePacket(
            query=query,
            passages=selected_passages,
            conflicts=conflicts,
            amendments=amendments,
            currency_status=overall_currency_status,
            currency_banner=currency_banner,
        )

    @classmethod
    def _detect_content_conflicts(
        cls,
        passages: List[EvidencePassage],
        conflicts_list: List[Dict[str, Any]],
    ) -> None:
        """Analyze numeric rates and rules across passages from different documents for potential conflicts."""
        # Detect differing percentage or currency amounts between different orders
        seen_rates: Dict[str, Tuple[str, str]] = {}  # entity -> (order, value)

        rate_pattern = re.compile(
            r"(?:(\d+(?:\.\d+)?)\s*%\s*(?:da|dearness\s+allowance|महंगाई\s*भत्ता))|"
            r"(?:(?:da|dearness\s+allowance|महंगाई\s*भत्ता)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*%)",
            re.IGNORECASE,
        )

        seen_discrepancies: Set[Tuple[str, str, str, str]] = set()
        for p in passages:
            matches = rate_pattern.findall(p.content)
            for m in matches:
                val = m[0] or m[1]
                if val:
                    if "DA_RATE" in seen_rates:
                        prev_order, prev_val = seen_rates["DA_RATE"]
                        if prev_val != val and p.go_number != prev_order:
                            disc_key = (prev_order, prev_val, p.go_number or p.title, val)
                            if disc_key not in seen_discrepancies:
                                seen_discrepancies.add(disc_key)
                                conflicts_list.append({
                                    "conflict_type": "RATE_DISCREPANCY",
                                    "entity": "Dearness Allowance Rate",
                                    "first_order": prev_order,
                                    "first_val": f"{prev_val}%",
                                    "second_order": p.go_number or p.title,
                                    "second_val": f"{val}%",
                                    "notes": f"Discrepancy detected: {prev_order} states {prev_val}% while {p.go_number} states {val}%.",
                                })
                                p.has_conflict = True
                    else:
                        seen_rates["DA_RATE"] = (p.go_number or p.title, val)
