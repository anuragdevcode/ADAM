"""Precedent and Supersession DAG Engine for Uttarakhand Administrative Records.

Models Government Orders, notifications, and statutory rules as a directed acyclic
graph (DAG) to resolve multi-hop amendment chains, transitive supersessions, and
currency status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RelationType(StrEnum):
    """Statutory relationship types between administrative instruments."""
    SUPERSEDES = "SUPERSEDES"
    AMENDS = "AMENDS"
    REPEALS = "REPEALS"
    CORRIGENDUM = "CORRIGENDUM"
    CITES = "CITES"
    REFERS_TO = "REFERS_TO"


@dataclass
class PrecedentNode:
    """A node representing a specific Government Order, statutory rule, or gazette."""
    document_id: str
    order_number: str
    title: str
    department_id: Optional[str] = None
    order_date: Optional[date] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_active: bool = True
    is_superseded: bool = False
    superseded_by_order: Optional[str] = None
    superseded_date: Optional[date] = None


@dataclass
class PrecedentEdge:
    """A directed relationship edge from source order to target order."""
    source_order: str
    target_order: str
    relation_type: RelationType
    raw_citation: Optional[str] = None
    effective_date: Optional[date] = None


class PrecedentDAG:
    """Directed Acyclic Graph modeling legal relations across Uttarakhand Government Orders."""

    def __init__(self):
        self.nodes: Dict[str, PrecedentNode] = {}  # keyed by clean normalized order_number
        self.outgoing_edges: Dict[str, List[PrecedentEdge]] = {}  # source -> edges
        self.incoming_edges: Dict[str, List[PrecedentEdge]] = {}  # target -> edges

    @classmethod
    def normalize_order_number(cls, num: Optional[str]) -> str:
        """Normalize order number for invariant graph lookup."""
        if not num:
            return ""
        return num.strip().upper().replace(" ", "")

    def add_node(self, node: PrecedentNode) -> None:
        """Register a node in the precedent graph."""
        norm_key = self.normalize_order_number(node.order_number)
        if norm_key:
            self.nodes[norm_key] = node
            self.outgoing_edges.setdefault(norm_key, [])
            self.incoming_edges.setdefault(norm_key, [])

    def add_edge(
        self,
        source_order: str,
        target_order: str,
        relation_type: RelationType,
        raw_citation: Optional[str] = None,
        effective_date: Optional[date] = None,
    ) -> None:
        """Add a directed edge between two orders."""
        src_key = self.normalize_order_number(source_order)
        tgt_key = self.normalize_order_number(target_order)

        if not src_key or not tgt_key:
            return

        edge = PrecedentEdge(
            source_order=src_key,
            target_order=tgt_key,
            relation_type=relation_type,
            raw_citation=raw_citation,
            effective_date=effective_date,
        )

        self.outgoing_edges.setdefault(src_key, []).append(edge)
        self.incoming_edges.setdefault(tgt_key, []).append(edge)

        # Automatically update supersession status on target node
        if relation_type in (RelationType.SUPERSEDES, RelationType.REPEALS):
            if tgt_key in self.nodes:
                self.nodes[tgt_key].is_superseded = True
                self.nodes[tgt_key].is_active = False
                self.nodes[tgt_key].superseded_by_order = src_key
                self.nodes[tgt_key].superseded_date = effective_date

    def resolve_active_terminal_order(self, order_number: str, max_hops: int = 5) -> Tuple[PrecedentNode, List[str]]:
        """Transitively traverse supersession edges to find the currently active terminal order.

        Returns:
            Tuple of (terminal_node, chain_of_superseding_orders)
        """
        current_key = self.normalize_order_number(order_number)
        chain = [current_key]
        visited = {current_key}

        for _ in range(max_hops):
            # Check incoming superseding edges (orders that supersede current_key)
            inc = self.incoming_edges.get(current_key, [])
            superseding_edges = [
                e for e in inc if e.relation_type in (RelationType.SUPERSEDES, RelationType.REPEALS)
            ]

            if not superseding_edges:
                break

            # Pick the most recent superseding order
            next_edge = max(
                superseding_edges,
                key=lambda e: e.effective_date or date.min,
            )
            next_key = next_edge.source_order

            if next_key in visited:
                logger.warning("Supersession cycle detected involving %s", next_key)
                break

            visited.add(next_key)
            chain.append(next_key)
            current_key = next_key

        terminal_node = self.nodes.get(current_key)
        if not terminal_node:
            terminal_node = PrecedentNode(
                document_id="unregistered",
                order_number=current_key,
                title=f"Order {current_key}",
            )
        return terminal_node, chain

    def get_amendment_chain(self, order_number: str) -> List[PrecedentNode]:
        """Retrieve all orders that amend the specified order, sorted chronologically."""
        norm_key = self.normalize_order_number(order_number)
        inc = self.incoming_edges.get(norm_key, [])
        amend_edges = [
            e for e in inc if e.relation_type in (RelationType.AMENDS, RelationType.CORRIGENDUM)
        ]

        amend_nodes = []
        for e in amend_edges:
            node = self.nodes.get(e.source_order)
            if node:
                amend_nodes.append(node)

        # Sort chronologically by order_date
        amend_nodes.sort(key=lambda n: n.order_date or date.min)
        return amend_nodes

    def build_currency_banner(self, order_number: str) -> Optional[str]:
        """Generate official Currency Notice banner if the order is superseded."""
        norm_key = self.normalize_order_number(order_number)
        node = self.nodes.get(norm_key)
        if not node or not node.is_superseded:
            # Check transitive supersession
            terminal_node, chain = self.resolve_active_terminal_order(order_number)
            if len(chain) <= 1:
                return None
            superseding = terminal_node.order_number
            date_str = f" effective {terminal_node.effective_from}" if terminal_node.effective_from else ""
            return f"CURRENCY NOTICE: {order_number} has been SUPERSEDED by {superseding}{date_str}."

        superseding = node.superseded_by_order or "a subsequent government order"
        date_str = f" dated {node.superseded_date}" if node.superseded_date else ""
        return f"CURRENCY NOTICE: {order_number} has been SUPERSEDED by {superseding}{date_str}."

    @classmethod
    def build_from_database(
        cls,
        session: Session,
        seed_order_numbers: Optional[List[str]] = None,
        max_depth: int = 3,
    ) -> PrecedentDAG:
        """Populate PrecedentDAG directly from database records."""
        from adam.db.models import Document, DocumentVersion, PrecedentReference

        dag = cls()

        # Query all precedent references
        query = session.query(PrecedentReference).join(
            DocumentVersion, PrecedentReference.source_version_id == DocumentVersion.id
        )

        refs = query.all()
        for ref in refs:
            source_ver = ref.source_version
            source_doc = source_ver.document if source_ver else None

            # Add source node
            if source_ver and source_ver.go_number:
                dag.add_node(
                    PrecedentNode(
                        document_id=source_doc.id if source_doc else source_ver.document_id,
                        order_number=source_ver.go_number,
                        title=source_doc.title if source_doc else source_ver.go_number,
                        department_id=source_doc.department_id if source_doc else None,
                        order_date=getattr(source_ver, "order_date", None),
                    )
                )

            # Add target node if document exists
            target_doc = ref.target_document
            target_order = ref.cited_order_number
            if target_doc and target_doc.current_version:
                target_ver = target_doc.current_version
                target_order = target_ver.go_number or target_order
                dag.add_node(
                    PrecedentNode(
                        document_id=target_doc.id,
                        order_number=target_order or target_doc.id,
                        title=target_doc.title,
                        department_id=target_doc.department_id,
                    )
                )
            elif target_order:
                dag.add_node(
                    PrecedentNode(
                        document_id=f"ref_{target_order}",
                        order_number=target_order,
                        title=f"Government Order {target_order}",
                    )
                )

            # Add edge
            if source_ver and source_ver.go_number and target_order:
                rel = RelationType(ref.relation_type) if ref.relation_type in RelationType._value2member_map_ else RelationType.REFERS_TO
                dag.add_edge(
                    source_order=source_ver.go_number,
                    target_order=target_order,
                    relation_type=rel,
                    raw_citation=ref.raw_citation_text,
                    effective_date=ref.cited_date,
                )

        return dag
