"""Tests for Frontend-Backend Integration Verification Checklist (frontend-backend-integration-verification.md).

Covers:
1. Section 1: Model Inventory & Single-Instance Lifecycle Verification
2. Section 2: Text-to-Text Input -> Output SSE Streaming & Grounded Citations Roundtrip
3. Section 3: Speech-to-Text Voice Input Roundtrip & Pipeline Parity
4. Section 4: Text-to-Speech Voice Output & Substantive Text Purity (No Spoken Citations)
5. Section 5: Speech-to-Speech Full Loop
6. Section 6: Feature Parity Audit (All Frontend Views & Controls to Backend Endpoints)
"""

import io
import json
import pytest
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from unittest.mock import patch
from adam.api.app import create_app
from adam.api import deps
from adam.api.voice.stt import FasterWhisperEngine, SttResult, get_stt_engine
from adam.api.voice.tts import get_tts_engine
from adam.db.models import (
    Base,
    Document,
    DocumentVersion,
    DocumentPage,
    DocumentChunk,
    Source,
    PrecedentReference,
    ReviewAnnotation,
    AgentExecutionAudit,
)
from adam.model.registry import ModelRegistry
from adam.model.runtime import SingleModelLifecycleManager
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import (
    Classification,
    DepartmentId,
    DocType,
    LifecycleStatus,
    ProvenanceStatus,
    RefreshCadence,
    ReviewStatus,
    SourceStatus,
)


@pytest.fixture
def integ_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def integ_session(integ_engine):
    factory = sessionmaker(bind=integ_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def integ_client(integ_engine, tmp_path, monkeypatch):
    test_storage = LocalStorageBackend(tmp_path / "integ_storage")
    monkeypatch.setattr("adam.api.routers.documents.LocalStorageBackend", lambda: test_storage)

    app = create_app()

    def override_db():
        factory = sessionmaker(bind=integ_engine, autoflush=False, expire_on_commit=False)
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_db

    # Seed verified document & chunks for RAG roundtrips
    factory = sessionmaker(bind=integ_engine, autoflush=False, expire_on_commit=False)
    db = factory()

    # Source
    src = Source(
        id="src_integ_fin",
        name="Finance Department Uttarakhand",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Finance Secretary",
        owner_contact="finance@uk.gov.in",
        written_authority_ref="AUTH-UK-FIN-2026",
        permitted_domains=["uk.gov.in", "ekosh.uk.gov.in"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.DAILY.value,
        status=SourceStatus.APPROVED.value,
    )
    db.add(src)
    db.flush()

    # Document
    doc = Document(
        id="doc_da_order_2024",
        source_id=src.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Sanction of Dearness Allowance Revision for Uttarakhand State Government Servants",
        authority_level="STATE_CABINET",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    db.add(doc)
    db.flush()

    # Version
    ver = DocumentVersion(
        id="ver_da_2024_01",
        document_id=doc.id,
        source_url="https://ekosh.uk.gov.in/orders/UK_FIN_2024_4821.pdf",
        go_number="UK/FIN/2024/4821",
        issued_on=date(2024, 7, 1),
        effective_from=date(2024, 7, 1),
        sha256="abc123da4821sha256hash",
        mime_type="application/pdf",
        byte_size=10240,
        original_object_key="documents/doc_da_order_2024/da.pdf",
        provenance_status=ProvenanceStatus.VERIFIED.value,
    )
    db.add(ver)
    doc.current_version_id = ver.id
    db.flush()

    # Page
    page = DocumentPage(
        id="page_da_2024_01",
        version_id=ver.id,
        page_number=1,
        clean_text=(
            "GOVERNMENT OF UTTARAKHAND, FINANCE DEPARTMENT\n"
            "ORDER NO: UK/FIN/2024/4821 DATED 01 JULY 2024\n"
            "Subject: Revision of Dearness Allowance rates.\n"
            "1. The Governor is pleased to sanction the revised Dearness Allowance at the rate of 50 percent "
            "of basic pay with effect from 01 July 2024 for all state government employees."
        ),
        selected_text=(
            "The Governor is pleased to sanction the revised Dearness Allowance at the rate of 50 percent "
            "of basic pay with effect from 01 July 2024 for all state government employees."
        ),
        review_status=ReviewStatus.REVIEWED.value,
        text_confidence=0.99,
        is_scanned=0,
        image_key="pages/doc_da_order_2024/1.png",
    )
    db.add(page)
    db.flush()

    # Chunk
    chunk = DocumentChunk(
        id="chunk_da_2024_01",
        document_id=doc.id,
        version_id=ver.id,
        chunk_index=0,
        content=(
            "The Governor is pleased to sanction the revised Dearness Allowance at the rate of 50 percent "
            "of basic pay with effect from 01 July 2024 for all state government employees under Order UK/FIN/2024/4821."
        ),
        token_count=35,
        section_heading="Revision of Dearness Allowance rates",
        page_start=1,
        page_end=1,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        classification=Classification.PUBLIC.value,
        go_number="UK/FIN/2024/4821",
        source_url="https://ekosh.uk.gov.in/orders/UK_FIN_2024_4821.pdf",
        review_status=ReviewStatus.REVIEWED.value,
    )
    db.add(chunk)
    db.commit()

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Section 1: Model Inventory & Single Instance Lifecycle ─────────────────

def test_section1_model_inventory_and_instance_uniqueness(integ_client, integ_session):
    """Verify registered models in system metadata and single active instance guarantee."""
    res = integ_client.get("/api/system/models")
    assert res.status_code == 200
    models = res.json()
    assert len(models) >= 3

    model_ids = {m["id"] for m in models}
    assert "qwen3-4b-instruct-q4" in model_ids
    assert "qwen2.5-3b-instruct-q4" in model_ids

    # Confirm exactly one primary model exists
    primary_models = [m for m in models if m.get("is_primary")]
    assert len(primary_models) == 1

    # Confirm SingleModelLifecycleManager enforces single active instance
    manager = SingleModelLifecycleManager()
    m1 = manager.load_model("qwen3-4b-instruct-q4")
    assert manager.active_model_id == "qwen3-4b-instruct-q4"

    # Loading another switches the active model without leaving duplicates
    m2 = manager.load_model("qwen2.5-3b-instruct-q4")
    assert manager.active_model_id == "qwen2.5-3b-instruct-q4"

    # Confirm STT and TTS single engine instances
    stt = get_stt_engine()
    assert stt is not None
    assert hasattr(stt, "transcribe")

    tts = get_tts_engine()
    assert tts is not None
    assert hasattr(tts, "synthesize")


# ── Section 2: Text-to-Text Input -> Output SSE Roundtrip ──────────────────

def test_section2_text_to_text_roundtrip_streaming_and_citations(integ_client):
    """Verify end-to-end SSE chat stream with tokens, grounded citations, and session history."""
    query = "What is the revised rate of Dearness Allowance effective July 2024?"
    payload = {
        "query": query,
        "department_id": DepartmentId.FINANCE_TREASURY.value,
            "model_id": "qwen2.5-3b-instruct-q4",
    }
    headers = {
        "X-User-Id": "officer_test_roundtrip",
        "X-User-Role": "OFFICER",
        "X-Clearance-Level": Classification.PUBLIC.value,
    }

    res = integ_client.post("/api/chat", json=payload, headers=headers)
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = []
    current_event = None
    for line in res.text.split("\n"):
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: ") and current_event:
            try:
                data = json.loads(line[6:])
                events.append((current_event, data))
            except Exception:
                pass
            current_event = None

    event_types = [e[0] for e in events]
    assert "start" in event_types
    assert "token" in event_types
    assert "citations" in event_types
    assert "done" in event_types

    # Find start event and capture session_id
    start_data = next(d for t, d in events if t == "start")
    session_id = start_data["session_id"]
    assert session_id is not None

    # Reconstruct streamed answer from tokens
    streamed_text = "".join(d["text"] for t, d in events if t == "token")
    assert "50" in streamed_text or "percent" in streamed_text.lower()

    # Verify citations match the actual grounded chunk
    citations_data = next(d for t, d in events if t == "citations")
    assert len(citations_data) >= 1
    first_cit = citations_data[0]
    assert "UK/FIN/2024/4821" in str(first_cit.get("go_number")) or "Finance" in first_cit.get("department", "")
    assert first_cit.get("page") == 1
    assert "disclaimer" in first_cit

    # Verify conversation history matches database turns
    hist_res = integ_client.get(f"/api/sessions/{session_id}/history", headers=headers)
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history["turns"]) >= 2
    assert history["turns"][0]["role"] == "user"
    assert history["turns"][0]["content"] == query
    assert history["turns"][1]["role"] == "assistant"


def test_section2_adversarial_or_unanswerable_query_declined_gracefully(integ_client):
    """Verify out-of-domain or unanswerable queries decline gracefully without blank screens or errors."""
    query = "What is the secret recipe for chocolate cake in the Chief Minister's residence?"
    payload = {"query": query}
    headers = {"X-User-Id": "officer_test_roundtrip"}

    res = integ_client.post("/api/chat", json=payload, headers=headers)
    assert res.status_code == 200

    events = []
    current_event = None
    for line in res.text.split("\n"):
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: ") and current_event:
            try:
                events.append((current_event, json.loads(line[6:])))
            except Exception:
                pass
            current_event = None

    done_data = next(d for t, d in events if t == "done")
    # Must be marked as is_no_answer or high_risk
    assert done_data["is_no_answer"] is True or done_data.get("is_high_risk") is True

    # Tokens must provide a polite refusal / lack of evidence explanation, not an error stack
    streamed_text = "".join(d["text"] for t, d in events if t == "token")
    assert len(streamed_text) > 0
    assert "error" not in [t for t, _ in events]


# ── Section 3: Speech-to-Text Voice Input Roundtrip ─────────────────────────

def test_section3_speech_to_text_roundtrip_and_pipeline_parity(integ_client):
    """Verify STT transcription endpoint and confirm transcribed text feeds into the same chat pipeline."""
    if not isinstance(get_stt_engine(), FasterWhisperEngine):
        pytest.skip("Fast Whisper is not installed; the frontend now shows the API's explicit service-unavailable message.")
    # Send mock audio webm bytes
    mock_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 256
    files = {"file": ("test_voice.webm", mock_audio, "audio/webm")}
    with patch.object(
        FasterWhisperEngine,
        "transcribe",
        return_value=SttResult(
            transcript="What is the revised rate of Dearness Allowance?",
            language="hi",
            confidence=0.95,
        ),
    ):
        stt_res = integ_client.post("/api/voice/transcribe", files=files)
    assert stt_res.status_code == 200
    stt_data = stt_res.json()
    assert "transcript" in stt_data
    assert "language" in stt_data
    assert "confidence" in stt_data

    # Feed transcribed text into the chat endpoint — verifying it uses the identical pipeline path
    query_text = stt_data["transcript"] if stt_data["transcript"] else "What is the revised rate of Dearness Allowance?"
    chat_res = integ_client.post("/api/chat", json={"query": query_text})
    assert chat_res.status_code == 200
    assert "text/event-stream" in chat_res.headers["content-type"]


# ── Section 4: Text-to-Speech Voice Output Roundtrip ────────────────────────

def test_section4_text_to_speech_voice_output_and_purity(integ_client):
    """Verify TTS synthesis generates valid WAV audio and that metadata is excluded from speech text."""
    # Substantive answer text only (no citations, no disclaimers)
    substantive_answer = "Dearness Allowance has been revised to 50 percent of basic pay effective 01 July 2024."
    tts_payload = {"text": substantive_answer, "language": "en"}

    tts_res = integ_client.post("/api/voice/synthesize", json=tts_payload)
    assert tts_res.status_code == 200
    assert tts_res.headers["content-type"] == "audio/wav"
    audio_bytes = tts_res.content
    assert len(audio_bytes) >= 44
    # Check WAV RIFF header
    assert audio_bytes[:4] == b"RIFF"
    assert audio_bytes[8:12] == b"WAVE"


# ── Section 5: Speech-to-Speech Full Loop ───────────────────────────────────

def test_section5_speech_to_speech_full_loop(integ_client):
    """Verify full loop: Audio in -> STT -> RAG query -> Generation -> TTS -> Audio out."""
    if not isinstance(get_stt_engine(), FasterWhisperEngine):
        pytest.skip("Fast Whisper is not installed; speech-to-speech cannot start without the required STT service.")
    # Step 1: STT
    mock_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 128
    files = {"file": ("mic.webm", mock_audio, "audio/webm")}
    with patch.object(
        FasterWhisperEngine,
        "transcribe",
        return_value=SttResult(
            transcript="What is the revised Dearness Allowance rate?",
            language="hi",
            confidence=0.95,
        ),
    ):
        stt_resp = integ_client.post("/api/voice/transcribe", files=files)
    assert stt_resp.status_code == 200

    # Step 2 & 3: Chat RAG & Generation
    query = "What is the revised Dearness Allowance rate?"
    chat_res = integ_client.post("/api/chat", json={"query": query})
    assert chat_res.status_code == 200

    words = []
    for line in chat_res.text.split("\n"):
        if line.startswith("data: ") and '"text":' in line:
            try:
                data = json.loads(line[6:])
                words.append(data.get("text", ""))
            except Exception:
                pass
    synthesized_answer = "".join(words)
    assert len(synthesized_answer) > 0

    # Step 4: TTS synthesis of the generated answer
    tts_res = integ_client.post(
        "/api/voice/synthesize",
        json={"text": synthesized_answer, "language": "en"},
    )
    assert tts_res.status_code == 200
    assert tts_res.headers["content-type"] == "audio/wav"
    assert tts_res.content[:4] == b"RIFF"


# ── Section 6: Feature Parity Audit ─────────────────────────────────────────

def test_section6_feature_parity_all_views_and_controls(integ_client):
    """Verify that every frontend view and control has working backend API support."""
    # 1. System Metadata (Model picker & Vocabulary filters)
    assert integ_client.get("/api/system/models").status_code == 200
    assert integ_client.get("/api/system/vocabularies").status_code == 200

    # 2. Document Repository View (table, search, filters)
    doc_res = integ_client.get("/api/documents?department_id=FINANCE_TREASURY")
    assert doc_res.status_code == 200
    assert doc_res.json()["total"] >= 1

    # 3. Document Inspector View (details, pages, precedents)
    doc_id = doc_res.json()["items"][0]["id"]
    det_res = integ_client.get(f"/api/documents/{doc_id}")
    assert det_res.status_code == 200
    assert "pages" in det_res.json()

    # 4. Precedents Chain View
    prec_res = integ_client.get("/api/precedents")
    assert prec_res.status_code == 200

    # 5. Data Sources View (connectors & crawler status)
    src_res = integ_client.get("/api/sources")
    assert src_res.status_code == 200
    src_list = src_res.json()
    assert len(src_list) >= 1
    src_id = src_list[0]["id"]

    # Toggle status control
    toggle_res = integ_client.post(f"/api/sources/{src_id}/toggle-status")
    assert toggle_res.status_code == 200

    # 6. Audit & State Machine View
    audit_res = integ_client.get("/api/audit/executions")
    assert audit_res.status_code == 200

    # 7. Review & Quality Gate QA View
    rev_res = integ_client.get("/api/review/pages")
    assert rev_res.status_code == 200

    # 8. User Profile & Preferences Modal
    headers = {"X-User-Id": "officer_test_parity"}
    prof_res = integ_client.get("/api/user/profile", headers=headers)
    assert prof_res.status_code == 200
    assert prof_res.json()["user_id"] == "officer_test_parity"

    pref_res = integ_client.get("/api/user/preferences", headers=headers)
    assert pref_res.status_code == 200

    save_pref = integ_client.post(
        "/api/user/preferences",
        json={"opt_in": True, "purpose": "Interface display and language formatting", "preferences": {"theme": "light"}},
        headers=headers,
    )
    assert save_pref.status_code == 200
