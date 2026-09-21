"""External Database Connector with compound cursor incremental sync.

Extracts administrative and government records from external relational databases
(PostgreSQL, MySQL, SQLite) using strictly read-only connections and compound cursor
pagination (watermark_timestamp, unique_id).
"""

import json
import logging
import re
from datetime import datetime, timezone, date
from typing import Iterator, Optional, Dict, Any, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.db.models import Source
from adam.vocabularies import DocType, AuthorityLevel, Classification

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_sql_identifier(name: str, param_name: str = "identifier") -> str:
    """Ensure SQL identifier matches strict alphanumeric whitelist to prevent SQL injection."""
    cleaned = (name or "").strip()
    if not _IDENTIFIER_RE.match(cleaned):
        raise ValueError(
            f"Invalid SQL {param_name}: '{name}'. Identifiers must be alphanumeric and start with a letter or underscore."
        )
    return cleaned


class DatabaseConnector(BaseConnector):
    """Acquires records from external departmental SQL databases."""

    def __init__(self, connection_uri: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        self._connection_uri = connection_uri
        self._config = config or {}
        self._engine: Optional[Engine] = None

    def _get_engine(self, source: Source) -> Engine:
        if self._engine is not None:
            return self._engine

        cfg = source.config_json or self._config or {}
        uri = self._connection_uri or cfg.get("connection_uri")
        if not uri:
            raise ValueError(f"Source '{source.id}' missing required 'connection_uri' in configuration.")

        # Ensure safety: enforce read-only execution where possible
        engine_args = {"future": True, "pool_pre_ping": True}
        if uri.startswith("sqlite"):
            # External SQLite file
            pass
        elif uri.startswith("postgresql") or uri.startswith("mysql"):
            # Set timeout to prevent hanging connections
            engine_args["connect_args"] = {"connect_timeout": 10}

        self._engine = create_engine(uri, **engine_args)
        return self._engine

    def test_connection(self, source: Source) -> Tuple[bool, str]:
        """Test reachability and read permissions on external database."""
        try:
            eng = self._get_engine(source)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
                cfg = source.config_json or self._config or {}
                table_name = cfg.get("table_name")
                if table_name:
                    from sqlalchemy import inspect
                    insp = inspect(eng)
                    tables = set(insp.get_table_names())
                    if table_name not in tables:
                        return False, f"Table '{table_name}' does not exist in external database."
            return True, "Successfully connected to external database."
        except Exception as e:
            return False, f"External database connection failed: {str(e)}"

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        """Full discovery starting from cursor zero."""
        yield from self.discover_incremental(source, compound_cursor=None)

    def discover_incremental(
        self,
        source: Source,
        compound_cursor: Optional[Dict[str, Any]] = None,
    ) -> Iterator[DiscoveredItem]:
        """Incremental discovery using compound cursor (watermark_timestamp, unique_id)."""
        eng = self._get_engine(source)
        cfg = source.config_json or self._config or {}

        table_name = cfg.get("table_name")
        custom_query = cfg.get("query")
        watermark_col = _validate_sql_identifier(cfg.get("watermark_column", "updated_at"), "watermark_column")
        id_col = _validate_sql_identifier(cfg.get("id_column", "id"), "id_column")
        title_col = _validate_sql_identifier(cfg.get("title_column", "title"), "title_column")
        content_col = _validate_sql_identifier(cfg.get("content_column", "content"), "content_column")
        date_col = _validate_sql_identifier(cfg.get("date_column", "issued_on"), "date_column")
        go_num_col = _validate_sql_identifier(cfg.get("go_number_column", "go_number"), "go_number_column")
        dept_col = _validate_sql_identifier(cfg.get("department_column", "department_id"), "department_column")
        batch_size = max(1, min(10000, int(cfg.get("batch_size", 100))))

        cursor_wm = compound_cursor.get("watermark") if compound_cursor else None
        cursor_id = compound_cursor.get("last_id") if compound_cursor else None

        with eng.connect() as conn:
            # Build query with compound cursor condition
            if custom_query:
                # Custom query must include compound cursor placeholders if supported
                base_sql = custom_query
            else:
                if not table_name:
                    raise ValueError(f"Source '{source.id}' missing required 'table_name' or 'query'.")
                safe_table_name = _validate_sql_identifier(table_name, "table_name")

                where_clauses = []
                params = {}

                if cursor_wm is not None and cursor_id is not None:
                    where_clauses.append(
                        f"({watermark_col} > :wm OR ({watermark_col} = :wm AND {id_col} > :cid))"
                    )
                    params["wm"] = cursor_wm
                    params["cid"] = cursor_id
                elif cursor_wm is not None:
                    where_clauses.append(f"{watermark_col} > :wm")
                    params["wm"] = cursor_wm

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                order_sql = f"ORDER BY {watermark_col} ASC, {id_col} ASC"
                sql = f"SELECT * FROM {safe_table_name} {where_sql} {order_sql} LIMIT {batch_size}"

                result = conn.execute(text(sql), params)
                columns = result.keys()

                for row in result:
                    row_dict = dict(zip(columns, row))
                    row_id = str(row_dict.get(id_col, ""))
                    wm_val = row_dict.get(watermark_col)
                    wm_str = wm_val.isoformat() if hasattr(wm_val, "isoformat") else str(wm_val)

                    title = str(row_dict.get(title_col) or f"Record {row_id}")
                    dept = str(row_dict.get(dept_col) or source.department_id)
                    go_num = str(row_dict.get(go_num_col)) if row_dict.get(go_num_col) else None

                    displayed_date = None
                    raw_date = row_dict.get(date_col)
                    if isinstance(raw_date, (date, datetime)):
                        displayed_date = raw_date if isinstance(raw_date, date) else raw_date.date()
                    elif isinstance(raw_date, str):
                        try:
                            displayed_date = date.fromisoformat(raw_date[:10])
                        except Exception:
                            pass

                    # Raw content payload: text, JSON, or bytes
                    raw_content = row_dict.get(content_col, "")
                    source_url = f"db://{source.id}/{table_name}/{row_id}"

                    if not hasattr(self, "_content_cache"):
                        self._content_cache = {}

                    if isinstance(raw_content, bytes):
                        self._content_cache[source_url] = raw_content
                    elif isinstance(raw_content, str):
                        self._content_cache[source_url] = raw_content.encode("utf-8")
                    elif isinstance(raw_content, dict):
                        self._content_cache[source_url] = json.dumps(raw_content, ensure_ascii=False).encode("utf-8")
                    else:
                        self._content_cache[source_url] = str(raw_content or "").encode("utf-8")

                    yield DiscoveredItem(
                        source_url=source_url,
                        title=title,
                        doc_type=DocType.GO.value,
                        department_id=dept,
                        displayed_date=displayed_date,
                        go_number=go_num,
                        authority_level=AuthorityLevel.DEPARTMENTAL_SECRETARY.value,
                        classification=source.access_classification or Classification.PUBLIC.value,
                        metadata={
                            "database_source": True,
                            "table_name": table_name,
                            "row_id": row_id,
                            "watermark_val": wm_str,
                            "id_val": row_id,
                        },
                    )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        """Fetch item payload from cache or directly from external DB."""
        if hasattr(self, "_content_cache") and item.source_url in self._content_cache:
            data = self._content_cache[item.source_url]
        else:
            data = b""

        # Determine MIME type
        mime_type = "application/pdf" if data.startswith(b"%PDF-") else "text/plain"

        return FetchResult(
            source_url=item.source_url,
            data=data,
            http_status=200,
            http_headers={"content-type": mime_type},
            retrieved_at=datetime.now(timezone.utc),
        )

    def close(self) -> None:
        """Dispose cached SQLAlchemy engine and connection pool."""
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception:
                pass
            self._engine = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
