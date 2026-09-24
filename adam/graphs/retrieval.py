"""Graph-Augmented Retrieval (Graph RAG) for Uttarakhand Public Records.

Expands initial vector/BM25 search results by traversing the Precedent DAG
to fetch connected amending orders, superseding notifications, and statutory rules.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from adam.graphs.precedents import PrecedentDAG, RelationType
from adam.rag.models import EvidencePacket, EvidencePassage, ParsedQuery, UserContext
from adam.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)


class GraphRAGRetriever:
    """Graph-aware retrieval engine augmenting vector search with precedent DAG traversal."""

    def __init__(
        self,
        session: Session,
        base_retriever: Optional[HybridRetriever] = None,
        precedent_dag: Optional[PrecedentDAG] = None,
    ):
        self.session = session
        self.base_retriever = base_retriever or HybridRetriever(session)
        self.dag = precedent_dag or PrecedentDAG.build_from_database(session)

    def retrieve(
        self,
        query: ParsedQuery,
        user_context: Optional[UserContext] = None,
        top_k: int = 5,
        max_graph_hops: int = 2,
    ) -> List[EvidencePassage]:
        """Perform hybrid retrieval augmented with graph traversal of amending/superseding orders."""
        # 1. Base Hybrid Retrieval (BM25 + Vector)
        base_passages: List[EvidencePassage] = self.base_retriever.retrieve(
            query=query,
            user_context=user_context,
            top_k=top_k,
        )

        if not base_passages:
            return []

        expanded_passages: List[EvidencePassage] = list(base_passages)
        seen_chunk_ids: Set[str] = {p.chunk_id for p in base_passages}
        seen_doc_ids: Set[str] = {p.document_id for p in base_passages}

        # 2. Traverse Precedent DAG for each retrieved document
        for passage in base_passages:
            if not passage.go_number:
                continue

            norm_key = self.dag.normalize_order_number(passage.go_number)

            # Check for superseding orders
            terminal_node, chain = self.dag.resolve_active_terminal_order(
                order_number=passage.go_number,
                max_hops=max_graph_hops,
            )

            # If order was superseded, mark passage currency status
            if len(chain) > 1:
                passage.currency_status = "SUPERSEDED"
                passage.has_conflict = True
                passage.conflict_notes = f"SUPERSEDED by {terminal_node.order_number}"

                # Retrieve chunks for the active terminal order if not already in result set
                if terminal_node.document_id not in seen_doc_ids:
                    graph_chunks = self._fetch_document_chunks(terminal_node.document_id)
                    for gc in graph_chunks:
                        if gc.chunk_id not in seen_chunk_ids:
                            gc.is_superseding = True
                            gc.currency_status = "CURRENT"
                            gc.score = passage.score + 0.05  # Prioritize current superseding record
                            expanded_passages.append(gc)
                            seen_chunk_ids.add(gc.chunk_id)
                    seen_doc_ids.add(terminal_node.document_id)

            # Check for amending orders
            amendments = self.dag.get_amendment_chain(passage.go_number)
            for amend_node in amendments:
                if amend_node.document_id not in seen_doc_ids:
                    graph_chunks = self._fetch_document_chunks(amend_node.document_id)
                    for gc in graph_chunks:
                        if gc.chunk_id not in seen_chunk_ids:
                            gc.is_amending = True
                            gc.score = passage.score * 0.95
                            expanded_passages.append(gc)
                            seen_chunk_ids.add(gc.chunk_id)
                    seen_doc_ids.add(amend_node.document_id)

        # Sort expanded passages by score descending
        expanded_passages.sort(key=lambda p: getattr(p, "score", 0.0), reverse=True)
        return expanded_passages[: top_k + 4]

    def _fetch_document_chunks(self, document_id: str) -> List[EvidencePassage]:
        """Fetch high-scoring chunks for a graph-discovered document."""
        from adam.db.models import Document, DocumentChunk, DocumentVersion

        chunks = (
            self.session.query(DocumentChunk, DocumentVersion, Document)
            .join(DocumentVersion, DocumentChunk.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .filter(Document.id == document_id)
            .limit(2)
            .all()
        )

        passages = []
        for chk, ver, doc in chunks:
            passages.append(
                EvidencePassage(
                    chunk_id=chk.id,
                    document_id=doc.id,
                    version_id=ver.id,
                    title=doc.title,
                    department_id=doc.department_id,
                    doc_type=doc.doc_type,
                    page_start=chk.page_start,
                    page_end=chk.page_end,
                    section_heading=chk.section_heading or "General",
                    content=chk.content,
                    score=0.85,
                    go_number=ver.go_number,
                    source_url=ver.source_url,
                )
            )
        return passages
