"""Tests for official Uttarakhand state connectors onboarding, presets, and auto-seeding."""

import pytest
from starlette.testclient import TestClient

from adam.api.app import app
from adam.connectors.registry import ConnectorRegistry
from adam.connectors.ekosh import EkoshTreasuryConnector
from adam.connectors.ukrd import UkrdConnector
from adam.connectors.egazette import EGazetteConnector
from adam.connectors.itda import ITDASampleBatchConnector
from adam.connectors.generic_web import GenericWebsiteConnector
from adam.db.models import Source


def test_official_presets_catalog():
    presets = ConnectorRegistry.get_official_presets()
    assert len(presets) >= 6

    preset_ids = {p["preset_id"] for p in presets}
    assert {"ekosh", "ukrd", "egazette", "itda", "audit", "bor"}.issubset(preset_ids)

    for p in presets:
        assert p["name"]
        assert p["connector_id"]
        assert p["connector_class"]
        assert p["source_type"] in ["WEBSITE", "DATABASE", "FILE_UPLOAD"]
        assert p["department_id"]
        assert p["department_name"]
        assert isinstance(p["permitted_domains"], list)
        assert len(p["permitted_domains"]) > 0


def test_resolve_connector_for_official_presets():
    # Test eKosh resolution
    ekosh_src = Source(
        id="src_ekosh_treasury_go",
        name="Ekosh",
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/"],
        config_json={"connector_id": "ekosh"},
    )
    conn = ConnectorRegistry.resolve_connector(ekosh_src)
    assert isinstance(conn, EkoshTreasuryConnector)

    # Test UKRD resolution
    ukrd_src = Source(
        id="src_ukrd_documents",
        name="UKRD",
        permitted_domains=["ukrd.uk.gov.in"],
        permitted_path_prefixes=["/documents/"],
        config_json={"connector_id": "ukrd"},
    )
    conn = ConnectorRegistry.resolve_connector(ukrd_src)
    assert isinstance(conn, UkrdConnector)

    # Test eGazette resolution
    egazette_src = Source(
        id="src_uk_egazette",
        name="eGazette",
        permitted_domains=["gazettes.uk.gov.in"],
        permitted_path_prefixes=["/pages/go%27s-and-gazettes"],
        config_json={"connector_id": "egazette"},
    )
    conn = ConnectorRegistry.resolve_connector(egazette_src)
    assert isinstance(conn, EGazetteConnector)

    # Test ITDA sample batch resolution
    itda_src = Source(
        id="src_itda_pilot_batch",
        name="ITDA Batch",
        source_type="FILE_UPLOAD",
        permitted_domains=["itda.uk.gov.in"],
        config_json={"connector_id": "itda"},
    )
    conn = ConnectorRegistry.resolve_connector(itda_src)
    assert isinstance(conn, ITDASampleBatchConnector)


def test_api_presets_and_seed_endpoints():
    client = TestClient(app)

    # Test GET /api/sources/presets
    resp = client.get("/api/sources/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 6
    preset_map = {p["preset_id"]: p for p in data}
    assert "ekosh" in preset_map
    assert preset_map["ekosh"]["connector_class"] == "EkoshTreasuryConnector"

    # Test POST /api/sources/seed
    seed_resp = client.post("/api/sources/seed")
    assert seed_resp.status_code == 200
    seed_data = seed_resp.json()
    assert seed_data["success"] is True
    assert seed_data["total_active_sources"] >= 8

    # Verify sources list now has the seeded sources
    src_resp = client.get("/api/sources")
    assert src_resp.status_code == 200
    sources = src_resp.json()
    source_ids = {s["id"] for s in sources}
    assert "src_ekosh_treasury_go" in source_ids
    assert "src_ukrd_documents" in source_ids
    assert "src_uk_egazette" in source_ids
    assert "src_itda_pilot_batch" in source_ids


def test_api_trigger_job_json_and_multipart(monkeypatch):
    client = TestClient(app)

    from adam.db.models import IngestionJob
    mock_job = IngestionJob(
        id="job_mock123",
        source_id="src_ekosh_treasury_go",
        status="QUEUED",
        job_type="FULL",
        current_stage="IDLE",
    )
    monkeypatch.setattr(
        "adam.api.routers.ingestions.GLOBAL_INGESTION_CONTROL_PLANE.start_job",
        lambda **kwargs: mock_job,
    )

    # 1. Trigger via JSON (as used by UI "Run Ingest")
    resp_json = client.post(
        "/api/ingestion/jobs",
        json={
            "source_id": "src_ekosh_treasury_go",
            "job_type": "FULL",
            "max_items": 1,
        },
    )
    assert resp_json.status_code == 200
    json_data = resp_json.json()
    assert json_data["job_id"] == "job_mock123"
    assert json_data["source_id"] == "src_ekosh_treasury_go"
    assert json_data["status"] == "QUEUED"

    # 2. Trigger via Multipart Form (as used by UI "Upload Files")
    resp_form = client.post(
        "/api/ingestion/jobs",
        data={
            "source_id": "src_itda_pilot_batch",
            "job_type": "FULL",
        },
        files={"files": ("test_doc.txt", b"Test government document content", "text/plain")},
    )
    assert resp_form.status_code == 200
    form_data = resp_form.json()
    assert form_data["job_id"] == "job_mock123"

    # 3. Missing source_id returns 400
    resp_err = client.post("/api/ingestion/jobs", json={})
    assert resp_err.status_code == 400

