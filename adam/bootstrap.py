"""Anonymized mini public pilot corpus bootstrap engine.

Per Phase 08 specification:
- 'A fresh developer can bootstrap with an anonymised mini corpus and seeded evaluation set, never a production backup.'
- Completes in under 2 seconds on local SQLite.
- Seeds representative public pilot documents across 5 core Uttarakhand departments.
- Contains zero PII, zero classified records, and 100% verified administrative public schemas.
"""

import hashlib
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from adam.config import STORAGE_DIR
from adam.db.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentVersion,
    PrecedentReference,
    Source,
)
from adam.storage.base import get_storage_backend
from adam.storage.local import LocalStorageBackend
from adam.rag.retriever import MultilingualSemanticVectorizer
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProvenanceStatus,
    ReviewStatus,
    SourceStatus,
)

MINI_CORPUS_SPEC = [
    {
        "dept_id": DepartmentId.FINANCE_TREASURY.value,
        "source_name": "Uttarakhand Finance Department Orders",
        "doc_id": "doc_pilot_fin_da_2024",
        "title": "Revision of Dearness Allowance for State Employees (2024)",
        "go_number": "UK/FIN/2024/3401",
        "date": date(2024, 1, 15),
        "section": "Dearness Allowance Revision",
        "content": (
            "In continuation of earlier government orders, the Governor of Uttarakhand is pleased "
            "to revise the rate of Dearness Allowance payable to regular State Government employees "
            "from 46 percent to 50 percent of basic pay with effect from 1st January 2024. "
            "The arrears for January to March shall be credited to the General Provident Fund (GPF) account."
        ),
        "precedent": {
            "relation": "SUPERSEDES",
            "cited_order": "UK/FIN/2023/1102",
            "citation_text": "This order supersedes earlier Government Order No. UK/FIN/2023/1102 dated 15 July 2023.",
        },
    },
    {
        "dept_id": DepartmentId.BOARD_OF_REVENUE.value,
        "source_name": "Uttarakhand Revenue & Land Records Portal",
        "doc_id": "doc_pilot_rev_mutation_2023",
        "title": "Standard Operating Procedure for Online Land Mutation (Dakhil-Kharij)",
        "go_number": "UK/REV/2023/782",
        "date": date(2023, 9, 20),
        "section": "Time-Bound Mutation Disposal",
        "content": (
            "Under Section 34 of the Uttarakhand Land Revenue Act, all applications for undisputed "
            "succession (varasat) and registered sale deed mutation (dakhil-kharij) shall be disposed "
            "within 35 working days from receipt through the Bhulekh portal. No physical presence shall "
            "be mandatory for undisputed succession."
        ),
    },
    {
        "dept_id": DepartmentId.RURAL_DEVELOPMENT.value,
        "source_name": "Uttarakhand Rural Development Gazette",
        "doc_id": "doc_pilot_rd_mgnrega_2024",
        "title": "Revision of Wage Rates under Mahatma Gandhi NREGA for FY 2024-25",
        "go_number": "UK/RD/2024/920",
        "date": date(2024, 3, 28),
        "section": "MGNREGA Wage Revision",
        "content": (
            "The Governor of Uttarakhand is pleased to notify the revised wage rate of Rs. 237 "
            "per person-day for unskilled manual workers engaged under the Mahatma Gandhi National "
            "Rural Employment Guarantee Act (MGNREGA) in the State of Uttarakhand with effect from 1st April 2024."
        ),
    },
    {
        "dept_id": DepartmentId.GENERAL_ADMINISTRATION.value,
        "source_name": "Uttarakhand Secretariat General Administration",
        "doc_id": "doc_pilot_gad_hours_2024",
        "title": "Public Secretariat Working Hours and Holiday Schedule 2024",
        "go_number": "UK/GAD/2024/015",
        "date": date(2024, 1, 2),
        "section": "Secretariat Working Hours",
        "content": (
            "The official working hours for the Uttarakhand Civil Secretariat shall be from 9:30 AM to 5:30 PM "
            "with a half-hour lunch recess from 1:30 PM to 2:00 PM on all working days from Monday to Friday. "
            "The second and fourth Saturdays of every calendar month shall be observed as closed holidays."
        ),
    },
    {
        "dept_id": DepartmentId.AUDIT_DIRECTORATE.value,
        "source_name": "Uttarakhand Disaster Management & SDRF Authority",
        "doc_id": "doc_pilot_disaster_sdrf_2023",
        "title": "State Disaster Response Fund (SDRF) Assistance Norms and Relief Matrix",
        "go_number": "UK/USDMA/2023/512",
        "date": date(2023, 7, 10),
        "section": "Ex-Gratia Relief Norms",
        "content": (
            "Under the Disaster Management Act 2005, ex-gratia relief of Rs. 4,00,000 per deceased person "
            "shall be provided to the next of kin from the State Disaster Response Fund (SDRF) in cases of "
            "loss of life due to declared natural disasters including landslides, cloudbursts, and flash floods."
        ),
    },
]


def bootstrap_mini_corpus(
    session: Session,
    storage: Optional[LocalStorageBackend] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Seed the database with an anonymized mini public pilot corpus in under 2 seconds.

    Ensures zero production data or PII is used. Every document is PUBLIC.
    Idempotent: if records already exist and force is False, returns quickly.
    """
    start_time = time.perf_counter()
    storage = storage or get_storage_backend()

    # Check if already bootstrapped
    existing_count = session.query(Document).filter(Document.id.like("doc_pilot_%")).count()
    if existing_count >= len(MINI_CORPUS_SPEC) and not force:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "ALREADY_BOOTSTRAPPED",
            "documents_count": existing_count,
            "duration_ms": elapsed_ms,
            "message": "Mini pilot corpus is already seeded and ready.",
        }

    docs_created = 0
    chunks_created = 0

    for item in MINI_CORPUS_SPEC:
        # 1. Source
        src_id = f"src_{item['dept_id'].lower()}"
        src = session.query(Source).filter(Source.id == src_id).first()
        if not src:
            src = Source(
                id=src_id,
                name=item["source_name"],
                department_id=item["dept_id"],
                owner_name="Public Records Portal",
                owner_contact="records@uk.gov.in",
                written_authority_ref=f"AUTH/{item['dept_id']}/PILOT",
                permitted_domains=["uk.gov.in"],
                access_classification=Classification.PUBLIC.value,
                status=SourceStatus.APPROVED.value,
            )
            session.add(src)
            session.flush()

        # 2. Document
        doc = session.query(Document).filter(Document.id == item["doc_id"]).first()
        if not doc:
            doc = Document(
                id=item["doc_id"],
                source_id=src.id,
                title=item["title"],
                department_id=item["dept_id"],
                classification=Classification.PUBLIC.value,
                doc_type=DocType.GO.value,
                lifecycle_status=LifecycleStatus.ACTIVE.value,
            )
            session.add(doc)
            session.flush()
            docs_created += 1

        # 3. DocumentVersion
        ver_id = f"ver_{item['doc_id']}"
        ver = session.query(DocumentVersion).filter(DocumentVersion.id == ver_id).first()
        file_bytes = item["content"].encode("utf-8")
        sha256 = hashlib.sha256(file_bytes).hexdigest()
        storage_key = f"originals/{src_id}/{sha256}.pdf"

        # Store in storage backend
        storage.store(storage_key, file_bytes)

        if not ver:
            ver = DocumentVersion(
                id=ver_id,
                document_id=doc.id,
                source_url=f"https://uk.gov.in/orders/{item['go_number'].replace('/', '_')}.pdf",
                sha256=sha256,
                byte_size=len(file_bytes),
                mime_type="application/pdf",
                original_object_key=storage_key,
                go_number=item["go_number"],
                issued_on=item["date"],
                published_on=item["date"],
                provenance_status=ProvenanceStatus.VERIFIED.value,
            )
            session.add(ver)
            session.flush()

        # 4. DocumentPage
        page_id = f"page_{ver_id}_01"
        page = session.query(DocumentPage).filter(DocumentPage.id == page_id).first()
        img_key = f"pages/{ver_id}/p1.png"
        storage.store(img_key, b"\x89PNG\r\n\x1a\nSYNTHETIC_PAGE_IMAGE")

        if not page:
            page = DocumentPage(
                id=page_id,
                version_id=ver.id,
                page_number=1,
                image_key=img_key,
                clean_text=item["content"],
                selected_text=item["content"],
                word_count=len(item["content"].split()),
                review_status=ReviewStatus.AUTO_APPROVED.value,
                text_confidence=0.98,
            )
            session.add(page)
            session.flush()

        # 5. DocumentChunk
        chunk_id = f"chk_{item['doc_id']}_01"
        chunk = session.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
        if not chunk:
            chunk = DocumentChunk(
                id=chunk_id,
                document_id=doc.id,
                version_id=ver.id,
                chunk_index=0,
                content=item["content"],
                token_count=len(item["content"].split()) * 2,
                page_start=1,
                page_end=1,
                section_heading=item["section"],
                language="hi" if any("\u0900" <= c <= "\u097f" for c in item["content"]) else "en",
                department_id=item["dept_id"],
                doc_type=DocType.GO.value,
                classification=Classification.PUBLIC.value,
                order_date=item["date"],
                go_number=item["go_number"],
                source_url=ver.source_url,
                sha256=sha256,
                review_status=ReviewStatus.AUTO_APPROVED.value,
                embedding=MultilingualSemanticVectorizer.embed_text(f"{item['section']} {item['content']}"),
                embedding_json=MultilingualSemanticVectorizer.embed_text(f"{item['section']} {item['content']}"),
            )
            session.add(chunk)
            chunks_created += 1

        # 6. Precedent if present
        if "precedent" in item:
            prec_id = f"prec_{item['doc_id']}"
            prec = session.query(PrecedentReference).filter(PrecedentReference.id == prec_id).first()
            if not prec:
                prec = PrecedentReference(
                    id=prec_id,
                    source_version_id=ver.id,
                    raw_citation_text=item["precedent"]["citation_text"],
                    cited_order_number=item["precedent"]["cited_order"],
                    relation_type=item["precedent"]["relation"],
                )
                session.add(prec)

    session.commit()
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "status": "BOOTSTRAPPED_SUCCESS",
        "documents_created": docs_created,
        "chunks_created": chunks_created,
        "total_documents": len(MINI_CORPUS_SPEC),
        "duration_ms": elapsed_ms,
        "message": f"Successfully bootstrapped mini public pilot corpus in {elapsed_ms}ms.",
    }
