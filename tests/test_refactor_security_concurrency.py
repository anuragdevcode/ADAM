"""Comprehensive regression and verification tests for backend refactor, security hardening, and concurrency."""

import asyncio
import os
import httpx
import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adam.agent.coordinator import HeavyWorkerCoordinator, HeavyTaskType, ResourceContentionError
from adam.agent.redaction import SecretRedactor
from adam.api.services.acl_service import AclService
from adam.api.services.idempotency import IdempotencyManager
from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.connectors.database import DatabaseConnector, _validate_sql_identifier
from adam.connectors.file_batch import FileBatchConnector
from adam.db.models import Base, Document, DocumentVersion, AccessGrant, Source, IdempotencyRecord
from adam.ingest.control_plane import JobController
from adam.rag.models import UserContext
from adam.storage.base import StorageError
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import Classification, AccessAction


# ── 1. Storage Path Traversal Hardening ──────────────────────────────────────


def test_local_storage_path_traversal_rejection(tmp_path):
    storage = LocalStorageBackend(root_dir=str(tmp_path))

    # Valid key works
    storage.store("valid/doc.pdf", b"safe content")
    assert storage.get("valid/doc.pdf") == b"safe content"

    # Traversal attempts must raise StorageError
    traversal_keys = [
        "../../etc/passwd",
        "sub/../../outside.txt",
        "docs/../../../shadow",
    ]
    for key in traversal_keys:
        with pytest.raises(StorageError, match="path traversal attempt detected"):
            storage.store(key, b"malicious")

        with pytest.raises(StorageError, match="path traversal attempt detected"):
            storage.get(key)


# ── 2. Database Connector SQL Injection Prevention & Engine Disposal ────────


def test_sql_identifier_validation():
    # Valid identifiers
    assert _validate_sql_identifier("users") == "users"
    assert _validate_sql_identifier("tbl_records_2026") == "tbl_records_2026"
    assert _validate_sql_identifier("_hidden") == "_hidden"

    # Invalid identifiers / SQL injection payloads
    invalid_identifiers = [
        "records; DROP TABLE users;--",
        "col 1",
        "name' OR '1'='1",
        "users--",
        "table$name",
        "",
        "123start_with_digit",
    ]
    for ident in invalid_identifiers:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_sql_identifier(ident)


def test_database_connector_context_manager(tmp_path):
    db_path = tmp_path / "test.db"
    conn_str = f"sqlite:///{db_path}"

    with DatabaseConnector(connection_uri=conn_str) as connector:
        assert connector is not None
    # Context exit should safely dispose engines without error


# ── 3. BaseConnector Resource Cleanup ───────────────────────────────────────


class DummyConnector(BaseConnector):
    def __init__(self):
        self._http_client = httpx.Client()

    def discover(self, source):
        return iter([])

    def fetch(self, item):
        return FetchResult(
            source_url="test://doc",
            data=b"test",
            http_status=200,
            http_headers={},
            retrieved_at=datetime.now(timezone.utc),
        )


def test_base_connector_close_and_context_manager():
    conn = DummyConnector()
    client = conn._http_client
    assert not client.is_closed
    with conn:
        pass
    assert client.is_closed


# ── 4. FileBatchConnector Sandbox Enforcement ───────────────────────────────


def test_file_batch_sandbox_enforcement(tmp_path):
    allowed_dir = tmp_path / "allowed"
    forbidden_dir = tmp_path / "forbidden"
    allowed_dir.mkdir()
    forbidden_dir.mkdir()

    source = Source(
        id="src_batch_test",
        source_type="FILE_BATCH",
        permitted_path_prefixes=[str(allowed_dir)],
    )

    # Discovering in allowed directory works
    connector_allowed = FileBatchConnector(batch_dir=allowed_dir)
    items = list(connector_allowed.discover(source))
    assert isinstance(items, list)

    # Discovering in forbidden directory is blocked by sandbox
    connector_forbidden = FileBatchConnector(batch_dir=forbidden_dir)
    with pytest.raises(ValueError, match="outside authorized path prefixes"):
        list(connector_forbidden.discover(source))


# ── 5. Centralized AclService ───────────────────────────────────────────────


@pytest.fixture
def acl_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_acl_service_clearance_hierarchy():
    assert AclService.get_accessible_classifications("PUBLIC") == ["PUBLIC"]
    assert set(AclService.get_accessible_classifications("INTERNAL")) == {"PUBLIC", "INTERNAL"}
    assert set(AclService.get_accessible_classifications("RESTRICTED")) == {"PUBLIC", "INTERNAL", "RESTRICTED"}
    assert len(AclService.get_accessible_classifications("CONFIDENTIAL")) == 4
    assert len(AclService.get_accessible_classifications("PUBLIC", is_admin=True)) == 4


def test_acl_service_can_access_document(acl_db):
    pub_doc = Document(id="doc_pub", title="Public Doc", classification="PUBLIC", department_id="FINANCE")
    int_doc = Document(id="doc_int", title="Internal Doc", classification="INTERNAL", department_id="FINANCE")
    other_dept_doc = Document(id="doc_other", title="Other Dept Doc", classification="INTERNAL", department_id="REVENUE")
    conf_doc = Document(id="doc_conf", title="Confidential Doc", classification="CONFIDENTIAL", department_id="FINANCE")

    acl_db.add_all([pub_doc, int_doc, other_dept_doc, conf_doc])
    acl_db.commit()

    # Public user can see public doc, but not internal or confidential
    user_pub = UserContext(user_id="user_1", roles=["CITIZEN"], clearance_level="PUBLIC", department_id="FINANCE")
    assert AclService.can_access_document(user_pub, pub_doc, acl_db) is True
    assert AclService.can_access_document(user_pub, int_doc, acl_db) is False
    assert AclService.can_access_document(user_pub, conf_doc, acl_db) is False

    # Internal user from FINANCE cannot access REVENUE internal doc (department boundary)
    user_finance = UserContext(user_id="user_2", roles=["OFFICER"], clearance_level="INTERNAL", department_id="FINANCE")
    assert AclService.can_access_document(user_finance, int_doc, acl_db) is True
    assert AclService.can_access_document(user_finance, other_dept_doc, acl_db) is False

    # AccessGrant overrides department boundary
    grant = AccessGrant(
        id="grant_1",
        subject_id="user_2",
        document_id="doc_other",
        action="READ",
        granted_at=datetime.now(timezone.utc),
    )
    acl_db.add(grant)
    acl_db.commit()
    assert AclService.can_access_document(user_finance, other_dept_doc, acl_db) is True

    # Admin can access everything
    user_admin = UserContext(user_id="admin_1", roles=["ADMIN"], clearance_level="CONFIDENTIAL")
    assert AclService.can_access_document(user_admin, conf_doc, acl_db) is True


# ── 6. Idempotency Payload Hash Verification ─────────────────────────────────


def test_idempotency_payload_mismatch_rejection(acl_db):
    key = "idemp_key_test_001"
    user_id = "officer_1"
    endpoint = "/v1/test"
    payload_a = {"amount": 100, "item": "book"}
    payload_b = {"amount": 200, "item": "pen"}

    # Save initial response
    IdempotencyManager.save_response(
        db=acl_db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        payload=payload_a,
        status_code=200,
        response_json={"success": True},
    )

    # Replaying with exact same payload returns cached response
    cached = IdempotencyManager.get_cached_response(
        db=acl_db,
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        payload=payload_a,
    )
    assert cached is not None
    assert cached[0] == 200
    assert cached[1] == {"success": True}

    # Reusing the same key with a DIFFERENT payload must raise 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        IdempotencyManager.get_cached_response(
            db=acl_db,
            key=key,
            user_id=user_id,
            endpoint=endpoint,
            payload=payload_b,
        )
    assert exc_info.value.status_code == 409
    assert "conflict" in exc_info.value.detail.lower()


# ── 7. Control Plane Asyncio Loop Thread-Safety ──────────────────────────────


def test_job_controller_threadsafe_broadcast():
    async def run_test():
        controller = JobController("job_test_threads")
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()
        controller.add_listener(q, loop)

        # Broadcast from another thread
        event = {"type": "test_event", "value": 42}
        await asyncio.to_thread(controller.broadcast, event, force=True)

        # Event must arrive safely in asyncio.Queue
        received = await asyncio.wait_for(q.get(), timeout=2.0)
        assert received["type"] == "test_event"
        assert received["value"] == 42

        controller.remove_listener(q)

    asyncio.run(run_test())
