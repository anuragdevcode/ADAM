"""ADAM Graph Engineering Framework.

Provides declarative StateGraph workflow execution, multi-hop statutory Precedent DAGs,
Graph-augmented retrieval (Graph RAG), and end-to-end claim-to-pixel provenance graphs.
"""

from adam.graphs.stategraph import (
    END,
    START,
    CompiledStateGraph,
    ConditionalEdge,
    NodeExecutionRecord,
    StateGraph,
    StateGraphResult,
)
from adam.graphs.precedents import (
    PrecedentDAG,
    PrecedentEdge,
    PrecedentNode,
    RelationType,
)
from adam.graphs.retrieval import GraphRAGRetriever
from adam.graphs.provenance import (
    ProvenanceEdge,
    ProvenanceGraph,
    ProvenanceNode,
    ProvenanceNodeType,
    ProvenanceTraceResult,
)

__all__ = [
    "START",
    "END",
    "StateGraph",
    "CompiledStateGraph",
    "ConditionalEdge",
    "NodeExecutionRecord",
    "StateGraphResult",
    "PrecedentDAG",
    "PrecedentNode",
    "PrecedentEdge",
    "RelationType",
    "GraphRAGRetriever",
    "ProvenanceGraph",
    "ProvenanceNode",
    "ProvenanceNodeType",
    "ProvenanceEdge",
    "ProvenanceTraceResult",
]
