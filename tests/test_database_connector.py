"""Tests for DatabaseConnector: compound cursor, incremental sync, and test_connection."""

import sqlite3
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, text

from adam.connectors.database import DatabaseConnector
from adam.db.models import Source
from adam.vocabularies import Classification, DepartmentId, SourceStatus


@pytest.fixture
def sample_external_db(tmp_path):
    """Create a temporary external database simulating a departmental records database."""
    db_file = tmp_path / "dept_orders.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE departmental_orders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            issued_on TEXT NOT NULL,
            go_number TEXT,
            department_id TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Insert initial records with same and differing timestamps
    cursor.execute(
        """
        INSERT INTO departmental_orders (id, title, content, issued_on, go_number, department_id, updated_at)
        VALUES
            ('ord_001', 'Forest Fire Prevention Directive 2024', 'Directive content on wildfire containment.', '2024-03-01', 'UK/FOR/2024/01', 'FOREST_ENVIRONMENT', '2024-03-01T10:00:00Z'),
            ('ord_002', 'River Basin Afforestation Scheme', 'Policy on watershed afforestation.', '2024-03-05', 'UK/FOR/2024/02', 'FOREST_ENVIRONMENT', '2024-03-05T12:00:00Z'),
            ('ord_003', 'Eco-Tourism Guidelines Dehradun', 'Guidelines for eco-lodges and trails.', '2024-03-05', 'UK/FOR/2024/03', 'FOREST_ENVIRONMENT', '2024-03-05T12:00:00Z')
        """
    )
    conn.commit()
    conn.close()
    return f"sqlite:///{db_file}"


def test_database_connector_connection_test(sample_external_db):
    source = Source(
        id="src_ext_forest_db",
        name="Forest Department DB",
        source_type="DATABASE",
        config_json={
            "connection_uri": sample_external_db,
            "table_name": "departmental_orders",
        },
    )
    connector = DatabaseConnector()
    ok, msg = connector.test_connection(source)
    assert ok is True
    assert "Successfully connected" in msg


def test_database_connector_connection_test_invalid_table(sample_external_db):
    source = Source(
        id="src_ext_forest_db_bad",
        name="Forest Department DB Bad Table",
        source_type="DATABASE",
        config_json={
            "connection_uri": sample_external_db,
            "table_name": "non_existent_table",
        },
    )
    connector = DatabaseConnector()
    ok, msg = connector.test_connection(source)
    assert ok is False
    assert "does not exist" in msg


def test_database_connector_compound_cursor_incremental_sync(sample_external_db):
    source = Source(
        id="src_ext_forest_db",
        name="Forest Department DB",
        source_type="DATABASE",
        department_id=DepartmentId.GENERAL_ADMINISTRATION.value,
        config_json={
            "connection_uri": sample_external_db,
            "table_name": "departmental_orders",
            "watermark_column": "updated_at",
            "id_column": "id",
            "batch_size": 10,
        },
    )
    connector = DatabaseConnector()

    # 1. Full discovery (all 3 records)
    items = list(connector.discover(source))
    assert len(items) == 3
    assert items[0].title == "Forest Fire Prevention Directive 2024"
    assert items[1].title == "River Basin Afforestation Scheme"
    assert items[2].title == "Eco-Tourism Guidelines Dehradun"

    # 2. Incremental sync using compound cursor:
    # Say we already synced up to '2024-03-05T12:00:00Z' and id 'ord_002'
    # The compound cursor must return ONLY 'ord_003' (same timestamp, higher id)
    cursor = {"watermark": "2024-03-05T12:00:00Z", "last_id": "ord_002"}
    inc_items = list(connector.discover_incremental(source, compound_cursor=cursor))
    assert len(inc_items) == 1
    assert inc_items[0].metadata["id_val"] == "ord_003"
    assert inc_items[0].title == "Eco-Tourism Guidelines Dehradun"

    # 3. Test Fetch
    fetch_res = connector.fetch(inc_items[0])
    assert fetch_res.http_status == 200
    assert b"Guidelines for eco-lodges" in fetch_res.data
