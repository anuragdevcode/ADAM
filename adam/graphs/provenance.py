"""Claim-to-Pixel Provenance Graph for Sovereign Administrative Transparency.

Connects every synthesized statement and material claim (dates, amounts, rule numbers)
through an unbroken DAG of evidence passages, document versions, page numbers, and
exact PDF text block bounding boxes [x0, y0, x1, y1].
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional, Set, Tuple

from adam.rag.generator import CitationValidator
from adam.rag.models import Citation, EvidencePacket, EvidencePassage

logger = logging.getLogger(__name__)


class ProvenanceNodeType(StrEnum):
    """Categorization of entities within the provenance DAG."""
    CLAIM = "CLAIM"
    PASSAGE = "PASSAGE"
    DOCUMENT = "DOCUMENT"
    PAGE = "PAGE"
    BLOCK = "BLOCK"


@dataclass
class ProvenanceNode:
    """An individual entity node in the provenance trace."""
    node_id: str
    node_type: ProvenanceNodeType
    label: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvenanceEdge:
    """A directed grounding relationship."""
    source_id: str
    target_id: str
    relation: str  # GROUNDS, CONTAINS, LOCATED_ON, BOUNDED_BY


@dataclass
class ProvenanceTraceResult:
    """Consolidated claim-to-pixel provenance trace."""
    total_claims: int
    grounded_claims: int
    coverage_ratio: float
    nodes: List[ProvenanceNode] = field(default_factory=list)
    edges: List[ProvenanceEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "grounded_claims": self.grounded_claims,
            "coverage_ratio": round(self.coverage_ratio, 2),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": [
                {"id": n.node_id, "type": str(n.node_type.value), "label": n.label, "metadata": n.metadata}
                for n in self.nodes
            ],
            "edges": [
                {"source": e.source_id, "target": e.target_id, "relation": e.relation}
                for e in self.edges
            ],
        }

    def to_mermaid(self) -> str:
        """Render the provenance graph as a standard Mermaid diagram."""
        lines = ["flowchart TD"]
        for n in self.nodes:
            clean_label = re.sub(r'["\n]', " ", n.label)[:40].strip()
            lines.append(f'    {n.node_id}["{clean_label} ({n.node_type.value})"]')

        for e in self.edges:
            lines.append(f"    {e.source_id} -->|{e.relation}| {e.target_id}")

        return "\n".join(lines)


class ProvenanceGraph:
    """Constructs and queries the end-to-end claim-to-pixel provenance graph."""

    @classmethod
    def build_trace(
        cls,
        answer: str,
        packet: EvidencePacket,
    ) -> ProvenanceTraceResult:
        """Build a complete provenance DAG linking answer claims down to PDF page blocks."""
        claims = CitationValidator.extract_material_claims(answer)
        nodes: Dict[str, ProvenanceNode] = {}
        edges: List[ProvenanceEdge] = []

        grounded_count = 0

        # 1. Register Passage, Document, Page, and Block nodes
        for idx, passage in enumerate(packet.passages, start=1):
            passage_id = f"passage_{idx}"
            nodes[passage_id] = ProvenanceNode(
                node_id=passage_id,
                node_type=ProvenanceNodeType.PASSAGE,
                label=f"Passage [{idx}]: {passage.title[:30]}",
                metadata={
                    "chunk_id": passage.chunk_id,
                    "go_number": passage.go_number,
                    "department": passage.department_id,
                },
            )

            # Document Node
            doc_id = f"doc_{passage.document_id}"
            if doc_id not in nodes:
                nodes[doc_id] = ProvenanceNode(
                    node_id=doc_id,
                    node_type=ProvenanceNodeType.DOCUMENT,
                    label=f"Doc: {passage.title[:30]}",
                    metadata={"document_id": passage.document_id, "go_number": passage.go_number},
                )
            edges.append(ProvenanceEdge(passage_id, doc_id, "CONTAINS"))

            # Page Node
            page_id = f"page_{passage.document_id}_{passage.page_start}"
            if page_id not in nodes:
                nodes[page_id] = ProvenanceNode(
                    node_id=page_id,
                    node_type=ProvenanceNodeType.PAGE,
                    label=f"Page {passage.page_start}",
                    metadata={"page_number": passage.page_start, "document_id": passage.document_id},
                )
            edges.append(ProvenanceEdge(passage_id, page_id, "LOCATED_ON"))

            # Block Bounding Box Nodes (if available)
            if passage.bbox_list:
                for b_idx, bbox in enumerate(passage.bbox_list[:3]):
                    block_id = f"block_{passage.chunk_id}_{b_idx}"
                    nodes[block_id] = ProvenanceNode(
                        node_id=block_id,
                        node_type=ProvenanceNodeType.BLOCK,
                        label=f"BBox {bbox}",
                        metadata={"bbox": bbox},
                    )
                    edges.append(ProvenanceEdge(page_id, block_id, "BOUNDED_BY"))

        # 2. Extract and link Claims
        for c_idx, (claim_type, claim_val) in enumerate(claims, start=1):
            claim_id = f"claim_{c_idx}"
            clean_val = claim_val.lower().strip()

            claim_node = ProvenanceNode(
                node_id=claim_id,
                node_type=ProvenanceNodeType.CLAIM,
                label=f"{claim_type}: {claim_val}",
                metadata={"claim_type": claim_type, "value": claim_val},
            )
            nodes[claim_id] = claim_node

            is_claim_grounded = False
            for p_idx, passage in enumerate(packet.passages, start=1):
                p_text = (passage.content + " " + (passage.go_number or "")).lower()
                digits = re.findall(r"\d+", claim_val)
                if clean_val in p_text or (digits and all(d in p_text for d in digits)):
                    passage_id = f"passage_{p_idx}"
                    edges.append(ProvenanceEdge(claim_id, passage_id, "GROUNDS"))
                    is_claim_grounded = True

            if is_claim_grounded:
                grounded_count += 1

        total_claims = len(claims)
        coverage = (grounded_count / total_claims) if total_claims > 0 else 1.0

        return ProvenanceTraceResult(
            total_claims=total_claims,
            grounded_claims=grounded_count,
            coverage_ratio=coverage,
            nodes=list(nodes.values()),
            edges=edges,
        )
