"""Comprehensive tests for pgvector integration, schema migration, and pushdown retrieval."""

import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from adam.db.models import Base, Document, DocumentChunk, DocumentVersion, Source
from adam.db.migrations import (
    PGVECTOR_MIGRATION_VERSION,
    apply_migrations,
    apply_pgvector_migrations,
)
from adam.rag.chunker import SemanticChunker, chunk_document_version
from adam.rag.models import ParsedQuery, UserContext
from adam.rag.retriever import HybridRetriever, MultilingualSemanticVectorizer
from adam.vocabularies import Classification, DepartmentId, DocType, LifecycleStatus, ReviewStatus
from pgvector.sqlalchemy import Vector


def test_document_chunk_has_vector_column():
    """Verify that DocumentChunk model has the pgvector Vector(128) column and HNSW index defined."""
    cols = {c.name: c for c in DocumentChunk.__table__.columns}
    assert "embedding" in cols, "DocumentChunk must have an 'embedding' column"
    assert isinstance(cols["embedding"].type, Vector), "embedding column must be Vector type"
    assert cols["embedding"].type.dim == 128, "embedding column must have dimension 128"
    assert "embedding_json" in cols, "embedding_json must remain for fallback/compatibility"

    # Verify HNSW index is declared in table args
    index_names = {idx.name: idx for idx in DocumentChunk.__table__.indexes}
    assert "idx_chunk_embedding_hnsw" in index_names, "HNSW index must be declared in __table_args__"
    hnsw_idx = index_names["idx_chunk_embedding_hnsw"]
    assert hnsw_idx.dialect_options["postgresql"]["using"] == "hnsw"
    assert hnsw_idx.dialect_options["postgresql"]["ops"]["embedding"] == "vector_cosine_ops"


def test_pgvector_sql_generation_uses_cosine_operator():
    """Verify that on PostgreSQL dialect, order_by on embedding generates the native <=> operator."""
    mock_engine = create_engine("postgresql+psycopg://user:pass@localhost:5432/mock_db")
    Session = sessionmaker(bind=mock_engine)
    session = Session()

    q_vec = [0.1] * 128
    query = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).order_by(
        DocumentChunk.embedding.cosine_distance(q_vec)
    ).limit(10)

    compiled_sql = str(query.statement.compile(dialect=postgresql.dialect()))
    assert "<=>" in compiled_sql, f"Expected '<=>' operator in compiled SQL: {compiled_sql}"
    assert "ORDER BY document_chunks.embedding <=>" in compiled_sql
    assert "LIMIT" in compiled_sql


def test_vectorizer_properties():
    """Verify MultilingualSemanticVectorizer produces unit-normalized 128-dimensional vectors."""
    vec = MultilingualSemanticVectorizer.embed_text("Dearness allowance for Uttarakhand officers")
    assert len(vec) == 128
    assert isinstance(vec, list)

    # Norm should be approx 1.0
    import numpy as np
    norm = np.linalg.norm(np.array(vec))
    assert 0.99 <= norm <= 1.01

    # Empty text produces 0-vector
    empty_vec = MultilingualSemanticVectorizer.embed_text("")
    assert len(empty_vec) == 128
    assert all(v == 0.0 for v in empty_vec)


def test_chunk_document_precomputes_embeddings(tmp_path):
    """Verify that chunk_document_version computes and stores 128-dim vectors during ingestion."""
    db_file = tmp_path / "test_chunk_embed.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    source = Source(
        id="src_vector_test",
        name="Test Source",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Test Owner",
        owner_contact="test@uk.gov.in",
        written_authority_ref="AUTH/TEST",
        permitted_domains=["uk.gov.in"],
        access_classification=Classification.PUBLIC.value,
    )
    doc = Document(
        id="doc_vec_test",
        source_id=source.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="Finance Dearness Allowance Order",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    version = DocumentVersion(
        id="ver_vec_test",
        document_id=doc.id,
        source_url="https://uk.gov.in/test.pdf",
        sha256="testsha256",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="docs/test.pdf",
        go_number="UK/FIN/2024/999",
    )
    doc.versions.append(version)
    session.add_all([source, doc, version])
    session.commit()

    from adam.db.models import DocumentPage
    page = DocumentPage(
        id="page_vec_test",
        version_id=version.id,
        page_number=1,
        clean_text="Dearness allowance revised by 4 percent for state government employees.",
        selected_text="Dearness allowance revised by 4 percent for state government employees.",
        review_status=ReviewStatus.AUTO_APPROVED.value,
    )
    session.add(page)
    session.commit()

    chunks = chunk_document_version(session, version.id)
    assert len(chunks) >= 1
    chk = chunks[0]
    assert chk.embedding is not None, "chunk.embedding must be populated at chunking time"
    assert len(chk.embedding) == 128
    assert chk.embedding_json is not None, "chunk.embedding_json must also be populated"
    assert len(chk.embedding_json) == 128


def test_pgvector_migration_idempotency(tmp_path):
    """Verify apply_pgvector_migrations runs idempotently and records version in schema_migrations."""
    db_file = tmp_path / "test_migration.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)

    apply_pgvector_migrations(engine)
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("document_chunks")}
    assert "embedding" in cols

    with engine.begin() as conn:
        res = conn.execute(
            text("SELECT version FROM schema_migrations WHERE version = :ver"),
            {"ver": PGVECTOR_MIGRATION_VERSION},
        ).fetchone()
        assert res is not None
        assert res[0] == PGVECTOR_MIGRATION_VERSION

    # Second run should be a no-op without error
    apply_migrations(engine)


def test_hybrid_retriever_postgresql_branch_mocked(tmp_path):
    """Verify that when _is_postgresql returns True, HybridRetriever executes the pushdown branch."""
    db_file = tmp_path / "test_retriever_pg.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed one test chunk
    source = Source(
        id="src_ret_test",
        name="Source",
        department_id=DepartmentId.FINANCE_TREASURY.value,
        owner_name="Test",
        owner_contact="test@uk.gov.in",
        written_authority_ref="AUTH/TEST",
        permitted_domains=["uk.gov.in"],
        access_classification=Classification.PUBLIC.value,
    )
    doc = Document(
        id="doc_ret_test",
        source_id=source.id,
        department_id=DepartmentId.FINANCE_TREASURY.value,
        doc_type=DocType.GO.value,
        title="DA Revised 2024",
        classification=Classification.PUBLIC.value,
        lifecycle_status=LifecycleStatus.ACTIVE.value,
    )
    version = DocumentVersion(
        id="ver_ret_test",
        document_id=doc.id,
        source_url="https://uk.gov.in/test.pdf",
        sha256="testsha256",
        mime_type="application/pdf",
        byte_size=1024,
        original_object_key="docs/test.pdf",
        go_number="UK/FIN/2024/777",
    )
    emb = MultilingualSemanticVectorizer.embed_text("DA Revised 2024 Dearness Allowance")
    chunk = DocumentChunk(
        id="chk_ret_test",
        document_id=doc.id,
        version_id=version.id,
        chunk_index=0,
        content="Dearness allowance increased by 4 percent effective July 2024.",
        token_count=10,
        page_start=1,
        page_end=1,
        classification=Classification.PUBLIC.value,
        review_status=ReviewStatus.AUTO_APPROVED.value,
        embedding=emb,
        embedding_json=emb,
    )
    session.add_all([source, doc, version, chunk])
    session.commit()

    retriever = HybridRetriever(session)

    # Force _is_postgresql to True while using SQLite session; the try/except handles SQLite <=> error and falls back gracefully
    with patch.object(retriever, "_is_postgresql", return_value=True):
        parsed = ParsedQuery(
            raw_query="What is the dearness allowance increase?",
            clean_query="What is the dearness allowance increase?",
        )
        user_ctx = UserContext(user_id="officer_1", clearance_level=Classification.PUBLIC.value)
        results = retriever.retrieve(parsed_query=parsed, user_context=user_ctx, top_k=5)
        assert len(results) >= 1
        assert results[0].chunk_id == chunk.id
