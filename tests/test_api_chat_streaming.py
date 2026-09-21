"""Tests for the ADAM FastAPI streaming chat endpoint (Phase 06)."""
import json
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import pytest
from fastapi.testclient import TestClient


# ── Minimal AgentResponse stub ───────────────────────────────────────────────

@dataclass
class _Stub_Citation:
    document_title: str = "Finance Circular 2024"
    department: str = "FINANCE_TREASURY"
    go_number: str = "GO/2024/101"
    issue_date: str = "2024-01-15"
    page: int = 1
    source_url: str = "https://example.gov.in/go/2024/101"
    pdf_page_link: str = "https://example.gov.in/go/2024/101/page/1"
    version_hash: str = "abc123"
    section: Optional[str] = None
    bbox: Optional[List[float]] = None
    currency_banner: Optional[str] = None
    disclaimer: str = "A citation is a source pointer, not a claim of legal validity."
    gazette_number: Optional[str] = None
    retrieval_timestamp: str = "2024-01-15T00:00:00Z"
    document_id: Optional[str] = None

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
        }


@dataclass
class _Stub_AgentResponse:
    session_id: str = "sess_test123"
    answer: str = "The Dearness Allowance rate is 46%."
    citations: List[_Stub_Citation] = field(default_factory=lambda: [_Stub_Citation()])
    currency_banners: List[str] = field(default_factory=list)
    search_suggestions: List[str] = field(default_factory=list)
    is_no_answer: bool = False
    is_high_risk: bool = False
    is_research_brief: bool = False
    validation_passed: bool = True
    validation_errors: List[str] = field(default_factory=list)
    state_history: List = field(default_factory=list)
    tool_calls: List = field(default_factory=list)
    retrieval_pass_count: int = 1
    answer_pass_count: int = 1
    latency_ms: float = 42.0
    prompt_tokens: int = 100
    completion_tokens: int = 50
    model_id: str = "qwen3-4b-instruct-q4"
    temperature_applied: float = 0.0
    applied_schema: str = "ADAM_AGENT_SCHEMA_V1"
    session_summary: Optional[Dict] = None


def _make_test_client():
    """Create FastAPI test client with mocked AgentStateMachine."""
    from adam.api.app import create_app
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_agent_run():
    """Patch AgentStateMachine.run to return stub response."""
    stub = _Stub_AgentResponse()
    with patch(
        "adam.api.routers.chat.AgentStateMachine",
    ) as MockClass:
        instance = MagicMock()
        instance.run.return_value = stub
        MockClass.return_value = instance
        yield stub, MockClass


@pytest.fixture()
def test_client():
    from adam.api.app import create_app
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_chat_endpoint_streams_sse(mock_agent_run, test_client):
    """SSE stream must emit: start, token(s), citations, done events in order."""
    stub_response, _ = mock_agent_run

    resp = test_client.post(
        "/api/chat",
        json={"query": "What is the Dearness Allowance rate?", "session_id": None},
        headers={"X-User-Id": "officer_1", "X-User-Role": "OFFICER", "X-Clearance-Level": "PUBLIC"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    body = resp.text
    # Must contain required SSE events
    assert "event: start" in body
    assert "event: token" in body
    assert "event: citations" in body
    assert "event: done" in body


def test_chat_endpoint_start_event_contains_session_id(mock_agent_run, test_client):
    """start event must contain session_id."""
    stub_response, _ = mock_agent_run

    resp = test_client.post(
        "/api/chat",
        json={"query": "DA rate?"},
        headers={"X-User-Id": "officer_1"},
    )
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    start_data = None
    for i, line in enumerate(lines):
        if line == "event: start":
            # next non-empty line is data:
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data:"):
                    start_data = json.loads(lines[j][len("data:"):].strip())
                    break
            break

    assert start_data is not None, "start event not found"
    assert "session_id" in start_data
    assert start_data["session_id"] == stub_response.session_id


def test_chat_endpoint_token_events_reconstruct_answer(mock_agent_run, test_client):
    """Concatenating all token events must reconstruct the original answer."""
    stub_response, _ = mock_agent_run

    resp = test_client.post(
        "/api/chat",
        json={"query": "DA rate?"},
        headers={"X-User-Id": "officer_1"},
    )
    assert resp.status_code == 200

    tokens = []
    lines = resp.text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i] == "event: token":
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data:"):
                    token_data = json.loads(lines[j][len("data:"):].strip())
                    tokens.append(token_data.get("text", ""))
                    break
        i += 1

    reconstructed = "".join(tokens).strip()
    assert reconstructed == stub_response.answer


def test_chat_endpoint_citations_event_is_valid_json(mock_agent_run, test_client):
    """citations SSE event must be a valid JSON array of citation objects."""
    stub_response, _ = mock_agent_run

    resp = test_client.post(
        "/api/chat",
        json={"query": "DA rate?"},
        headers={"X-User-Id": "officer_1"},
    )
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    for i, line in enumerate(lines):
        if line == "event: citations":
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data:"):
                    citations = json.loads(lines[j][len("data:"):].strip())
                    assert isinstance(citations, list)
                    assert len(citations) >= 1
                    assert "document_title" in citations[0]
                    assert "go_number" in citations[0]
                    return
    pytest.fail("citations event not found in SSE stream")


def test_chat_endpoint_done_event_contains_latency(mock_agent_run, test_client):
    """done event must contain latency_ms and validation_passed."""
    stub_response, _ = mock_agent_run

    resp = test_client.post(
        "/api/chat",
        json={"query": "DA rate?"},
        headers={"X-User-Id": "officer_1"},
    )
    assert resp.status_code == 200

    lines = resp.text.split("\n")
    for i, line in enumerate(lines):
        if line == "event: done":
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("data:"):
                    done_data = json.loads(lines[j][len("data:"):].strip())
                    assert "latency_ms" in done_data
                    assert "validation_passed" in done_data
                    assert done_data["validation_passed"] is True
                    return
    pytest.fail("done event not found in SSE stream")


def test_chat_endpoint_missing_query_returns_422(test_client):
    """Request with no query field must return HTTP 422 Unprocessable Entity."""
    resp = test_client.post(
        "/api/chat",
        json={},
        headers={"X-User-Id": "officer_1"},
    )
    assert resp.status_code == 422


def test_chat_endpoint_currency_banners_event(test_client):
    """When agent returns currency_banners, a banners SSE event must be present."""
    stub = _Stub_AgentResponse(
        currency_banners=["This GO has been amended. Applicable status not conclusively determined."]
    )
    with patch("adam.api.routers.chat.AgentStateMachine") as MockClass:
        instance = MagicMock()
        instance.run.return_value = stub
        MockClass.return_value = instance

        resp = test_client.post(
            "/api/chat",
            json={"query": "Treasury rules?"},
            headers={"X-User-Id": "officer_1"},
        )
        assert resp.status_code == 200
        assert "event: banners" in resp.text


def test_chat_endpoint_no_answer_refusal_reflected_in_done(test_client):
    """is_no_answer=True must be reflected in the done event."""
    stub = _Stub_AgentResponse(
        is_no_answer=True,
        answer="I could not establish this from the approved repository.",
        citations=[],
        search_suggestions=["Include the specific Department name."],
    )
    with patch("adam.api.routers.chat.AgentStateMachine") as MockClass:
        instance = MagicMock()
        instance.run.return_value = stub
        MockClass.return_value = instance

        resp = test_client.post(
            "/api/chat",
            json={"query": "Tell me about aliens"},
            headers={"X-User-Id": "officer_1"},
        )
        assert resp.status_code == 200
        lines = resp.text.split("\n")
        for i, line in enumerate(lines):
            if line == "event: done":
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("data:"):
                        done = json.loads(lines[j][len("data:"):].strip())
                        assert done["is_no_answer"] is True
                        return


def test_chat_endpoint_error_event_structured_ollama_offline(test_client):
    """When agent raises Ollama offline exception, structured error SSE event must be emitted."""
    with patch("adam.api.routers.chat.AgentStateMachine") as MockClass:
        instance = MagicMock()
        instance.run.side_effect = RuntimeError("Cannot connect to local Ollama service at http://localhost:11434. The Ollama server is offline.")
        MockClass.return_value = instance

        resp = test_client.post(
            "/api/chat",
            json={"query": "Test query"},
            headers={"X-User-Id": "officer_1"},
        )
        assert resp.status_code == 200
        assert "event: error" in resp.text
        lines = resp.text.split("\n")
        found = False
        for i, line in enumerate(lines):
            if line == "event: error":
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("data:"):
                        err_data = json.loads(lines[j][len("data:"):].strip())
                        assert err_data["category"] == "ollama_offline"
                        assert err_data["command_hint"] == "ollama serve"
                        assert err_data["suggested_action"] == "start_ollama"
                        assert "Ollama Service Offline" in err_data["title"]
                        found = True
                        break
        assert found is True


def test_chat_endpoint_error_event_structured_gemini_key_missing(test_client):
    """When agent raises Gemini key missing exception, structured error SSE event must be emitted."""
    with patch("adam.api.routers.chat.AgentStateMachine") as MockClass:
        instance = MagicMock()
        instance.run.side_effect = RuntimeError("Gemini API key is not configured.")
        MockClass.return_value = instance

        resp = test_client.post(
            "/api/chat",
            json={"query": "Test query"},
            headers={"X-User-Id": "officer_1"},
        )
        assert resp.status_code == 200
        assert "event: error" in resp.text
        lines = resp.text.split("\n")
        found = False
        for i, line in enumerate(lines):
            if line == "event: error":
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("data:"):
                        err_data = json.loads(lines[j][len("data:"):].strip())
                        assert err_data["category"] == "gemini_key_missing"
                        assert err_data["suggested_action"] == "configure_gemini"
                        assert "Key Required" in err_data["title"]
                        found = True
                        break
        assert found is True


def test_chat_endpoint_error_event_redacts_api_key(test_client):
    """Effective Gemini key must never leak into SSE error stream."""
    secret_key = "AIzaSySecretKeyXYZ12345"
    with patch("adam.api.routers.chat.AgentStateMachine") as MockClass:
        instance = MagicMock()
        instance.run.side_effect = RuntimeError(f"Failed call with key {secret_key}")
        MockClass.return_value = instance

        resp = test_client.post(
            "/api/chat",
            json={"query": "Test query", "api_key": secret_key},
            headers={"X-User-Id": "officer_1"},
        )
        assert resp.status_code == 200
        assert secret_key not in resp.text
        assert "[REDACTED_KEY]" in resp.text
