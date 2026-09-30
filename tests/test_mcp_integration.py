"""Tests for Model Context Protocol (MCP) Standard Integration in ADAM."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from adam.api.app import app
from adam.api.deps import get_db
from adam.capabilities.mcp import AdamMcpServer, McpClientAdapter
from adam.capabilities.registry import CapabilityRegistry
from adam.db.models import Base, Document, DocumentVersion, Source
from adam.rag.models import UserContext
from adam.vocabularies import Classification, SourceStatus


@pytest.fixture
def mcp_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    source = Source(
        id="src_egazette",
        name="Official Uttarakhand Gazette",
        department_id="GENERAL_ADMINISTRATION",
        owner_name="General Administration Department",
        owner_contact="gad@uk.gov.in",
        written_authority_ref="AUTH-UK-GAD-01",
        status=SourceStatus.APPROVED.value,
        access_classification=Classification.PUBLIC.value,
    )
    doc = Document(
        id="doc_service_rules_2023",
        source_id="src_egazette",
        title="Uttarakhand Civil Services General Rules 2023",
        department_id="GENERAL_ADMINISTRATION",
        classification=Classification.PUBLIC.value,
        lifecycle_status="ACTIVE",
    )
    version = DocumentVersion(
        id="ver_gazette_1",
        document_id="doc_service_rules_2023",
        source_url="https://gazettes.uk.gov.in/rules_2023.pdf",
        sha256="gaz12345",
        mime_type="application/pdf",
        byte_size=2048,
        original_object_key="gazettes/rules_2023.pdf",
        retrieved_at=datetime.now(timezone.utc),
    )
    session.add_all([source, doc, version])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_mcp_server_tools_list():
    """Verify standard MCP tools/list JSON-RPC returns schema conforming to MCP specifications."""
    server = AdamMcpServer(registry=CapabilityRegistry)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    res = server.handle_json_rpc(
        request_payload={"jsonrpc": "2.0", "id": "req-1", "method": "tools/list", "params": {}},
        user_context=user,
    )
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == "req-1"
    tools = res["result"]["tools"]
    assert len(tools) >= 10

    # Verify MCP tool structure
    tool_names = {t["name"] for t in tools}
    assert "search" in tool_names
    assert "execute_python_sandbox" in tool_names

    sandbox_tool = next(t for t in tools if t["name"] == "execute_python_sandbox")
    assert "description" in sandbox_tool
    assert "inputSchema" in sandbox_tool
    assert "properties" in sandbox_tool["inputSchema"]


def test_mcp_server_tools_call(mcp_test_db):
    """Verify standard MCP tools/call JSON-RPC executes capability and returns McpCallToolResult."""
    server = AdamMcpServer(registry=CapabilityRegistry)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    # Call execute_python_sandbox via standard MCP tools/call
    res = server.handle_json_rpc(
        request_payload={
            "jsonrpc": "2.0",
            "id": "req-2",
            "method": "tools/call",
            "params": {
                "name": "execute_python_sandbox",
                "arguments": {"code": "x = 100\ny = 25\nresult = x / y"},
            },
        },
        user_context=user,
        db_session=mcp_test_db,
    )
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == "req-2"
    tool_res = res["result"]
    assert tool_res["isError"] is False
    assert len(tool_res["content"]) >= 1
    assert "4.0" in tool_res["content"][0]["text"]


def test_mcp_server_resources_list_and_read(mcp_test_db):
    """Verify standard MCP resources/list and resources/read return document URI and contents."""
    server = AdamMcpServer(registry=CapabilityRegistry)
    user = UserContext(clearance_level=Classification.PUBLIC.value)

    # 1. resources/list
    res_list = server.handle_json_rpc(
        request_payload={"jsonrpc": "2.0", "id": "req-3", "method": "resources/list"},
        user_context=user,
        db_session=mcp_test_db,
    )
    resources = res_list["result"]["resources"]
    uris = {r["uri"] for r in resources}
    assert "adam://system/self-model" in uris
    assert any("adam://collections/GENERAL_ADMINISTRATION" in u for u in uris)

    # 2. resources/read self-model
    res_read = server.handle_json_rpc(
        request_payload={
            "jsonrpc": "2.0",
            "id": "req-4",
            "method": "resources/read",
            "params": {"uri": "adam://system/self-model"},
        },
        user_context=user,
        db_session=mcp_test_db,
    )
    assert res_read["jsonrpc"] == "2.0"
    contents = res_read["result"]["contents"]
    assert len(contents) >= 1
    assert "ADAM" in contents[0]["text"]


def test_mcp_client_adapter_ssrf_and_air_gap():
    """Verify McpClientAdapter enforces SSRF validation and Air-Gapped Data Sovereignty."""
    # 1. Blocks loopback / private IP SSRF attempt
    adapter_bad = McpClientAdapter(
        endpoint_url="http://127.0.0.1:8000/mcp",
        server_name="malicious_local_server",
    )
    with pytest.raises(PermissionError) as exc_info:
        adapter_bad.list_remote_tools(user_context=UserContext())
    assert "SSRF" in str(exc_info.value) or "restricted" in str(exc_info.value)

    # 2. Air-gapped classified clearance blocks external server access
    adapter_gov = McpClientAdapter(
        endpoint_url="https://ekosh.uk.gov.in/mcp",
        server_name="state_statistics_service",
    )
    restricted_user = UserContext(clearance_level=Classification.RESTRICTED.value)
    with pytest.raises(PermissionError) as air_info:
        adapter_gov.list_remote_tools(user_context=restricted_user)
    assert "Air-Gapped Policy" in str(air_info.value)


def test_api_mcp_endpoints(mcp_test_db):
    """Test FastAPI MCP endpoints: /system/mcp/tools, /system/mcp/call, /system/mcp/resources."""
    app.dependency_overrides[get_db] = lambda: mcp_test_db
    client = TestClient(app)

    # 1. GET /api/system/mcp/tools
    resp_tools = client.get("/api/system/mcp/tools", headers={"X-Clearance-Level": "PUBLIC"})
    assert resp_tools.status_code == 200
    data_tools = resp_tools.json()
    assert "tools" in data_tools
    tool_names = {t["name"] for t in data_tools["tools"]}
    assert "execute_python_sandbox" in tool_names

    # 2. POST /api/system/mcp/call
    resp_call = client.post(
        "/api/system/mcp/call",
        json={
            "name": "execute_python_sandbox",
            "arguments": {"code": "result = 7 * 8"},
        },
        headers={"X-Clearance-Level": "PUBLIC"},
    )
    assert resp_call.status_code == 200
    data_call = resp_call.json()
    assert data_call["isError"] is False
    assert "56" in data_call["content"][0]["text"]

    # 3. GET /api/system/mcp/resources
    resp_res = client.get("/api/system/mcp/resources")
    assert resp_res.status_code == 200
    data_res = resp_res.json()
    assert "resources" in data_res

    app.dependency_overrides.clear()
