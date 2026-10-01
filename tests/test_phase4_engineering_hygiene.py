"""Test suite for Phase 4: Engineering Hygiene, Product, and Governance (H1-H8)."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adam.api.app import app
from adam.auth.security import create_access_token
from adam.connectors.registry import ConnectorRegistry
from adam.connectors.s3_bucket import S3BucketConnector
from adam.db.models import Source


# ── 1. Python 3.12 & Docker Hardening (H4, H6) ───────────────────────────────


def test_python_312_target_and_docker_hardening():
    """Verify single Python target (>=3.12) across pyproject and Dockerfile, and tests exclusion."""
    root = Path(__file__).resolve().parent.parent

    # 1. pyproject.toml
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.12"' in pyproject

    # 2. Dockerfile
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in dockerfile

    # Production target must NOT copy tests/
    prod_section = dockerfile.split("FROM base AS production")[-1]
    assert "COPY tests" not in prod_section

    # Development target must copy tests/
    dev_section = dockerfile.split("FROM base AS development")[-1].split("FROM base AS production")[0]
    assert "COPY tests" in dev_section


def test_prod_compose_postgres_port_unpublishing():
    """Verify production compose drops published database port to protect internal network (H6)."""
    root = Path(__file__).resolve().parent.parent
    prod_compose = (root / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "ports: !override []" in prod_compose


# ── 2. S3 / MinIO Object Storage Connector ───────────────────────────────────


def test_s3_bucket_connector_mocked():
    """Verify S3BucketConnector connection test, discovery pagination, and object fetching."""
    connector = S3BucketConnector(
        bucket_name="uk-gov-records",
        prefix="finance/2024",
        endpoint_url="http://minio:9000",
        aws_access_key_id="mock_key",
        aws_secret_access_key="mock_secret",
    )

    mock_client = MagicMock()
    # Test head_bucket
    mock_client.head_bucket.return_value = {}

    # Test discover
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "finance/2024/UK_FIN_2024_101.pdf",
                    "Size": 102400,
                    "ETag": '"abcdef123456"',
                    "LastModified": datetime(2024, 1, 15, tzinfo=timezone.utc),
                },
                {
                    "Key": "finance/2024/ignored.tmp",
                    "Size": 12,
                    "LastModified": datetime(2024, 1, 15, tzinfo=timezone.utc),
                },
            ]
        }
    ]

    # Test fetch
    mock_body = MagicMock()
    mock_body.read.return_value = b"%PDF-1.4 test payload content"
    mock_client.get_object.return_value = {
        "Body": mock_body,
        "ContentType": "application/pdf",
    }

    with patch.object(connector, "_get_s3_client", return_value=mock_client):
        source = Source(
            id="src_s3_test",
            name="S3 Test Bucket",
            department_id="FINANCE_TREASURY",
            source_type="S3",
            access_classification="PUBLIC",
            config_json={"bucket_name": "uk-gov-records", "prefix": "finance/2024"},
        )

        # 1. Connection test
        ok, msg = connector.test_connection(source)
        assert ok is True
        assert "uk-gov-records" in msg

        # 2. Discover
        items = list(connector.discover(source))
        assert len(items) == 1
        item = items[0]
        assert item.source_url == "s3://uk-gov-records/finance/2024/UK_FIN_2024_101.pdf"
        assert item.doc_type == "GO"
        assert item.department_id == "FINANCE_TREASURY"

        # 3. Fetch
        res = connector.fetch(item)
        assert res.http_status == 200
        assert res.data == b"%PDF-1.4 test payload content"


def test_connector_registry_resolves_s3():
    """Verify ConnectorRegistry dynamically instantiates S3BucketConnector for S3/OBJECT_STORAGE sources."""
    source_s3 = Source(
        id="src_s3_test",
        source_type="S3",
        config_json={"bucket_name": "uk-orders-archive", "prefix": "orders/"},
    )
    connector = ConnectorRegistry.resolve_connector(source_s3)
    assert isinstance(connector, S3BucketConnector)
    assert connector.bucket_name == "uk-orders-archive"
    assert connector.prefix == "orders"


# ── 3. Authenticated Metrics & OpenTelemetry Configuration (H8) ──────────────


def test_metrics_route_requires_authentication():
    """Verify Prometheus /api/metrics endpoint requires valid ADMIN/AUDITOR credentials (H8)."""
    client = TestClient(app)

    # 1. Unauthenticated request rejected
    r_unauth = client.get("/api/metrics")
    assert r_unauth.status_code in (401, 403)

    # 2. Insufficient clearance / non-admin rejected
    user_token = create_access_token({"sub": "citizen_user", "roles": ["PUBLIC"]})
    r_user = client.get("/api/metrics", headers={"Authorization": f"Bearer {user_token}"})
    assert r_user.status_code in (401, 403)

    # 3. Admin authorized
    admin_token = create_access_token({"sub": "admin_user", "roles": ["ADMIN"]})
    r_admin = client.get("/api/metrics", headers={"Authorization": f"Bearer {admin_token}"})
    assert r_admin.status_code == 200
    assert "adam_info" in r_admin.text or "adam_documents_total" in r_admin.text


# ── 4. Government Compliance Pack (Statutory Documentation) ──────────────────


def test_compliance_pack_documents_exist():
    """Verify all 4 statutory compliance documents are present with required sections."""
    root = Path(__file__).resolve().parent.parent
    compliance_dir = root / "docs" / "compliance"
    assert compliance_dir.is_dir()

    expected_docs = [
        ("data_residency.md", ["Data Residency", "Air-Gap", "State Data Centre"]),
        ("retention_and_erasure.md", ["Retention", "Cryptographic Erasure", "Gazette"]),
        ("dpdp_act_2023.md", ["DPDP Act", "Data Fiduciary", "Redaction"]),
        ("hardening_guide.md", ["CIS Benchmark", "Non-Root", "SIGNING_SECRET"]),
    ]

    for doc_name, required_keywords in expected_docs:
        doc_path = compliance_dir / doc_name
        assert doc_path.is_file(), f"Missing compliance doc: {doc_name}"
        content = doc_path.read_text(encoding="utf-8")
        for kw in required_keywords:
            assert kw.lower() in content.lower(), f"Keyword '{kw}' missing from {doc_name}"


# ── 5. Project Governance Documents (H3) ─────────────────────────────────────


def test_governance_docs_changelog_and_contributing():
    """Verify CHANGELOG.md and CONTRIBUTING.md exist and document Phases 0 through 4."""
    root = Path(__file__).resolve().parent.parent

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Phase 0" in changelog
    assert "Phase 1" in changelog
    assert "Phase 2" in changelog
    assert "Phase 3" in changelog
    assert "Phase 4" in changelog

    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Pull Request" in contributing or "PR" in contributing
    assert "ruff" in contributing
    assert "test" in contributing.lower()
