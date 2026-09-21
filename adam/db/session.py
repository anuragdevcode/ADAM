"""Database session and engine management."""

from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from adam.config import get_database_url

Base = declarative_base()

_ENGINES: dict[str, Engine] = {}
_SESSION_FACTORIES: dict[str, sessionmaker] = {}


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints in SQLite."""
    if dbapi_connection.__class__.__module__.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine(db_url: Optional[str] = None) -> Engine:
    """Get or create SQLAlchemy Engine for the given URL (or environment default)."""
    url = db_url or get_database_url()
    if url not in _ENGINES:
        engine = create_engine(
            url,
            echo=False,
            future=True,
        )
        # Automatically ensure schema tables and versioned migrations exist
        from adam.db.models import Base
        Base.metadata.create_all(bind=engine)
        from adam.db.migrations import apply_ingestion_migrations
        apply_ingestion_migrations(engine)
        _migrate_missing_columns(engine)
        _ENGINES[url] = engine
    return _ENGINES[url]


def _migrate_missing_columns(engine: Engine) -> None:
    """Ensure newly added model columns exist in existing SQLite databases."""
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        from adam.db.models import Base
        with engine.begin() as conn:
            altered = False
            for table_name, table in Base.metadata.tables.items():
                if table_name in existing_tables:
                    existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
                    for col in table.columns:
                        if col.name not in existing_cols:
                            col_type = col.type.compile(engine.dialect)
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}"))
                            altered = True
            if altered and "sqlite" in str(engine.url):
                conn.execute(text("REINDEX"))
    except Exception:
        pass



def get_session(engine: Optional[Engine] = None, db_url: Optional[str] = None) -> Session:
    """Create a new database session."""
    eng = engine or get_engine(db_url)
    url_key = str(eng.url)
    if url_key not in _SESSION_FACTORIES:
        _SESSION_FACTORIES[url_key] = sessionmaker(
            bind=eng, autoflush=False, expire_on_commit=False
        )
    return _SESSION_FACTORIES[url_key]()


@contextmanager
def session_scope(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """Context manager for transactional database sessions."""
    session = get_session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Optional[Engine] = None) -> None:
    """Create all registered database tables and run versioned migrations."""
    from adam.db.models import Base  # ensure all models are imported
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
    from adam.db.migrations import apply_ingestion_migrations
    apply_ingestion_migrations(eng)
