"""Document extraction pipeline coordinating text, OCR, blocks, quality gates, and precedent resolution.

Pipeline flow per the Phase 02 spec:
    original bytes → virus/type validation → born-digital extraction → page render/OCR
    → layout & language detection → normalized text + coordinates → human QA → immutable chunks
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from adam.config import COLLECTOR_VERSION
from adam.db.models import (
    Document,
    DocumentVersion,
    DocumentPage,
    DocumentAttribute,
    PrecedentReference,
    AuditEvent,
    TextBlock,
    ExtractedTable,
    ProcessingRun,
)
from adam.extract.metadata import AdministrativeMetadataExtractor
from adam.extract.pdf import PdfExtractor
from adam.extract.precedents import PrecedentCitationParser
from adam.extract.ocr import get_ocr_engine, OcrResult, BaseOcrEngine
from adam.extract.quality import PageQualityGate, determine_review_status
from adam.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def _compute_config_hash(ocr_engine_name: str, parser_version: str) -> str:
    """SHA-256 hash of processing configuration for reproducibility tracking."""
    config = json.dumps({
        "parser_version": parser_version,
        "ocr_engine": ocr_engine_name,
        "scanned_text_threshold": PdfExtractor.SCANNED_TEXT_THRESHOLD,
    }, sort_keys=True)
    return hashlib.sha256(config.encode()).hexdigest()


class DocumentExtractionPipeline:
    """Coordinates parsing of original document bytes into structured text,
    blocks with coordinates, OCR for scans, quality gates, and precedents."""

    def __init__(
        self,
        session: Session,
        storage: StorageBackend,
        ocr_engine: Optional[BaseOcrEngine] = None,
    ):
        self.session = session
        self.storage = storage
        self._ocr_engine = ocr_engine

    @property
    def ocr_engine(self) -> BaseOcrEngine:
        if self._ocr_engine is None:
            self._ocr_engine = get_ocr_engine()
        return self._ocr_engine

    def process_version(self, version_id: str, actor: str = "extractor") -> DocumentVersion:
        """Full Phase 02 extraction pipeline for a single document version.

        Steps:
        1. Fetch immutable bytes from storage
        2. Born-digital text extraction (PyMuPDF)
        3. Page image rendering for citation display
        4. OCR for scanned pages
        5. Block-level text extraction with bounding boxes
        6. Quality gate evaluation and review status
        7. Table extraction into dedicated model
        8. Administrative metadata extraction
        9. Precedent citation parsing and resolution
        10. ProcessingRun audit record
        """
        started_at = datetime.now(timezone.utc)

        version = self.session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not version:
            raise ValueError(f"DocumentVersion '{version_id}' not found.")

        doc = version.document
        data = self.storage.get(version.original_object_key)
        is_pdf = "pdf" in version.mime_type.lower() or data.startswith(b"%PDF-")

        # ── Step 1: Born-digital text extraction ──────────────────────────
        if is_pdf:
            pages = PdfExtractor.extract_pages(data)
            expected_page_count = PdfExtractor.get_page_count(data)
        else:
            pages = []
            expected_page_count = 0

        # Acceptance criterion 1: 100% pages accounted for
        if is_pdf and len(pages) != expected_page_count:
            logger.error(
                "Page count mismatch for version %s: extracted %d, expected %d",
                version_id, len(pages), expected_page_count,
            )
            raise ValueError(
                f"Page count mismatch: extracted {len(pages)}, "
                f"PDF has {expected_page_count} pages."
            )

        # ── Step 2: Clear previous records for idempotency ────────────────
        self.session.query(TextBlock).filter(
            TextBlock.page_id.in_(
                self.session.query(DocumentPage.id).filter(DocumentPage.version_id == version.id)
            )
        ).delete(synchronize_session="fetch")
        self.session.query(ExtractedTable).filter(
            ExtractedTable.page_id.in_(
                self.session.query(DocumentPage.id).filter(DocumentPage.version_id == version.id)
            )
        ).delete(synchronize_session="fetch")
        self.session.query(DocumentPage).filter(DocumentPage.version_id == version.id).delete()

        # OCR engine info for ProcessingRun
        ocr_engine = self.ocr_engine
        ocr_engine_name = type(ocr_engine).__name__
        ocr_available = ocr_engine.is_available() and ocr_engine_name != "NullOcrEngine"

        full_text_parts = []
        quality_summary = {"flagged_pages": 0, "auto_approved_pages": 0, "total_flags": 0}

        for p in pages:
            # ── Step 3: Page image rendering ──────────────────────────────
            image_key = None
            if is_pdf:
                try:
                    png_bytes = PdfExtractor.render_page_image(data, p.page_number, dpi=150)
                    image_storage_path = f"pages/{version.id}/page_{p.page_number:04d}.png"
                    storage_obj = self.storage.store(
                        key=image_storage_path,
                        data=png_bytes,
                    )
                    image_key = storage_obj.key
                except Exception as img_err:
                    logger.warning("Failed to render page %d image: %s", p.page_number, img_err)

            # ── Step 4: OCR for scanned pages ─────────────────────────────
            ocr_text = ""
            text_confidence = 1.0 if not p.is_scanned else 0.0

            if p.is_scanned and ocr_available and image_key:
                try:
                    img_data = self.storage.get(image_key)
                    languages = ["hin", "eng"] if p.detected_language in ("hi", "bilingual") else ["eng"]
                    ocr_result: OcrResult = ocr_engine.ocr_page_image(img_data, languages=languages)
                    ocr_text = ocr_result.text
                    text_confidence = ocr_result.confidence
                except Exception as ocr_err:
                    logger.warning("OCR failed for page %d: %s", p.page_number, ocr_err)

            # ── Step 5: Select best text ──────────────────────────────────
            if p.is_scanned and ocr_text:
                selected_text = ocr_text
            else:
                selected_text = p.clean_text

            # ── Step 6: Quality gate evaluation ───────────────────────────
            flags = PageQualityGate.evaluate(
                page_number=p.page_number,
                clean_text=p.clean_text,
                ocr_text=ocr_text if ocr_text else None,
                text_confidence=text_confidence,
                is_scanned=p.is_scanned,
                has_tables=bool(p.tables),
                detected_language=p.detected_language,
            )
            review_status = determine_review_status(flags)

            if review_status == "FLAGGED":
                quality_summary["flagged_pages"] += 1
            else:
                quality_summary["auto_approved_pages"] += 1
            quality_summary["total_flags"] += len(flags)

            # ── Step 7: Persist DocumentPage ──────────────────────────────
            doc_page = DocumentPage(
                version_id=version.id,
                page_number=p.page_number,
                clean_text=p.clean_text,
                raw_text=p.raw_text,
                is_scanned=1 if p.is_scanned else 0,
                scan_quality_score=p.scan_quality_score,
                detected_language=p.detected_language,
                tables_json=p.tables if p.tables else None,
                word_count=p.word_count,
                image_key=image_key,
                ocr_text=ocr_text,
                selected_text=selected_text,
                text_confidence=text_confidence,
                rotation=0,
                review_status=review_status,
            )
            self.session.add(doc_page)
            self.session.flush()  # ensure doc_page.id is available for child records

            # ── Step 8: Block-level extraction ────────────────────────────
            if is_pdf:
                try:
                    import fitz
                    pdf_doc = fitz.open(stream=data, filetype="pdf")
                    fitz_page = pdf_doc[p.page_number - 1]

                    from adam.extract.blocks import BlockExtractor
                    blocks = BlockExtractor.extract_blocks(fitz_page)
                    for blk in blocks:
                        text_block = TextBlock(
                            page_id=doc_page.id,
                            block_type=blk.block_type,
                            text=blk.text,
                            bbox=blk.bbox,
                            reading_order=blk.reading_order,
                            confidence=blk.confidence,
                        )
                        self.session.add(text_block)

                    pdf_doc.close()
                except Exception as blk_err:
                    logger.warning("Block extraction failed for page %d: %s", p.page_number, blk_err)

            # ── Step 9: Dedicated ExtractedTable records ──────────────────
            if p.tables:
                for tbl_data in p.tables:
                    # Store table data as CSV in storage
                    csv_key = None
                    try:
                        import csv
                        import io
                        buf = io.StringIO()
                        writer = csv.writer(buf)
                        if tbl_data.get("headers"):
                            writer.writerow(tbl_data["headers"])
                        for row in tbl_data.get("rows", []):
                            writer.writerow(row)
                        csv_bytes = buf.getvalue().encode("utf-8")
                        csv_path = f"tables/{version.id}/page_{p.page_number:04d}_tbl_{tbl_data.get('table_index', 0)}.csv"
                        csv_obj = self.storage.store(key=csv_path, data=csv_bytes)
                        csv_key = csv_obj.key
                    except Exception as tbl_err:
                        logger.warning("Table CSV storage failed: %s", tbl_err)

                    ext_table = ExtractedTable(
                        page_id=doc_page.id,
                        html_or_csv_key=csv_key,
                        bbox=tbl_data.get("bbox"),
                        extraction_method="PYMUPDF",
                        review_status="PENDING",
                        table_data_json=tbl_data,
                    )
                    self.session.add(ext_table)

            if selected_text:
                full_text_parts.append(selected_text)

        full_text = "\n\n".join(full_text_parts)

        # ── Step 10: Administrative metadata extraction ───────────────────
        meta = AdministrativeMetadataExtractor.extract(full_text)

        attr = self.session.query(DocumentAttribute).filter(
            DocumentAttribute.version_id == version.id
        ).first()
        if not attr:
            attr = DocumentAttribute(version_id=version.id)
            self.session.add(attr)

        attr.subject = meta.subject
        attr.issuing_authority_title = meta.issuing_authority_title
        attr.signatory_name = meta.signatory_name
        attr.order_number = meta.order_number or version.go_number
        attr.order_date = meta.order_date or version.issued_on
        attr.language_distribution = meta.language_distribution

        # Update document title and version metadata if found
        if meta.subject and (not doc.title or "untitled" in doc.title.lower() or doc.title.endswith(".pdf")):
            doc.title = meta.subject
        if meta.order_number and not version.go_number:
            version.go_number = meta.order_number
        if meta.order_date and not version.issued_on:
            version.issued_on = meta.order_date

        # ── Step 11: Precedent citation extraction and resolution ─────────
        citations = PrecedentCitationParser.extract_citations(full_text)
        self.session.query(PrecedentReference).filter(
            PrecedentReference.source_version_id == version.id
        ).delete()

        for cit in citations:
            target_doc_id = None
            if cit.cited_order_number:
                target_ver = (
                    self.session.query(DocumentVersion)
                    .filter(DocumentVersion.go_number == cit.cited_order_number)
                    .first()
                )
                if not target_ver:
                    target_attr = (
                        self.session.query(DocumentAttribute)
                        .filter(DocumentAttribute.order_number == cit.cited_order_number)
                        .first()
                    )
                    if target_attr:
                        target_ver = target_attr.version

                if target_ver and target_ver.document_id != doc.id:
                    target_doc_id = target_ver.document_id

            prec_ref = PrecedentReference(
                source_version_id=version.id,
                raw_citation_text=cit.raw_citation_text,
                cited_order_number=cit.cited_order_number,
                cited_date=cit.cited_date,
                cited_act_or_rule=cit.cited_act_or_rule,
                target_document_id=target_doc_id,
                relation_type=cit.relation_type,
            )
            self.session.add(prec_ref)

        # ── Step 12: Processing run audit ─────────────────────────────────
        completed_at = datetime.now(timezone.utc)
        has_failures = quality_summary["flagged_pages"] > 0
        run_result = "PARTIAL" if has_failures else "SUCCESS"
        if not pages:
            run_result = "FAILED"

        prun = ProcessingRun(
            version_id=version.id,
            parser_version=COLLECTOR_VERSION,
            ocr_engine=ocr_engine_name,
            model_version=None,
            config_hash=_compute_config_hash(ocr_engine_name, COLLECTOR_VERSION),
            started_at=started_at,
            completed_at=completed_at,
            result=run_result,
            details_json={
                "page_count": len(pages),
                "expected_page_count": expected_page_count,
                "total_words": sum(p.word_count for p in pages),
                "has_tables": any(len(p.tables) > 0 for p in pages),
                "has_scanned_pages": any(p.is_scanned for p in pages),
                "ocr_available": ocr_available,
                "precedent_count": len(citations),
                "subject": meta.subject,
                "quality": quality_summary,
            },
        )
        self.session.add(prun)

        # Audit event for backward compatibility
        audit = AuditEvent(
            entity_type="DOCUMENT_VERSION",
            entity_id=version.id,
            action="TEXT_EXTRACTION",
            actor=actor,
            details_json={
                "page_count": len(pages),
                "total_words": sum(p.word_count for p in pages),
                "has_tables": any(len(p.tables) > 0 for p in pages),
                "has_scanned_pages": any(p.is_scanned for p in pages),
                "precedent_count": len(citations),
                "subject": meta.subject,
                "processing_run_result": run_result,
            },
        )
        self.session.add(audit)
        self.session.commit()
        return version

    def process_all(self, source_id: Optional[str] = None, actor: str = "extractor") -> int:
        """Process all unextracted or pending versions."""
        query = self.session.query(DocumentVersion)
        if source_id:
            query = query.join(Document, DocumentVersion.document_id == Document.id).filter(
                Document.source_id == source_id
            )

        # Find versions that don't have pages yet
        versions = query.all()
        count = 0
        for ver in versions:
            if not ver.pages:
                try:
                    self.process_version(ver.id, actor=actor)
                    count += 1
                except Exception as e:
                    logger.error("Failed to process version %s: %s", ver.id, e)
        return count
