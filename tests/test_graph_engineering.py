"""Comprehensive Unit Tests for ADAM Graph Engineering Framework.

Validates:
1. Declarative StateGraph compilation, node transitions, and conditional edge routing.
2. Precedent & Supersession DAG with multi-hop transitive resolution and currency alerts.
3. Graph RAG retrieval augmenting base passages with legal graph neighbors.
4. Claim-to-Pixel Provenance Graph connecting claims down to PDF page blocks.
"""

from datetime import date
from unittest.mock import MagicMock
import pytest

from adam.graphs.precedents import (
    PrecedentDAG,
    PrecedentNode,
    RelationType,
)
from adam.graphs.provenance import (
    ProvenanceGraph,
    ProvenanceNodeType,
    ProvenanceTraceResult,
)
from adam.graphs.retrieval import GraphRAGRetriever
from adam.graphs.stategraph import (
    END,
    START,
    CompiledStateGraph,
    NodeExecutionRecord,
    StateGraph,
    StateGraphResult,
)
from adam.rag.models import EvidencePacket, EvidencePassage, ParsedQuery, UserContext


# ── 1. Declarative StateGraph Workflow Tests ─────────────────────────────────

def test_stategraph_linear_pipeline_execution():
    """Verify linear node-to-node execution in StateGraph."""
    graph = StateGraph()

    def step_a(state):
        return {"val": state.get("val", 0) + 1, "path": state.get("path", []) + ["A"]}

    def step_b(state):
        return {"val": state["val"] * 2, "path": state["path"] + ["B"]}

    graph.add_node("node_a", step_a)
    graph.add_node("node_b", step_b)
    graph.set_entry_point("node_a")
    graph.add_edge("node_a", "node_b")
    graph.set_finish_point("node_b")

    compiled = graph.compile()
    res = compiled.invoke({"val": 5})

    assert res.execution_path == ["node_a", "node_b"]
    assert res.final_state["val"] == 12  # (5 + 1) * 2
    assert res.final_state["path"] == ["A", "B"]
    assert res.total_steps == 2
    assert res.terminated_early is False


def test_stategraph_conditional_edge_routing():
    """Verify dynamic routing based on state conditions."""
    graph = StateGraph()

    def classifier(state):
        intent = "calc" if "calculate" in state.get("query", "") else "rag"
        return {"intent": intent}

    def calc_node(state):
        return {"result": 42}

    def rag_node(state):
        return {"result": "found records"}

    graph.add_node("classify", classifier)
    graph.add_node("calc", calc_node)
    graph.add_node("rag", rag_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        router_fn=lambda s: s["intent"],
        path_map={"calc": "calc", "rag": "rag"},
    )
    graph.set_finish_point("calc")
    graph.set_finish_point("rag")

    compiled = graph.compile()

    # Route to calculation
    res1 = compiled.invoke({"query": "calculate salary"})
    assert res1.execution_path == ["classify", "calc"]
    assert res1.final_state["result"] == 42

    # Route to RAG
    res2 = compiled.invoke({"query": "search orders"})
    assert res2.execution_path == ["classify", "rag"]
    assert res2.final_state["result"] == "found records"


def test_stategraph_max_steps_guard():
    """Verify that circular edges are safely terminated by max_steps ceiling."""
    graph = StateGraph()

    def loop_node(state):
        return {"count": state.get("count", 0) + 1}

    graph.add_node("loop", loop_node)
    graph.set_entry_point("loop")
    graph.add_edge("loop", "loop")  # cycle

    compiled = graph.compile()
    res = compiled.invoke({"count": 0}, max_steps=5)

    assert res.terminated_early is True
    assert res.total_steps == 5
    assert "step ceiling reached" in res.termination_reason


# ── 2. Precedent and Supersession DAG Tests ──────────────────────────────────

def test_precedent_dag_transitive_supersession():
    """Verify multi-hop transitive supersession: Order 1 -> Order 2 -> Order 3."""
    dag = PrecedentDAG()

    dag.add_node(PrecedentNode("doc1", "GO/2018/100", "Initial Procurement Limit", order_date=date(2018, 1, 1)))
    dag.add_node(PrecedentNode("doc2", "GO/2021/200", "Revised Procurement Limit", order_date=date(2021, 6, 1)))
    dag.add_node(PrecedentNode("doc3", "GO/2024/300", "Current Procurement Limit", order_date=date(2024, 3, 1)))

    # Order 2 supersedes Order 1
    dag.add_edge("GO/2021/200", "GO/2018/100", RelationType.SUPERSEDES, effective_date=date(2021, 6, 1))
    # Order 3 supersedes Order 2
    dag.add_edge("GO/2024/300", "GO/2021/200", RelationType.SUPERSEDES, effective_date=date(2024, 3, 1))

    # Resolving original Order 1 must yield active terminal Order 3!
    terminal, chain = dag.resolve_active_terminal_order("GO/2018/100")
    assert terminal.order_number == "GO/2024/300"
    assert len(chain) == 3
    assert chain == ["GO/2018/100", "GO/2021/200", "GO/2024/300"]

    # Currency banner verification
    banner = dag.build_currency_banner("GO/2018/100")
    assert banner is not None
    assert "GO/2018/100 has been SUPERSEDED by GO/2021/200" in banner or "GO/2024/300" in banner


def test_precedent_dag_amendment_chain_chronological():
    """Verify retrieval of amendment orders sorted chronologically."""
    dag = PrecedentDAG()
    dag.add_node(PrecedentNode("doc_base", "GO/RULES/2015", "Base Service Rules", order_date=date(2015, 1, 1)))
    dag.add_node(PrecedentNode("doc_amend2", "GO/AMEND/2022", "Second Amendment", order_date=date(2022, 5, 1)))
    dag.add_node(PrecedentNode("doc_amend1", "GO/AMEND/2018", "First Amendment", order_date=date(2018, 3, 1)))

    dag.add_edge("GO/AMEND/2022", "GO/RULES/2015", RelationType.AMENDS)
    dag.add_edge("GO/AMEND/2018", "GO/RULES/2015", RelationType.AMENDS)

    amendments = dag.get_amendment_chain("GO/RULES/2015")
    assert len(amendments) == 2
    # Must be sorted chronologically: 2018 first, then 2022
    assert amendments[0].order_number == "GO/AMEND/2018"
    assert amendments[1].order_number == "GO/AMEND/2022"


# ── 3. Graph RAG Retrieval Tests ─────────────────────────────────────────────

def test_graph_rag_expands_superseded_passage():
    """Verify GraphRAGRetriever enriches passages with graph-discovered superseding orders."""
    dag = PrecedentDAG()
    dag.add_node(PrecedentNode("doc_old", "GO/2018/10", "Old Order", order_date=date(2018, 1, 1)))
    dag.add_node(PrecedentNode("doc_new", "GO/2023/50", "New Order", order_date=date(2023, 1, 1)))
    dag.add_edge("GO/2023/50", "GO/2018/10", RelationType.SUPERSEDES, effective_date=date(2023, 1, 1))

    # Mock base retriever returning only the old passage
    old_passage = EvidencePassage(
        chunk_id="chk_old",
        document_id="doc_old",
        version_id="v1",
        title="Old Order",
        department_id="FIN",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="Limits",
        content="Old limit is 25000.",
        go_number="GO/2018/10",
        score=0.80,
    )
    mock_base = MagicMock()
    mock_base.retrieve.return_value = [old_passage]

    # GraphRAGRetriever
    mock_session = MagicMock()
    graph_retriever = GraphRAGRetriever(
        session=mock_session,
        base_retriever=mock_base,
        precedent_dag=dag,
    )

    # Mock fetching chunks for the new document
    new_passage = EvidencePassage(
        chunk_id="chk_new",
        document_id="doc_new",
        version_id="v2",
        title="New Order",
        department_id="FIN",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="Limits",
        content="New limit is 50000.",
        go_number="GO/2023/50",
    )
    graph_retriever._fetch_document_chunks = MagicMock(return_value=[new_passage])

    results = graph_retriever.retrieve(ParsedQuery(raw_query="limit", clean_query="limit"))

    assert len(results) == 2
    # The old passage must be marked as SUPERSEDED
    assert old_passage.currency_status == "SUPERSEDED"
    assert old_passage.has_conflict is True
    # The new passage must be included and marked as superseding
    assert new_passage in results
    assert new_passage.is_superseding is True


# ── 4. Claim-to-Pixel Provenance Graph Tests ─────────────────────────────────

def test_provenance_graph_trace_construction():
    """Verify construction of claim-to-pixel provenance DAG."""
    passage = EvidencePassage(
        chunk_id="chk_prov_1",
        document_id="doc_prov_1",
        version_id="ver_prov_1",
        title="Finance GO 2024",
        department_id="FINANCE",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="DA Rate",
        content="DA rate is 50% sanctioned under GO/FIN/2024/89 on 15 March 2024.",
        go_number="GO/FIN/2024/89",
        bbox_list=[[50, 50, 400, 100], [50, 120, 400, 180]],
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="DA rate", clean_query="DA rate"),
        passages=[passage],
    )

    answer = "Under GO/FIN/2024/89, the Dearness Allowance rate was fixed at 50% on 15 March 2024."
    trace: ProvenanceTraceResult = ProvenanceGraph.build_trace(answer, packet)

    assert trace.total_claims >= 2  # 50%, 15 March 2024, GO/FIN/2024/89
    assert trace.grounded_claims >= 2
    assert trace.coverage_ratio == 1.0  # 100% grounded

    # Check node categories
    node_types = {n.node_type for n in trace.nodes}
    assert ProvenanceNodeType.CLAIM in node_types
    assert ProvenanceNodeType.PASSAGE in node_types
    assert ProvenanceNodeType.DOCUMENT in node_types
    assert ProvenanceNodeType.PAGE in node_types
    assert ProvenanceNodeType.BLOCK in node_types

    # Check edge connections
    relations = {e.relation for e in trace.edges}
    assert "GROUNDS" in relations
    assert "CONTAINS" in relations
    assert "LOCATED_ON" in relations
    assert "BOUNDED_BY" in relations

    # Check Mermaid rendering
    mermaid = trace.to_mermaid()
    assert "flowchart TD" in mermaid
    assert "GROUNDS" in mermaid
    assert "BOUNDED_BY" in mermaid
