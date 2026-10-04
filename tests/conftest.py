"""Shared pytest fixtures and mock test environments."""

import hashlib
import os
import tempfile
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Any

# Ensure tests use an isolated database and storage to prevent interference with live local server or corruption
if not os.environ.get("DATABASE_URL"):
    _test_db = Path(tempfile.gettempdir()) / "adam_pytest.db"
    try:
        if _test_db.exists():
            _test_db.unlink()
    except OSError:
        pass
    os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"

if not os.environ.get("ADAM_STORAGE_DIR"):
    _test_storage = Path(tempfile.gettempdir()) / "adam_test_storage"
    _test_storage.mkdir(parents=True, exist_ok=True)
    os.environ["ADAM_STORAGE_DIR"] = str(_test_storage)

# Allow legacy unit tests that provide raw mock headers (X-User-Role) to run without token fixtures.
# Phase 1 and security hardening suites explicitly monkeypatch ADAM_TRUST_UNVERIFIED_HEADERS=false.
os.environ.setdefault("ADAM_TRUST_UNVERIFIED_HEADERS", "true")

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adam.db.models import Base
from adam.db.session import _set_sqlite_pragma
from adam.ingest.registry import SourceOnboardingSheet
from adam.storage.local import LocalStorageBackend
from adam.vocabularies import DepartmentId, Classification, RefreshCadence


SAMPLE_PDF_BYTES_1 = b"%PDF-1.4\n1 0 obj\n<< /Title (Uttarakhand Treasury Order 2024-01) >>\nendobj\ntrailer\n<<>>\n%%EOF"
SAMPLE_PDF_BYTES_2 = b"%PDF-1.4\n1 0 obj\n<< /Title (Uttarakhand Treasury Order 2024-02 Revised) >>\nendobj\ntrailer\n<<>>\n%%EOF"


@pytest.fixture
def tmp_storage(tmp_path: Path) -> LocalStorageBackend:
    """Fixture providing a temporary LocalStorageBackend."""
    storage_dir = tmp_path / "storage"
    return LocalStorageBackend(storage_dir)


@pytest.fixture
def db_session():
    """Fixture providing an isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_source_sheet() -> SourceOnboardingSheet:
    """Standard test source onboarding sheet."""
    return SourceOnboardingSheet(
        id="src_test_treasury",
        name="Test Treasury GO Portal",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Director of Treasuries, UK",
        owner_contact="director-treasury@uk.gov.in",
        written_authority_ref="TEST-AUTH-2024-01",
        permitted_domains=["ekosh.uk.gov.in"],
        permitted_path_prefixes=["/government-orders/"],
        access_classification=Classification.PUBLIC.value,
        refresh_cadence=RefreshCadence.WEEKLY.value,
        rate_limit_per_minute=60,
        retention_policy="PERMANENT",
    )


@pytest.fixture
def mock_treasury_html() -> str:
    """Simulated HTML page for Treasury GO portal."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Government Orders - Ekosh Uttarakhand</title></head>
    <body>
      <h1>Departmental Government Orders</h1>
      <table class="table">
        <tr>
          <th>Order No</th>
          <th>Date</th>
          <th>Subject / Title</th>
          <th>Download</th>
        </tr>
        <tr>
          <td>GO/2024/101</td>
          <td>15/01/2024</td>
          <td>Revised Dearness Allowance for State Employees</td>
          <td><a href="/government-orders/go-2024-101.pdf">Download PDF</a></td>
        </tr>
        <tr>
          <td>GO/2024/102</td>
          <td>20/01/2024</td>
          <td>Treasury Single Account Operational Guidelines</td>
          <td><a href="/government-orders/go-2024-102.pdf">Download PDF</a></td>
        </tr>
      </table>
    </body>
    </html>
    """


@pytest.fixture
def cli_runner(tmp_path: Path, monkeypatch):
    """Fixture providing CliRunner isolated in a temporary database and storage directory."""
    from click.testing import CliRunner
    db_file = tmp_path / "test_adam.db"
    storage_dir = tmp_path / "test_storage"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    return CliRunner()

