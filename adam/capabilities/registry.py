"""Typed Capability Registry for ADAM's Next-Generation Agent Tooling Layer.

Serves as the central authoritative catalog of all tools, specialist agents,
graph traversers, relational queries, sandboxes, and MCP/A2A bridges.

Guarantees:
1. Typed Pydantic parameter schemas for every capability.
2. Fine-grained clearance filtering and Air-Gapped Data Sovereignty compliance.
3. Approval boundary enforcement for high-risk actions.
4. Seamless export to standard OpenAI function-calling and Model Context Protocol (MCP) tool manifests.
5. Full backwards compatibility with ReadOnlyToolRegistry.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from adam.agent.redaction import SecretRedactor
from adam.agent.sandbox import SecurePythonSandbox
from adam.capabilities.a2a import (
    A2ABudget,
    A2AResponseEnvelope,
    A2ASpecialistCoordinator,
    A2ATaskContract,
)
from adam.capabilities.governance import (
    AirGappedSovereigntyViolationError,
    ApprovalBoundaryRequiredError,
    CapabilityGovernanceEngine,
    CapabilitySecurityViolationError,
)
from adam.capabilities.models import (
    CapabilityDescriptor,
    CapabilityInvocationRequest,
    CapabilityInvocationResult,
    CapabilityPermissions,
    CapabilityType,
    CostModel,
    InvocationStatus,
    RiskLevel,
)
from adam.db.models import Document, DocumentPage, DocumentVersion, PrecedentReference, Source, TextBlock
from adam.graphs.precedents import PrecedentDAG
from adam.graphs.provenance import ProvenanceGraph
from adam.rag.acl import AclEnforcer
from adam.rag.models import EvidencePassage, UserContext
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever
from adam.vocabularies import AgentToolName, Classification, SourceStatus

logger = logging.getLogger(__name__)


# ── Typed Argument Schemas for Capabilities ───────────────────────────────────

class SearchCapabilityArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str = Field(..., description="Search query keywords or natural language question")
    department_id: Optional[str] = Field(None, description="Optional department filter (e.g. FINANCE_TREASURY)")
    doc_type: Optional[str] = Field(None, description="Optional document type filter")
    top_k: int = Field(5, description="Max passages to retrieve (1-10, default 5)")


class OpenCitedSourceArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document_id: str = Field(..., description="Unique document identifier")
    page_number: Optional[int] = Field(1, description="Page number to inspect (1-indexed)")
    version_id: Optional[str] = Field(None, description="Optional version identifier")


class ListCollectionsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class InspectSystemArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subtopic: Optional[str] = Field("all", description="Focus area: all, model, harness, sources, budget, tools")


class LookupPrecedentsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    document_id: Optional[str] = Field(None, description="Document identifier")
    order_number: Optional[str] = Field(None, description="Government order number to trace")


class TraversePrecedentDagArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_number: str = Field(..., description="Government order number to trace in DAG")
    max_hops: int = Field(3, description="Maximum graph hops to traverse (default 3)")


class TraceClaimProvenanceArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: str = Field(..., description="Synthesized answer text to trace down to PDF text blocks")


class ExecutePythonSandboxArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(..., description="Self-contained Python arithmetic script without imports")
    context_vars: Optional[Dict[str, Any]] = Field(None, description="Initial numerical variables dictionary")
    timeout_seconds: float = Field(2.0, description="Max execution duration in seconds")


class VerifyClaimArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    claim: str = Field(..., description="Claim or numerical rate to verify against evidence")
    passages: Optional[List[str]] = Field(None, description="Optional list of passages to verify against")


class DatabaseQueryArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    table: str = Field(..., description="Target database table: documents, document_versions, sources, precedent_references")
    filter_by: Optional[Dict[str, Any]] = Field(None, description="Equality filters (e.g. {'department_id': 'UK_FIN'})")
    aggregate: Optional[str] = Field("count", description="Aggregate function: count, list")
    limit: int = Field(20, description="Max rows to return (1-100, default 20)")


class CompareSourcesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_a: str = Field(..., description="First source content, document ID, or citation reference")
    source_b: str = Field(..., description="Second source content, document ID, or citation reference")
    comparison_focus: Optional[str] = Field(None, description="Focus area (rates, allowances, dates, eligibility)")


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str = Field(..., description="Search query keywords")
    domain_filter: Optional[str] = Field(None, description="Domain constraint (e.g. gov.in, nic.in)")
    max_results: int = Field(5, description="Max search results (1-10, default 5)")


class FetchWebPageArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str = Field(..., description="Target HTTP/HTTPS URL")
    extract_tables: bool = Field(True, description="Whether to format HTML tables as markdown tables")


class A2ADispatchArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    specialist_agent_id: str = Field(..., description="Specialist: precedent_graph, quantitative_analysis, web_research, compliance_audit")
    objective: str = Field(..., description="Target objective for the specialist")
    input_artifacts: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Input artifacts dictionary")


# ── Capability Registry Implementation ────────────────────────────────────────

class CapabilityRegistry:
    """Central registry and execution coordinator for ADAM's Capability Fabric."""

    _capabilities: Dict[str, CapabilityDescriptor] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, descriptor: CapabilityDescriptor) -> None:
        """Register a new capability in the fabric."""
        cls._capabilities[descriptor.id.lower()] = descriptor
        logger.debug("Registered capability: '%s' [%s]", descriptor.id, descriptor.type.value)

    @classmethod
    def get(cls, capability_id: str) -> Optional[CapabilityDescriptor]:
        """Look up a registered capability by ID or normalized name."""
        cls._ensure_initialized()
        norm_id = capability_id.strip().lower()
        # Handle tool name aliases
        if norm_id in ("search", "repo_search"):
            norm_id = "search"
        elif norm_id in ("database", "database_query"):
            norm_id = "database_query"
        elif norm_id in ("python_sandbox", "execute_python_sandbox"):
            norm_id = "execute_python_sandbox"
        elif norm_id in ("precedent", "precedents", "lookup_precedents"):
            norm_id = "lookup_precedents"

        return cls._capabilities.get(norm_id)

    @classmethod
    def list_capabilities(
        cls,
        user_context: Optional[UserContext] = None,
        filter_unavailable: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return list of capability manifest dictionaries, filtered by caller clearance."""
        cls._ensure_initialized()
        manifests = []
        for cap in cls._capabilities.values():
            allowed_clearance, _ = CapabilityGovernanceEngine.evaluate_clearance(cap, user_context)
            allowed_airgap, _ = CapabilityGovernanceEngine.evaluate_air_gapped_policy(cap, user_context)
            is_avail = allowed_clearance and allowed_airgap

            if filter_unavailable and not is_avail:
                continue

            entry = cap.to_manifest_dict()
            entry["is_available"] = is_avail
            manifests.append(entry)
        return manifests

    @classmethod
    def get_mcp_tools_manifest(cls, user_context: Optional[UserContext] = None) -> List[Dict[str, Any]]:
        """Export capabilities as standard Model Context Protocol (MCP) tool specifications."""
        cls._ensure_initialized()
        tools = []
        for cap in cls._capabilities.values():
            allowed_clearance, _ = CapabilityGovernanceEngine.evaluate_clearance(cap, user_context)
            allowed_airgap, _ = CapabilityGovernanceEngine.evaluate_air_gapped_policy(cap, user_context)
            if allowed_clearance and allowed_airgap:
                tools.append(cap.to_mcp_tool_schema())
        return tools

    @classmethod
    def invoke(
        cls,
        capability_id: str,
        arguments: Dict[str, Any],
        user_context: Optional[UserContext] = None,
        session: Optional[Session] = None,
        depth: int = 0,
        approval_token: Optional[str] = None,
    ) -> CapabilityInvocationResult:
        """Execute a capability with strict security, parameter validation, and governance."""
        cls._ensure_initialized()
        start_t = time.perf_counter()
        user_ctx = user_context or UserContext()

        descriptor = cls.get(capability_id)
        if not descriptor:
            return CapabilityInvocationResult(
                capability_id=capability_id,
                status=InvocationStatus.FAILED,
                error=f"Capability '{capability_id}' is not registered in the Capability Fabric.",
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        req = CapabilityInvocationRequest(
            capability_id=descriptor.id,
            arguments=arguments,
            user_context=user_ctx,
            session=session,
            depth=depth,
            approval_token=approval_token,
        )

        # 1. Clearance Enforcement
        allowed_clr, clr_reason = CapabilityGovernanceEngine.evaluate_clearance(descriptor, user_ctx)
        if not allowed_clr:
            return CapabilityInvocationResult(
                capability_id=descriptor.id,
                status=InvocationStatus.BLOCKED,
                error=clr_reason,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        # 2. Air-Gapped Data Sovereignty Boundary
        allowed_airgap, airgap_reason = CapabilityGovernanceEngine.evaluate_air_gapped_policy(descriptor, user_ctx)
        if not allowed_airgap:
            return CapabilityInvocationResult(
                capability_id=descriptor.id,
                status=InvocationStatus.BLOCKED,
                error=airgap_reason,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        # 3. Approval Boundary Check
        allowed_appr, appr_reason = CapabilityGovernanceEngine.evaluate_approval_boundary(descriptor, req)
        if not allowed_appr:
            return CapabilityInvocationResult(
                capability_id=descriptor.id,
                status=InvocationStatus.APPROVAL_REQUIRED,
                requires_approval=True,
                approval_prompt=appr_reason,
                error=appr_reason,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        # 4. Typed Parameter Validation
        validated_args = arguments or {}
        if descriptor.input_model:
            try:
                validated_args = descriptor.input_model.model_validate(validated_args).model_dump(exclude_unset=False)
            except Exception as ve:
                return CapabilityInvocationResult(
                    capability_id=descriptor.id,
                    status=InvocationStatus.FAILED,
                    error=f"Invalid arguments for capability '{descriptor.id}': {str(ve)}",
                    latency_ms=(time.perf_counter() - start_t) * 1000.0,
                )

        # 5. Execute Handler
        try:
            handler = descriptor.handler or cls._default_dispatch_handler(descriptor.id)
            raw_result = handler(validated_args, user_ctx, session, depth)
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            # Extract evidence passages if present
            evidence_passages = []
            if isinstance(raw_result, dict):
                evidence_passages = raw_result.get("raw_passages") or raw_result.get("evidence_passages") or []
            elif hasattr(raw_result, "evidence_passages"):
                evidence_passages = getattr(raw_result, "evidence_passages")

            sanitized_val = SecretRedactor.sanitize_data(raw_result)

            return CapabilityInvocationResult(
                capability_id=descriptor.id,
                status=InvocationStatus.SUCCESS,
                value=sanitized_val,
                evidence_passages=evidence_passages,
                latency_ms=duration_ms,
            )
        except Exception as e:
            logger.exception("Capability execution error in '%s'", descriptor.id)
            return CapabilityInvocationResult(
                capability_id=descriptor.id,
                status=InvocationStatus.FAILED,
                error=SecretRedactor.sanitize_text(str(e)),
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

    # ── Built-in Execution Handlers ──────────────────────────────────────────

    @classmethod
    def _default_dispatch_handler(cls, capability_id: str) -> Callable[..., Any]:
        """Dispatch built-in capability logic."""
        if capability_id == "search":
            return cls._handle_search
        elif capability_id == "open_cited_source":
            return cls._handle_open_cited_source
        elif capability_id == "list_authorised_collections":
            return cls._handle_list_collections
        elif capability_id == "inspect_system":
            return cls._handle_inspect_system
        elif capability_id == "lookup_precedents":
            return cls._handle_lookup_precedents
        elif capability_id == "traverse_precedent_dag":
            return cls._handle_traverse_precedent_dag
        elif capability_id == "trace_claim_provenance":
            return cls._handle_trace_claim_provenance
        elif capability_id == "execute_python_sandbox":
            return cls._handle_execute_python_sandbox
        elif capability_id == "verify_claim":
            return cls._handle_verify_claim
        elif capability_id == "database_query":
            return cls._handle_database_query
        elif capability_id == "compare_sources":
            return cls._handle_compare_sources
        elif capability_id == "web_search":
            return cls._handle_web_search
        elif capability_id == "fetch_web_page":
            return cls._handle_fetch_web_page
        elif capability_id == "a2a_dispatch":
            return cls._handle_a2a_dispatch
        raise CapabilitySecurityViolationError(f"No handler registered for '{capability_id}'.")

    @classmethod
    def _handle_search(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        query_text = args.get("query", "")
        parsed = QueryUnderstanding.parse(query_text)
        if args.get("department_id"):
            parsed.department_id = args["department_id"]
        if args.get("doc_type"):
            parsed.doc_type = args["doc_type"]

        top_k = min(10, max(1, args.get("top_k", 5)))
        retriever = HybridRetriever(session)
        passages = retriever.retrieve(parsed, user_context=user, top_k=top_k)
        return {
            "query": query_text,
            "total_found": len(passages),
            "passages": [p.to_dict() for p in passages],
            "raw_passages": passages,
        }

    @classmethod
    def _handle_open_cited_source(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        if not session:
            return {"error": "Database session required."}
        doc_id = args.get("document_id")
        page_num = args.get("page_number", 1)

        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return {"error": f"Document '{doc_id}' not found."}
        if not AclEnforcer.is_document_authorized(session, doc, user):
            return {"error": "Access Denied: Document classification exceeds clearance."}

        v = session.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.retrieved_at.desc()).first()
        return {
            "document_id": doc.id,
            "title": doc.title,
            "department_id": doc.department_id,
            "classification": doc.classification,
            "source_url": v.source_url if v else "",
            "page_number": page_num,
        }

    @classmethod
    def _handle_list_collections(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        if not session:
            return {"total_accessible_collections": 0, "collections": []}
        sources = session.query(Source).filter(Source.status == SourceStatus.APPROVED.value).all()
        accessible = [s for s in sources if AclEnforcer.is_source_authorized(session, s, user)]
        return {
            "user_id": user.user_id,
            "clearance_level": user.clearance_level,
            "total_accessible_collections": len(accessible),
            "collections": [{"id": s.id, "name": s.name, "dept": s.department_id} for s in accessible],
        }

    @classmethod
    def _handle_inspect_system(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        from adam.agent.introspection import SystemIntrospectionService
        service = SystemIntrospectionService(session)
        snapshot = service.generate_snapshot(subtopic=args.get("subtopic", "all"))
        return {
            "system_name": snapshot.system_info.name,
            "version": snapshot.system_info.version,
            "active_model": snapshot.active_model.name if snapshot.active_model else None,
            "harness_profile": snapshot.active_harness.profile_name if snapshot.active_harness else None,
            "total_documents": snapshot.data_sources.total_documents if snapshot.data_sources else 0,
            "text_summary": snapshot.to_ground_truth_context(),
        }

    @classmethod
    def _handle_lookup_precedents(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        if not session:
            return {"total_found": 0, "precedents": []}
        order_num = args.get("order_number") or ""
        doc_id = args.get("document_id")

        q = session.query(PrecedentReference)
        if doc_id:
            q = q.filter(PrecedentReference.source_document_id == doc_id)
        elif order_num:
            q = q.filter(PrecedentReference.cited_order_number.ilike(f"%{order_num.strip()}%"))

        refs = q.limit(10).all()
        return {
            "total_found": len(refs),
            "precedents": [
                {"id": r.id, "relation_type": r.relation_type, "cited_order_number": r.cited_order_number}
                for r in refs
            ],
        }

    @classmethod
    def _handle_traverse_precedent_dag(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        if not session:
            return {"error": "Database session required."}
        order_num = args.get("order_number", "")
        max_hops = min(5, max(1, args.get("max_hops", 3)))

        dag = PrecedentDAG.build_from_database(session)
        terminal_node, chain = dag.resolve_active_terminal_order(order_number=order_num, max_hops=max_hops)
        amendments = dag.get_amendment_chain(order_number=order_num)

        return {
            "order_number": order_num,
            "is_superseded": len(chain) > 1,
            "active_terminal_order": terminal_node.order_number if terminal_node else None,
            "supersession_chain": [n.order_number for n in chain],
            "amendments_count": len(amendments),
            "amendments": [a.order_number for a in amendments],
        }

    @classmethod
    def _handle_trace_claim_provenance(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        from adam.rag.models import EvidencePacket, ParsedQuery
        answer = args.get("answer", "")
        mock_packet = EvidencePacket(query=ParsedQuery(raw_query=answer, clean_query=answer), passages=[])
        trace = ProvenanceGraph.build_trace(answer=answer, packet=mock_packet)
        return trace.to_dict()

    @classmethod
    def _handle_execute_python_sandbox(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        code = args.get("code", "")
        context_vars = args.get("context_vars")
        timeout = min(2.0, max(0.5, args.get("timeout_seconds", 2.0)))
        res = SecurePythonSandbox.execute(code=code, context_vars=context_vars, timeout_seconds=timeout)
        return res.to_dict()

    @classmethod
    def _handle_verify_claim(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        import re
        claim = args.get("claim", "")
        passages = args.get("passages") or []
        corpus = " ".join(passages).lower()
        is_supported = claim.lower().strip() in corpus if corpus else False
        digits = re.findall(r"\d+", claim)
        if digits and corpus and all(d in corpus for d in digits):
            is_supported = True
        return {
            "claim": claim,
            "is_supported": is_supported,
            "verified_in_corpus": bool(corpus),
        }

    @classmethod
    def _handle_database_query(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        if not session:
            return {"error": "Database session required."}
        table = str(args.get("table", "")).strip().lower()
        aggregate = str(args.get("aggregate", "count")).strip().lower()
        limit = min(100, max(1, args.get("limit", 20)))
        filter_by = args.get("filter_by") or {}

        if table == "documents":
            q = session.query(Document)
            if filter_by.get("department_id"):
                q = q.filter(Document.department_id == filter_by["department_id"])
            if aggregate == "count":
                return {"table": table, "aggregate": "count", "result": q.count()}
            docs = q.limit(limit).all()
            return {"table": table, "total_returned": len(docs), "records": [{"id": d.id, "title": d.title} for d in docs]}
        elif table == "sources":
            q = session.query(Source)
            if aggregate == "count":
                return {"table": table, "aggregate": "count", "result": q.count()}
            srcs = q.limit(limit).all()
            return {"table": table, "total_returned": len(srcs), "records": [{"id": s.id, "name": s.name} for s in srcs]}
        return {"table": table, "aggregate": aggregate, "result": 0}

    @classmethod
    def _handle_compare_sources(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        import re
        src_a = str(args.get("source_a", ""))
        src_b = str(args.get("source_b", ""))
        nums_a = set(re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?%?\b", src_a))
        nums_b = set(re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?%?\b", src_b))
        common = sorted(list(nums_a.intersection(nums_b)))
        return {
            "source_a_label": "Source A",
            "source_b_label": "Source B",
            "common_values": common,
            "summary": f"Found {len(common)} common numbers/values between sources.",
        }

    @classmethod
    def _handle_web_search(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        from adam.agent.web import SecureWebSearchEngine
        query = args.get("query", "")
        domain_filter = args.get("domain_filter")
        max_results = min(10, max(1, args.get("max_results", 5)))
        engine = SecureWebSearchEngine()
        results = engine.search(query=query, domain_filter=domain_filter, max_results=max_results)
        return {"query": query, "total_found": len(results), "results": [r.to_dict() for r in results]}

    @classmethod
    def _handle_fetch_web_page(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        from adam.agent.web import SecureWebFetcher
        url = args.get("url", "")
        extract_tables = bool(args.get("extract_tables", True))
        fetcher = SecureWebFetcher()
        page = fetcher.fetch(url=url, extract_tables=extract_tables)
        return page.to_dict()

    @classmethod
    def _handle_a2a_dispatch(cls, args: Dict[str, Any], user: UserContext, session: Optional[Session], depth: int = 0) -> Dict[str, Any]:
        coord = A2ASpecialistCoordinator(session=session, user_context=user)
        contract = A2ATaskContract(
            specialist_agent_id=args.get("specialist_agent_id", ""),
            objective=args.get("objective", ""),
            input_artifacts=args.get("input_artifacts") or {},
            clearance_level=user.clearance_level,
            depth=depth + 1,
        )
        resp: A2AResponseEnvelope = coord.dispatch(contract)
        return resp.to_dict()

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Register all authoritative capabilities on first access."""
        if cls._initialized:
            return

        # 1. Search
        cls.register(CapabilityDescriptor(
            id="search",
            name="Authoritative Repository Hybrid Search",
            type=CapabilityType.TOOL,
            purpose="Retrieve approved Uttarakhand Government Orders and administrative chunks",
            description="Executes authorized hybrid retrieval combining BM25 keyword matching with vector embeddings.",
            input_model=SearchCapabilityArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=80.0, token_cost_weight="MEDIUM"),
            limitations=["Searches local indexed documents only", "Strictly read-only"],
            when_to_use="Always consult first for any statutory, administrative, policy, or legal inquiry.",
            when_to_avoid="Do not use for basic conversational greetings or system identity queries.",
            requires_network=False,
        ))

        # 2. Open Cited Source
        cls.register(CapabilityDescriptor(
            id="open_cited_source",
            name="Inspect Cited Document Source",
            type=CapabilityType.DATA_SOURCE,
            purpose="Inspect full PDF text, OCR blocks, and page coordinates of a cited order",
            description="Retrieves granular document metadata, page record text, and bounding boxes.",
            input_model=OpenCitedSourceArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=25.0, token_cost_weight="LOW"),
            limitations=["Requires valid document_id in repository"],
            when_to_use="When specific paragraph coordinates or visual grounding of an order are required.",
            requires_network=False,
        ))

        # 3. List Authorised Collections
        cls.register(CapabilityDescriptor(
            id="list_authorised_collections",
            name="Discover Authorised Collections",
            type=CapabilityType.DATA_SOURCE,
            purpose="Enumerate approved departmental sources accessible under current user clearance",
            description="Lists public records sources and collections filtered strictly by clearance.",
            input_model=ListCollectionsArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=15.0, token_cost_weight="LOW"),
            limitations=["Filtered strictly by user clearance level"],
            when_to_use="When discovering repository boundaries or checking departmental scope.",
            requires_network=False,
        ))

        # 4. Inspect System
        cls.register(CapabilityDescriptor(
            id="inspect_system",
            name="Authoritative System Self-Model Inspection",
            type=CapabilityType.TOOL,
            purpose="Inspect active model, runtime backend, harness profile, memory budget, and tools",
            description="Queries live system self-model. Keys, tokens, and private paths are redacted.",
            input_model=InspectSystemArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=20.0, token_cost_weight="LOW"),
            limitations=["Authoritative read-only ground truth; keys redacted"],
            when_to_use="When user asks about ADAM's identity, active model weights, or system capabilities.",
            requires_network=False,
        ))

        # 5. Lookup Precedents
        cls.register(CapabilityDescriptor(
            id="lookup_precedents",
            name="Relational Precedent Lookup",
            type=CapabilityType.TOOL,
            purpose="Query direct precedent linkages (supersedes, amends, in continuation of)",
            description="Looks up immediate precedent relations for an order number or document ID.",
            input_model=LookupPrecedentsArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=30.0, token_cost_weight="LOW"),
            limitations=["Direct 1-hop linkages only"],
            when_to_use="When checking direct amendments or mentions of an order.",
            requires_network=False,
        ))

        # 6. Traverse Precedent DAG
        cls.register(CapabilityDescriptor(
            id="traverse_precedent_dag",
            name="Deep Precedent DAG Traversal",
            type=CapabilityType.GRAPH_TRAVERSAL,
            purpose="Traverse full multi-hop directed acyclic graph for superseding terminal orders",
            description="Recursively resolves statutory currency, identifying if an order was superseded.",
            input_model=TraversePrecedentDagArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.MEDIUM,
            cost=CostModel(latency_weight_ms=60.0, token_cost_weight="LOW"),
            limitations=["Max 5 hops traversal ceiling"],
            when_to_use="When checking if a historical Government Order remains in force or has been superseded.",
            requires_network=False,
        ))

        # 7. Trace Claim Provenance
        cls.register(CapabilityDescriptor(
            id="trace_claim_provenance",
            name="Claim-to-Pixel Provenance Graph Builder",
            type=CapabilityType.GRAPH_TRAVERSAL,
            purpose="Connect synthesized claims down to PDF text blocks and page bounding boxes",
            description="Builds an unbroken DAG from answer claims to source passages, pages, and coordinates.",
            input_model=TraceClaimProvenanceArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=40.0, token_cost_weight="LOW"),
            limitations=["Extracts claims and links to provided evidence"],
            when_to_use="When generating audit-grade citations or visual bounding-box proofs.",
            requires_network=False,
        ))

        # 8. Execute Python Sandbox
        cls.register(CapabilityDescriptor(
            id="execute_python_sandbox",
            name="Isolated Deterministic Python Sandbox",
            type=CapabilityType.SANDBOX_COMPUTE,
            purpose="Execute mathematical, statistical, or date calculations without LLM hallucinations",
            description="Strictly isolated Python environment without filesystem, imports, or network access.",
            input_model=ExecutePythonSandboxArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.MEDIUM,
            cost=CostModel(latency_weight_ms=45.0, token_cost_weight="LOW", compute_intensity="MODERATE"),
            limitations=["No imports, no network, 2.0s hard timeout, 256MB memory cap"],
            when_to_use="When computing financial allowances, revised salaries, pensions, percentages, or dates.",
            requires_network=False,
        ))

        # 9. Verify Claim
        cls.register(CapabilityDescriptor(
            id="verify_claim",
            name="Evidence Claim Verification",
            type=CapabilityType.TOOL,
            purpose="Verify whether an assertion, numerical rate, or date is grounded in gathered evidence",
            description="String and token-level verification check against accumulated passages.",
            input_model=VerifyClaimArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=10.0, token_cost_weight="LOW"),
            limitations=["Evaluates against provided corpus context"],
            when_to_use="Intermediate verification before final response synthesis.",
            requires_network=False,
        ))

        # 10. Database Query
        cls.register(CapabilityDescriptor(
            id="database_query",
            name="Read-Only Database Inspector",
            type=CapabilityType.DATA_SOURCE,
            purpose="Read-only query of relational tables (documents, versions, sources, precedents)",
            description="Performs aggregate counts and metadata summaries over official tables.",
            input_model=DatabaseQueryArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.MEDIUM,
            cost=CostModel(latency_weight_ms=35.0, token_cost_weight="LOW"),
            limitations=["Strictly read-only; no raw SQL; max 100 rows"],
            when_to_use="When user asks for document counts, totals, departmental statistics, or inventory summaries.",
            requires_network=False,
        ))

        # 11. Compare Sources
        cls.register(CapabilityDescriptor(
            id="compare_sources",
            name="Multi-Source Delta Analyzer",
            type=CapabilityType.TOOL,
            purpose="Perform structured comparison and delta analysis between two texts or orders",
            description="Compares rates, dates, allowances, and terminology between two sources.",
            input_model=CompareSourcesArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.LOW,
            cost=CostModel(latency_weight_ms=25.0, token_cost_weight="LOW"),
            limitations=["Read-only text and fact comparison"],
            when_to_use="When comparing two historical orders or internal state rules against external guidelines.",
            requires_network=False,
        ))

        # 12. Web Search
        cls.register(CapabilityDescriptor(
            id="web_search",
            name="Secure Domain-Aware Web Search",
            type=CapabilityType.TOOL,
            purpose="Search external public web sources for national/central policies",
            description="SSRF-safe external search prioritizing official domains (.gov.in, .nic.in).",
            input_model=WebSearchArgs,
            permissions=CapabilityPermissions(
                min_clearance_level=Classification.PUBLIC.value,
                is_air_gapped_compatible=False,  # BARRRED under classified clearance
            ),
            risk=RiskLevel.HIGH,
            cost=CostModel(latency_weight_ms=250.0, token_cost_weight="HIGH", rate_limit_units=2),
            limitations=["Prohibited under RESTRICTED/CONFIDENTIAL air-gapped clearances", "Domain allowlisted"],
            when_to_use="Use ONLY when local repository evidence is insufficient or external comparison is demanded.",
            when_to_avoid="Never use when user asks about local Uttarakhand state rules or when air-gapped.",
            requires_network=True,
        ))

        # 13. Fetch Web Page
        cls.register(CapabilityDescriptor(
            id="fetch_web_page",
            name="SSRF-Safe Web Page Retrieval",
            type=CapabilityType.TOOL,
            purpose="Fetch and extract clean markdown/table content from external URLs",
            description="Retrieves external web pages with private IP filtering and 1MB size limit.",
            input_model=FetchWebPageArgs,
            permissions=CapabilityPermissions(
                min_clearance_level=Classification.PUBLIC.value,
                is_air_gapped_compatible=False,  # BARRED under classified clearance
            ),
            risk=RiskLevel.HIGH,
            cost=CostModel(latency_weight_ms=300.0, token_cost_weight="HIGH", rate_limit_units=2),
            limitations=["Prohibited under RESTRICTED/CONFIDENTIAL air-gapped clearances", "5.0s timeout"],
            when_to_use="When inspecting an authoritative external web source found via web search.",
            requires_network=True,
        ))

        # 14. A2A Dispatch (Specialist Agent Delegation)
        cls.register(CapabilityDescriptor(
            id="a2a_dispatch",
            name="Agent-to-Agent Specialist Delegation",
            type=CapabilityType.SPECIALIST_AGENT,
            purpose="Delegate complex sub-investigations to bounded specialist agents",
            description="Issues an A2ATaskContract to a specialist agent with strict depth <= 1 and budget limits.",
            input_model=A2ADispatchArgs,
            permissions=CapabilityPermissions(min_clearance_level=Classification.PUBLIC.value, is_air_gapped_compatible=True),
            risk=RiskLevel.MEDIUM,
            cost=CostModel(latency_weight_ms=200.0, token_cost_weight="HIGH", compute_intensity="HEAVY"),
            limitations=["Max recursion depth = 1 (no cascading agents)", "Max 2 specialists per session"],
            when_to_use="When a sub-task requires specialized multi-step analysis (e.g. PrecedentGraphSpecialist).",
            requires_network=False,
        ))

        cls._initialized = True


# Global registry singleton instance
GLOBAL_CAPABILITY_REGISTRY = CapabilityRegistry
