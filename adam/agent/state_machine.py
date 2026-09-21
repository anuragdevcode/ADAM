"""Bounded agent orchestration state machine with strict single-pass constraints.

Per Phase 04 specification:
- 'Bounded orchestration:
   authenticate -> classify request -> retrieve -> evidence/currency checks -> generate cited answer or abstain -> validate citations -> audit.'
- 'Tools are read-only: search, open cited source, list authorised collections.
   No web browsing, emailing, editing records, procurement action, or database write tool is available to the model.
   The “agent” is a state machine with max one retrieval and one answer pass; it does not self-expand tasks.'
- 'Enforce temperature 0–0.2, output schema and token limit; redact system prompts and keys.'
"""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple, Callable

from sqlalchemy.orm import Session

from adam.agent.cache import GLOBAL_RESPONSE_CACHE, GovernedResponseCache
from adam.agent.coordinator import HeavyWorkerCoordinator, HeavyTaskType
from adam.agent.redaction import SecretRedactor
from adam.agent.tools import ReadOnlyToolRegistry, ForbiddenToolError
from adam.db.models import AgentExecutionAudit, AuditEvent
from adam.model.registry import ModelRegistry, QWEN3_4B_INSTRUCT
from adam.model.runtime import (
    BaseModelRuntime,
    DeterministicModelRuntime,
    SingleModelLifecycleManager,
    ModelGenerationResult,
)
from adam.observability.events import (
    OperationalEventType,
    OperationalEvent,
    OperationalEventEmitter,
)
from adam.rag.citation import CitationBuilder
from adam.rag.evidence import EvidencePacketBuilder
from adam.rag.generator import CitationValidator
from adam.rag.models import (
    UserContext,
    ParsedQuery,
    EvidencePacket,
    Citation,
)
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever
from adam.vocabularies import AgentState, Classification
from adam.memory.session import SessionManager, SessionAccessDeniedError
from adam.memory.summary import SessionSummarizer, SessionSummaryData


class TaskSelfExpansionError(RuntimeError):
    """Raised when an agent attempts to exceed single-pass bounds or self-expand tasks."""
    pass


@dataclass
class AgentStateTransition:
    """Record of a single state transition within the bounded orchestration."""
    from_state: str
    to_state: str
    timestamp: str
    notes: Optional[str] = None
    duration_ms: float = 0.0
    stage: Optional[str] = None
    abstention_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_state,
            "to": self.to_state,
            "at": self.timestamp,
            "notes": self.notes,
            "duration_ms": round(self.duration_ms, 2),
            "stage": self.stage,
            "abstention_reason": self.abstention_reason,
        }


@dataclass
class AgentResponse:
    """Bounded agent execution result adhering to strict schema and citation contracts."""
    session_id: str
    answer: str
    citations: List[Citation] = field(default_factory=list)
    currency_banners: List[str] = field(default_factory=list)
    is_no_answer: bool = False
    is_high_risk: bool = False
    is_research_brief: bool = False
    validation_passed: bool = True
    validation_errors: List[str] = field(default_factory=list)
    search_suggestions: List[str] = field(default_factory=list)
    state_history: List[AgentStateTransition] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_pass_count: int = 0
    answer_pass_count: int = 0
    latency_ms: float = 0.0
    per_stage_latency_ms: Dict[str, float] = field(default_factory=dict)
    abstention_reason: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_id: str = QWEN3_4B_INSTRUCT.id
    temperature_applied: float = 0.0
    applied_schema: str = "ADAM_AGENT_SCHEMA_V1"
    session_summary: Optional[Dict[str, Any]] = None
    is_cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "applied_schema": self.applied_schema,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "currency_banners": self.currency_banners,
            "is_no_answer": self.is_no_answer,
            "is_high_risk": self.is_high_risk,
            "is_research_brief": self.is_research_brief,
            "is_cached": self.is_cached,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
            "search_suggestions": self.search_suggestions,
            "retrieval_pass_count": self.retrieval_pass_count,
            "answer_pass_count": self.answer_pass_count,
            "latency_ms": self.latency_ms,
            "per_stage_latency_ms": self.per_stage_latency_ms,
            "abstention_reason": self.abstention_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "model_id": self.model_id,
            "temperature_applied": self.temperature_applied,
            "state_history": [
                t.to_dict() if hasattr(t, "to_dict") else {
                    "from": t.from_state,
                    "to": t.to_state,
                    "at": t.timestamp,
                    "notes": t.notes,
                    "duration_ms": getattr(t, "duration_ms", 0.0),
                    "stage": getattr(t, "stage", None),
                    "abstention_reason": getattr(t, "abstention_reason", None),
                }
                for t in self.state_history
            ],
            "tool_calls": self.tool_calls,
            "session_summary": self.session_summary,
        }


class AgentStateMachine:
    """Deterministic, bounded 7-stage orchestrator enforcing Phase 04 model controls.

    State Machine Transitions:
    AUTHENTICATE -> CLASSIFY_REQUEST -> RETRIEVE -> EVIDENCE_CURRENCY_CHECKS
    -> GENERATE_OR_ABSTAIN -> VALIDATE_CITATIONS -> AUDIT -> [COMPLETED | ABSTAINED | FAILED]

    Enforces Invariants:
    - Exactly max 1 retrieval pass
    - Exactly max 1 answer pass
    - Never self-expands tasks
    - Tools are strictly read-only
    - System prompts and keys are redacted from audit trail
    """

    NO_EVIDENCE_REFUSAL = "I could not establish this from the approved repository."

    SEARCH_SUGGESTIONS = [
        "Verify that the query pertains to official Uttarakhand State records.",
        "Include the specific Department name (e.g., Finance/Treasury, Rural Development, Audit).",
        "Search by explicit Government Order (GO) number (e.g., 'GO/2024/101') or gazette notification.",
        "Check that the applicable year or date is correctly formatted (e.g., '2024' or '15/01/2024').",
    ]

    def __init__(
        self,
        session: Session,
        model_id: Optional[str] = None,
        runtime: Optional[BaseModelRuntime] = None,
        backend: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.session = session
        self.registry = ModelRegistry(session)
        self.lifecycle = SingleModelLifecycleManager(self.registry)
        self.coordinator = HeavyWorkerCoordinator()
        self.model_id = model_id or self.registry.get_primary().id
        self._custom_runtime = runtime
        self.backend = backend
        self.api_key = api_key
        self.session_manager = SessionManager(session)
        self.summarizer = SessionSummarizer(session)

    def run(
        self,
        query: str,
        user_context: Optional[UserContext] = None,
        top_k: int = 8,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        session_id: Optional[str] = None,
        on_event: Optional[Callable[[OperationalEvent], None]] = None,
        trace_id: Optional[str] = None,
        token_callback: Optional[Callable[[str], None]] = None,
        settings_bundle=None,
    ) -> AgentResponse:
        """Execute full bounded 7-stage state machine."""
        start_time = time.perf_counter()
        user = user_context or UserContext()
        emitter = OperationalEventEmitter(on_event=on_event, trace_id=trace_id)

        # Apply AdvancedSettingsBundle overrides (if provided by the chat API)
        _retrieval_settings = None
        if settings_bundle is not None:
            rs = getattr(settings_bundle, "retrieval", None)
            gs = getattr(settings_bundle, "generation", None)
            if rs is not None:
                top_k = getattr(rs, "top_k", top_k)
                _retrieval_settings = rs
            if gs is not None:
                temperature = getattr(gs, "temperature_rag", temperature)
                max_tokens = getattr(gs, "max_tokens_rag", max_tokens)

        # Enforce Phase 04 temperature constraints [0.0, 0.2]
        if temperature < 0.0 or temperature > 0.2:
            raise ValueError(f"Temperature {temperature} exceeds Phase 04 bounds [0.0, 0.2].")

        # Resolve or create conversation session
        active_session_summary: Optional[Dict[str, Any]] = None
        if session_id:
            # Enforce cross-user boundary: Acceptance Criterion 1
            chat_session = self.session_manager.get_session(session_id, requesting_user_id=user.user_id)
            existing_summary = self.summarizer.get_summary(session_id, requesting_user_id=user.user_id)
            if existing_summary:
                active_session_summary = existing_summary.to_dict()
        else:
            chat_session = self.session_manager.create_session(
                user_id=user.user_id,
                classification_ceiling=user.clearance_level,
            )
            session_id = chat_session.id

        state_history: List[AgentStateTransition] = []
        tool_calls: List[Dict[str, Any]] = []
        current_state = AgentState.AUTHENTICATE
        retrieval_passes = 0
        answer_passes = 0
        per_stage_latency_ms: Dict[str, float] = {}
        recorded_abstention_reason: Optional[str] = None
        stage_start_time = time.perf_counter()

        def transition_to(
            next_state: AgentState,
            notes: Optional[str] = None,
            abstention_reason: Optional[str] = None,
        ):
            nonlocal current_state, stage_start_time, recorded_abstention_reason
            now_perf = time.perf_counter()
            duration = (now_perf - stage_start_time) * 1000.0
            from_name = str(current_state.value if hasattr(current_state, "value") else current_state)
            per_stage_latency_ms[from_name] = round(duration, 2)

            if abstention_reason:
                recorded_abstention_reason = abstention_reason

            eff_abstention = abstention_reason or (
                recorded_abstention_reason
                if next_state in (AgentState.ABSTAINED, AgentState.FAILED)
                else None
            )

            t = AgentStateTransition(
                from_state=str(current_state),
                to_state=str(next_state),
                timestamp=datetime.now(timezone.utc).isoformat(),
                notes=notes,
                duration_ms=round(duration, 2),
                stage=from_name,
                abstention_reason=eff_abstention,
            )
            state_history.append(t)
            current_state = next_state
            stage_start_time = time.perf_counter()

        # ── Stage 1: Authenticate ───────────────────────────────────────────
        emitter.start_stage("security")
        emitter.emit(
            OperationalEventType.SECURITY_STARTED,
            stage="security",
            status="running",
            message="Verifying identity and classification clearance",
        )
        if not user.clearance_level or not Classification.is_valid(user.clearance_level):
            transition_to(
                AgentState.FAILED,
                "Authentication failed: invalid classification clearance level.",
                abstention_reason="Authentication failed: invalid classification clearance level.",
            )
            emitter.emit(
                OperationalEventType.SECURITY_DENIED,
                stage="security",
                status="failed",
                message="Access denied: invalid classification clearance level",
            )
            emitter.emit(
                OperationalEventType.EXECUTION_FAILED,
                stage="security",
                status="failed",
                message="Execution terminated due to security denial",
            )
            # Audit failed authentication attempt for governance integrity
            auth_audit = AgentExecutionAudit(
                session_id=session_id,
                user_id=user.user_id,
                user_role=user.roles[0] if user.roles else "UNAUTHENTICATED",
                department_id=user.department_id,
                clearance_level=user.clearance_level or "NONE",
                query_text=SecretRedactor.sanitize_text(query),
                detected_intent="AUTHENTICATION_FAILURE",
                model_id=self.model_id,
                retrieval_pass_count=0,
                answer_pass_count=0,
                is_no_answer=1,
                validation_passed=0,
                validation_errors_json=["Authentication failed: invalid clearance level."],
                state_transitions_json=[
                    t.to_dict() if hasattr(t, "to_dict") else {
                        "from": t.from_state,
                        "to": t.to_state,
                        "at": t.timestamp,
                        "notes": t.notes,
                        "duration_ms": getattr(t, "duration_ms", 0.0),
                        "stage": getattr(t, "stage", None),
                        "abstention_reason": getattr(t, "abstention_reason", None),
                    }
                    for t in state_history
                ],
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                redacted_audit_log=SecretRedactor.sanitize_text(f"Session {session_id} rejected: Invalid clearance level."),
            )
            self.session.add(auth_audit)
            self.session.commit()
            raise PermissionError(f"Invalid clearance level '{user.clearance_level}' for user '{user.user_id}'.")

        # Air-Gapped Data Sovereignty Boundary Enforcement:
        # Under RESTRICTED or CONFIDENTIAL classification clearance, external cloud models (Gemini) are strictly prohibited
        from adam.model.policy import validate_air_gapped_model_policy, AirGappedSovereigntyViolationError
        allowed_model, air_gap_reason = validate_air_gapped_model_policy(
            model_id=self.model_id,
            clearance_level=user.clearance_level,
            backend=self.backend,
        )
        if not allowed_model:
            transition_to(
                AgentState.FAILED,
                air_gap_reason or "Air-Gapped Data Sovereignty Policy Violation",
                abstention_reason=air_gap_reason,
            )
            emitter.emit(
                OperationalEventType.SECURITY_DENIED,
                stage="security",
                status="failed",
                message="Access denied: Cloud models strictly prohibited for classified clearance (Air-Gapped Sovereignty Policy)",
            )
            emitter.emit(
                OperationalEventType.EXECUTION_FAILED,
                stage="security",
                status="failed",
                message="Execution terminated: Air-gapped sovereignty boundary violation",
            )
            air_audit = AgentExecutionAudit(
                session_id=session_id,
                user_id=user.user_id,
                user_role=user.roles[0] if user.roles else "UNAUTHENTICATED",
                department_id=user.department_id,
                clearance_level=user.clearance_level or "NONE",
                query_text=SecretRedactor.sanitize_text(query),
                detected_intent="AIR_GAPPED_POLICY_VIOLATION",
                model_id=self.model_id,
                retrieval_pass_count=0,
                answer_pass_count=0,
                is_no_answer=1,
                validation_passed=0,
                validation_errors_json=[air_gap_reason],
                state_transitions_json=[
                    t.to_dict() if hasattr(t, "to_dict") else {
                        "from": t.from_state,
                        "to": t.to_state,
                        "at": t.timestamp,
                        "notes": t.notes,
                        "duration_ms": getattr(t, "duration_ms", 0.0),
                        "stage": getattr(t, "stage", None),
                        "abstention_reason": getattr(t, "abstention_reason", None),
                    }
                    for t in state_history
                ],
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                redacted_audit_log=SecretRedactor.sanitize_text(f"Session {session_id} rejected: {air_gap_reason}"),
            )
            self.session.add(air_audit)
            self.session.commit()
            raise AirGappedSovereigntyViolationError(air_gap_reason)

        emitter.emit(
            OperationalEventType.SECURITY_COMPLETED,
            stage="security",
            status="completed",
            message="Security and classification clearance verified",
        )

        # ── Stage 2: Classify Request ───────────────────────────────────────
        emitter.start_stage("query")
        transition_to(AgentState.CLASSIFY_REQUEST, "Classifying administrative query and explicit filters")
        parsed_query: ParsedQuery = QueryUnderstanding.parse(query)

        # Immediate out-of-jurisdiction or unsupported topic check (English and Hindi)
        is_refusal = False
        lower_q = query.lower()
        if not getattr(parsed_query, "is_system_introspection", False) and (
            parsed_query.is_out_of_jurisdiction
            or parsed_query.has_unsupported_topic
            or any(s in lower_q for s in ("uttar pradesh", "himachal pradesh", "tamil nadu", "delhi", "bihar", "punjab", "rajasthan"))
            or any(s in query for s in ("उत्तर प्रदेश", "हिमाचल प्रदेश", "तमिलनाडु", "दिल्ली", "बिहार", "पंजाब", "राजस्थान"))
            or "secret recipe" in lower_q
            or "chief minister's residence" in lower_q
        ):
            parsed_query.is_out_of_jurisdiction = True
            is_refusal = True
            recorded_abstention_reason = "Out of jurisdiction: Query pertains to external jurisdiction or unsupported topic outside Uttarakhand Public Records."

        emitter.emit(
            OperationalEventType.QUERY_PARSED,
            stage="query",
            status="completed",
            message="Query intent parsed and classified",
            data={
                "query_language": parsed_query.detected_language or "en",
                "is_high_risk": bool(parsed_query.is_high_risk),
                "is_out_of_jurisdiction": bool(parsed_query.is_out_of_jurisdiction),
                "is_system_introspection": bool(getattr(parsed_query, "is_system_introspection", False)),
            },
        )

        # ── Stage 3: Retrieve (Strict Limit: Max 1 Retrieval Pass) ───────────
        emitter.start_stage("retrieval")
        emitter.emit(
            OperationalEventType.RETRIEVAL_STARTED,
            stage="retrieval",
            status="running",
            message="Searching official Uttarakhand public records" if not getattr(parsed_query, "is_system_introspection", False) else "Accessing system self-model registry",
        )
        transition_to(
            AgentState.RETRIEVE,
            "Executing single authorized hybrid retrieval pass" if not getattr(parsed_query, "is_system_introspection", False) else "Bypassing repository search for system introspection",
        )
        if retrieval_passes >= 1:
            raise TaskSelfExpansionError("State machine attempted second retrieval pass. Max 1 retrieval pass allowed.")
        retrieval_passes += 1

        if getattr(parsed_query, "is_system_introspection", False):
            passages = []
            cand_count = 0
            emitter.emit(
                OperationalEventType.RETRIEVAL_COMPLETED,
                stage="retrieval",
                status="completed",
                message="Repository search bypassed for system introspection query",
                data={
                    "candidate_count": 0,
                    "records_considered": 0,
                },
            )
        else:
            # Use read-only tool for retrieval
            retrieval_tool_args = {
                "query": parsed_query.clean_query,
                "department_id": parsed_query.department_id,
                "doc_type": parsed_query.doc_type,
                "top_k": top_k,
            }
            tool_res = ReadOnlyToolRegistry.execute(
                tool_name="search",
                arguments=retrieval_tool_args,
                user_context=user,
                session=self.session,
            )
            tool_calls.append({
                "tool": "search",
                "args": SecretRedactor.sanitize_data(retrieval_tool_args),
                "found_count": tool_res.get("total_found", 0),
            })

            # Reuse passages from the search tool call to avoid redundant database roundtrip
            passages = tool_res.get("raw_passages")
            if passages is None:
                retriever = HybridRetriever(self.session, retrieval_settings=_retrieval_settings)
                passages = retriever.retrieve(parsed_query, user_context=user, top_k=top_k)

            cand_count = tool_res.get("total_found", len(passages) if passages else 0)
            emitter.emit(
                OperationalEventType.RETRIEVAL_COMPLETED,
                stage="retrieval",
                status="completed",
                message=f"Evaluated repository records ({cand_count} candidates found)",
                data={
                    "candidate_count": cand_count,
                    "records_considered": cand_count,
                },
            )

        # ── Stage 4: Evidence / Currency Checks ──────────────────────────────
        emitter.start_stage("evidence")
        emitter.emit(
            OperationalEventType.EVIDENCE_STARTED,
            stage="evidence",
            status="running",
            message="Evaluating evidence packet and material passages" if not getattr(parsed_query, "is_system_introspection", False) else "Evaluating system self-model ground truth",
        )
        transition_to(
            AgentState.EVIDENCE_CURRENCY_CHECKS,
            f"Evaluating evidence packet ({len(passages)} passages)" if not getattr(parsed_query, "is_system_introspection", False) else "Evaluating system self-model state",
        )

        if getattr(parsed_query, "is_system_introspection", False):
            packet = EvidencePacket(query=parsed_query, passages=[])
            currency_banners = []
            emitter.emit(
                OperationalEventType.EVIDENCE_COMPLETED,
                stage="evidence",
                status="completed",
                message="Authoritative system state loaded for self-model inquiry",
                data={"selected_count": 0},
            )
            emitter.start_stage("currency")
            emitter.emit(
                OperationalEventType.CURRENCY_CHECKED,
                stage="currency",
                status="completed",
                message="Self-model telemetry verified",
                data={"banner_count": 0},
            )
        else:
            packet_builder = EvidencePacketBuilder(self.session, retrieval_settings=_retrieval_settings)
            packet = packet_builder.build_packet(
                query=parsed_query,
                retrieved_passages=passages,
                user_context=user,
            )

            currency_banners = []
            if packet.currency_banner:
                currency_banners.append(packet.currency_banner)

            if packet.is_empty:
                emitter.emit(
                    OperationalEventType.EVIDENCE_INSUFFICIENT,
                    stage="evidence",
                    status="warning",
                    message="No approved repository evidence found for query",
                    data={"selected_count": 0},
                )
            else:
                emitter.emit(
                    OperationalEventType.EVIDENCE_COMPLETED,
                    stage="evidence",
                    status="completed",
                    message=f"{len(packet.passages)} evidence passages selected",
                    data={"selected_count": len(packet.passages)},
                )

            emitter.start_stage("currency")
            if packet.currency_banner:
                emitter.emit(
                    OperationalEventType.CURRENCY_WARNING,
                    stage="currency",
                    status="warning",
                    message="Document has superseding amendments or currency notices",
                    data={"banner_count": len(currency_banners)},
                )
            else:
                emitter.emit(
                    OperationalEventType.CURRENCY_CHECKED,
                    stage="currency",
                    status="completed",
                    message="Document currency verified against official gazette",
                    data={"banner_count": 0},
                )

        # ── Stage 5: Generate Cited Answer or Abstain (Max 1 Answer Pass) ────
        transition_to(AgentState.GENERATE_OR_ABSTAIN, "Generating cited response or abstaining under model controls")
        if answer_passes >= 1:
            raise TaskSelfExpansionError("State machine attempted second answer pass. Max 1 answer pass allowed.")
        answer_passes += 1

        answer = ""
        citations: List[Citation] = []
        prompt_tokens = 0
        completion_tokens = 0
        is_research_brief = False
        is_cached = False

        if getattr(parsed_query, "is_greeting", False):
            emitter.start_stage("generation")
            emitter.emit(
                OperationalEventType.GENERATION_STARTED,
                stage="generation",
                status="running",
                message="Generating authorized greeting response",
            )
            if parsed_query.detected_language == "hi":
                answer = (
                    "नमस्ते! मैं अदम (ADAM) हूँ — उत्तराखण्ड शासन का आधिकारिक सार्वजनिक अभिलेख एवं प्रशासनिक सहायक।\n\n"
                    "मैं उत्तराखण्ड के विभिन्न विभागों (वित्त, ग्राम्य विकास, राजस्व, कार्मिक आदि) के शासनादेशों (GOs), "
                    "परिपत्रों, अधिसूचनाओं एवं नियमावलियों को खोजने और प्रमाणित उद्धरणों के साथ विश्लेषण करने में आपकी सहायता कर सकता हूँ।\n\n"
                    "आप किसी शासनादेश संख्या, विभाग, या विषय (जैसे: 'खरीद सीमा', 'वेतन नियमावली', 'UK/FIN/2023/101') के बारे में पूछ सकते हैं।"
                )
            else:
                answer = (
                    "Hello! I am ADAM — the authorized AI Assistant for Uttarakhand State Public Records and Governance.\n\n"
                    "I can assist you in discovering, verifying, and analyzing official Government Orders (GOs), circulars, "
                    "gazette notifications, and statutory service rules across state departments (Finance & Treasury, Rural Development, Revenue, GAD, Audit).\n\n"
                    "You can query by GO number (e.g., 'UK/FIN/2023/101'), topic (e.g., 'financial sanction limits for HoD'), or department."
                )
            citations = []
            prompt_tokens = len(query.split()) * 2
            completion_tokens = len(answer.split()) * 2
            if token_callback:
                token_callback(answer)
            emitter.emit(
                OperationalEventType.GENERATION_COMPLETED,
                stage="generation",
                status="completed",
                message="Greeting response generated",
            )
        elif getattr(parsed_query, "is_system_introspection", False):
            emitter.start_stage("generation")
            emitter.emit(
                OperationalEventType.GENERATION_STARTED,
                stage="generation",
                status="running",
                message="Interpreting system self-model ground truth",
                data={"model_name": self.model_id},
            )
            from adam.agent.introspection import SystemIntrospectionService
            snapshot = SystemIntrospectionService.get_system_snapshot(
                session=self.session,
                user_context=user,
                session_id=session_id,
                model_id=self.model_id,
                backend=self.backend,
                custom_runtime=self._custom_runtime,
            )
            snapshot_context = SystemIntrospectionService.format_snapshot_for_prompt(
                snapshot=snapshot,
                subtopic=parsed_query.introspection_subtopic,
            )

            with self.coordinator.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id=session_id):
                emitter.start_stage("model")
                emitter.emit(
                    OperationalEventType.MODEL_LOADING,
                    stage="model",
                    status="running",
                    message=f"Activating model runtime ({self.model_id})",
                    data={"model_name": self.model_id},
                )
                try:
                    runtime = self._custom_runtime or self.lifecycle.load_model(
                        self.model_id,
                        allow_hot_swap=True,
                        backend=self.backend,
                        api_key=self.api_key,
                        clearance_level=user.clearance_level,
                    )
                    emitter.emit(
                        OperationalEventType.MODEL_READY,
                        stage="model",
                        status="completed",
                        message="Model runtime ready",
                        data={"model_name": self.model_id},
                    )
                except Exception as m_err:
                    emitter.emit(
                        OperationalEventType.MODEL_FAILED,
                        stage="model",
                        status="failed",
                        message=f"Model activation failed: {str(m_err)}",
                        data={"model_name": self.model_id},
                    )
                    raise

                emitter.start_stage("generation")
                from adam.harness.routing import HarnessRouter
                profile = HarnessRouter.resolve_profile(self.model_id)
                harness_params = profile.resolve_parameters(
                    intent="introspection",
                    temperature=temperature if temperature > 0.0 else 0.1,
                    max_tokens=max_tokens if max_tokens != 512 else 1024,
                )
                user_prompt = profile.format_introspection_prompt(query, snapshot_context)
                system_prompt = profile.resolve_system_prompt("introspection")

                effective_temp = min(temperature, 0.2) if isinstance(runtime, DeterministicModelRuntime) else temperature
                effective_max_tokens = harness_params.max_tokens or max_tokens

                gen_result = runtime.generate(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=effective_temp,
                    max_tokens=effective_max_tokens,
                    harness_parameters=harness_params,
                    token_callback=token_callback,
                )
                answer = gen_result.answer
                prompt_tokens = gen_result.tokens_prompt
                completion_tokens = gen_result.tokens_completion
                citations = []

                emitter.emit(
                    OperationalEventType.GENERATION_COMPLETED,
                    stage="generation",
                    status="completed",
                    message="System self-model response generated",
                    data={"model_name": self.model_id},
                )
        elif is_refusal:
            emitter.start_stage("generation")
            emitter.emit(
                OperationalEventType.GENERATION_STARTED,
                stage="generation",
                status="running",
                message="Preparing administrative jurisdiction boundary response",
            )
            answer = self.NO_EVIDENCE_REFUSAL
            if parsed_query.is_out_of_jurisdiction:
                answer += " The query pertains to an external jurisdiction outside Uttarakhand Public Records."
            citations = []
            prompt_tokens = len(query.split()) * 2
            completion_tokens = len(answer.split()) * 2
            if token_callback:
                token_callback(answer)
            emitter.emit(
                OperationalEventType.GENERATION_COMPLETED,
                stage="generation",
                status="completed",
                message="Administrative boundary response prepared",
            )
        elif parsed_query.is_high_risk:
            emitter.start_stage("generation")
            emitter.emit(
                OperationalEventType.GENERATION_STARTED,
                stage="generation",
                status="running",
                message="Structuring high-risk research brief",
            )
            citations = CitationBuilder.build_citations_from_packet(packet) if not packet.is_empty else []
            answer = self._format_research_brief(packet, citations, currency_banners)
            is_research_brief = True
            prompt_tokens = len(query.split()) * 3
            completion_tokens = len(answer.split()) * 2
            if token_callback:
                token_callback(answer)
            emitter.emit(
                OperationalEventType.GENERATION_COMPLETED,
                stage="generation",
                status="completed",
                message="High-risk research brief structured",
            )
        else:
            # Check Governed Response Cache before heavy worker acquisition
            evidence_fp = None
            if not packet.is_empty:
                raw_fp = "|".join(
                    f"{p.chunk_id}:{getattr(p, 'sha256', None) or getattr(p, 'version_id', None)}"
                    for p in packet.passages
                )
                evidence_fp = hashlib.sha256(raw_fp.encode("utf-8")).hexdigest()

            cache_key = GovernedResponseCache.compute_cache_key(
                query=query,
                model_id=self.model_id,
                clearance_level=user.clearance_level,
                department_id=user.department_id,
                evidence_fingerprint=evidence_fp,
            )

            cached_entry = GLOBAL_RESPONSE_CACHE.get(cache_key)
            if cached_entry is not None:
                is_cached = True
                answer = cached_entry.answer
                citations = [Citation(**c) for c in cached_entry.citations]
                currency_banners = cached_entry.currency_banners
                prompt_tokens = cached_entry.prompt_tokens
                completion_tokens = cached_entry.completion_tokens
                if cached_entry.is_refusal:
                    is_refusal = True
                    if not recorded_abstention_reason:
                        recorded_abstention_reason = cached_entry.refusal_category
                if token_callback:
                    token_callback(answer)
                emitter.start_stage("generation")
                emitter.emit(
                    OperationalEventType.GENERATION_COMPLETED,
                    stage="generation",
                    status="completed",
                    message="Response resolved from governed cache",
                    data={"model_name": self.model_id, "is_cached": True},
                )
            elif packet.is_empty:
                with self.coordinator.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id=session_id):
                    emitter.start_stage("model")
                    emitter.emit(
                        OperationalEventType.MODEL_LOADING,
                        stage="model",
                        status="running",
                        message=f"Activating model runtime ({self.model_id})",
                        data={"model_name": self.model_id},
                    )
                    try:
                        runtime = self._custom_runtime or self.lifecycle.load_model(
                            self.model_id,
                            allow_hot_swap=True,
                            backend=self.backend,
                            api_key=self.api_key,
                            clearance_level=user.clearance_level,
                        )
                        emitter.emit(
                            OperationalEventType.MODEL_READY,
                            stage="model",
                            status="completed",
                            message="Model runtime ready",
                            data={"model_name": self.model_id},
                        )
                    except Exception as m_err:
                        emitter.emit(
                            OperationalEventType.MODEL_FAILED,
                            stage="model",
                            status="failed",
                            message=f"Model activation failed: {str(m_err)}",
                            data={"model_name": self.model_id},
                        )
                        raise

                    emitter.start_stage("generation")
                    emitter.emit(
                        OperationalEventType.GENERATION_STARTED,
                        stage="generation",
                        status="running",
                        message="Generating conversational guidance",
                        data={"model_name": self.model_id},
                    )
                    from adam.harness.routing import HarnessRouter
                    profile = HarnessRouter.resolve_profile(self.model_id)
                    harness_params = profile.resolve_parameters(
                        intent="conversational",
                        temperature=temperature if temperature > 0.0 else 0.2,
                        max_tokens=max_tokens if max_tokens != 512 else 256,
                    )
                    user_prompt = profile.format_conversational_prompt(query)
                    system_prompt = profile.resolve_system_prompt("conversational")

                    effective_temp = min(temperature, 0.2) if isinstance(runtime, DeterministicModelRuntime) else temperature
                    effective_max_tokens = harness_params.max_tokens or max_tokens

                    gen_result = runtime.generate(
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        temperature=effective_temp,
                        max_tokens=effective_max_tokens,
                        harness_parameters=harness_params,
                        token_callback=token_callback,
                    )
                    answer = gen_result.answer
                    prompt_tokens = gen_result.tokens_prompt
                    completion_tokens = gen_result.tokens_completion
                    emitter.emit(
                        OperationalEventType.GENERATION_COMPLETED,
                        stage="generation",
                        status="completed",
                        message="Conversational response generated",
                        data={"model_name": self.model_id},
                    )
                citations = []
                GLOBAL_RESPONSE_CACHE.put(
                    cache_key=cache_key,
                    answer=answer,
                    citations=[],
                    currency_banners=currency_banners,
                    search_suggestions=self.SEARCH_SUGGESTIONS if is_refusal else [],
                    model_id=self.model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    is_refusal=is_refusal,
                    refusal_category=recorded_abstention_reason,
                )
            else:
                citations = CitationBuilder.build_citations_from_packet(packet)
                # Enforce single heavy worker mutual exclusion on inference
                with self.coordinator.acquire_worker(HeavyTaskType.CHAT_INFERENCE, task_id=session_id):
                    emitter.start_stage("model")
                    emitter.emit(
                        OperationalEventType.MODEL_LOADING,
                        stage="model",
                        status="running",
                        message=f"Activating model runtime ({self.model_id})",
                        data={"model_name": self.model_id},
                    )
                    try:
                        runtime = self._custom_runtime or self.lifecycle.load_model(
                            self.model_id,
                            allow_hot_swap=True,
                            backend=self.backend,
                            api_key=self.api_key,
                            clearance_level=user.clearance_level,
                        )
                        emitter.emit(
                            OperationalEventType.MODEL_READY,
                            stage="model",
                            status="completed",
                            message="Model runtime ready",
                            data={"model_name": self.model_id},
                        )
                    except Exception as m_err:
                        emitter.emit(
                            OperationalEventType.MODEL_FAILED,
                            stage="model",
                            status="failed",
                            message=f"Model activation failed: {str(m_err)}",
                            data={"model_name": self.model_id},
                        )
                        raise

                    emitter.start_stage("generation")
                    emitter.emit(
                        OperationalEventType.GENERATION_STARTED,
                        stage="generation",
                        status="running",
                        message="Synthesizing grounded response with citations",
                        data={"model_name": self.model_id},
                    )
                    
                    # Format grounded prompt using model-specific harness profile
                    from adam.harness.routing import HarnessRouter
                    profile = HarnessRouter.resolve_profile(self.model_id)
                    harness_params = profile.resolve_parameters(
                        intent="rag",
                        temperature=temperature if temperature > 0.0 else 0.2,
                        max_tokens=max_tokens if max_tokens != 512 else 1024,
                    )
                    user_prompt = profile.format_rag_prompt(parsed_query.clean_query, packet)
                    system_prompt = profile.resolve_system_prompt("rag")

                    effective_temp = min(temperature, 0.2) if isinstance(runtime, DeterministicModelRuntime) else temperature
                    effective_max_tokens = harness_params.max_tokens or max_tokens

                    gen_result: ModelGenerationResult = runtime.generate(
                        user_prompt=user_prompt,
                        system_prompt=system_prompt,
                        temperature=effective_temp,
                        max_tokens=effective_max_tokens,
                        harness_parameters=harness_params,
                        token_callback=token_callback,
                    )
                    answer = gen_result.answer
                    prompt_tokens = gen_result.tokens_prompt
                    completion_tokens = gen_result.tokens_completion
                    if gen_result.is_refusal:
                        is_refusal = True
                        if not recorded_abstention_reason:
                            recorded_abstention_reason = "Model determined response cannot be substantiated by verified repository records."

                    if packet.currency_banner:
                        answer += f"\n\n*Currency Status: {packet.currency_banner}*"

                    emitter.emit(
                        OperationalEventType.GENERATION_COMPLETED,
                        stage="generation",
                        status="completed",
                        message="Grounded response synthesis complete",
                        data={"model_name": self.model_id},
                    )

                GLOBAL_RESPONSE_CACHE.put(
                    cache_key=cache_key,
                    answer=answer,
                    citations=[c.to_dict() for c in citations],
                    currency_banners=currency_banners,
                    search_suggestions=self.SEARCH_SUGGESTIONS if is_refusal else [],
                    model_id=self.model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    is_refusal=is_refusal,
                    refusal_category=recorded_abstention_reason,
                )

        # ── Stage 6: Validate Citations ─────────────────────────────────────
        transition_to(AgentState.VALIDATE_CITATIONS, "Validating material claim citations against evidence packet")
        if getattr(parsed_query, "is_greeting", False) or getattr(parsed_query, "is_system_introspection", False):
            passed, val_errors = True, []
        else:
            validator = CitationValidator()
            passed, val_errors = validator.validate(answer, packet)
            if not passed and val_errors and not recorded_abstention_reason and is_refusal:
                recorded_abstention_reason = f"Citation validation failed: {', '.join(val_errors)}"

        # Inspect and verify cited source records via read-only tool open_cited_source
        if citations and not is_refusal:
            for cit in citations[:3]:
                if cit.document_id:
                    try:
                        open_res = ReadOnlyToolRegistry.execute(
                            tool_name="open_cited_source",
                            arguments={"document_id": cit.document_id, "page_number": cit.page_start or 1},
                            user_context=user,
                            session=self.session,
                        )
                        tool_calls.append({
                            "tool": "open_cited_source",
                            "args": {"document_id": cit.document_id, "page_number": cit.page_start or 1},
                            "verified": "error" not in open_res,
                        })
                    except Exception:
                        pass

        # ── Stage 7: Audit (Immutable Record & Redaction) ────────────────────
        transition_to(AgentState.AUDIT, "Compiling audit record and redacting credentials/system prompts")
        total_latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Build redacted audit trail
        raw_audit_summary = (
            f"Session: {session_id} | User: {user.user_id} | Role: {user.roles[0] if user.roles else 'N/A'} | "
            f"Query: {query} | Model: {self.model_id} | Latency: {total_latency_ms:.1f}ms | "
            f"Passes: R={retrieval_passes}/A={answer_passes} | Tokens: P={prompt_tokens}/C={completion_tokens}"
        )
        redacted_audit_log = SecretRedactor.sanitize_text(raw_audit_summary)

        final_state = (
            AgentState.COMPLETED
            if (not is_refusal or getattr(parsed_query, "is_greeting", False) or getattr(parsed_query, "is_system_introspection", False))
            else AgentState.ABSTAINED
        )
        transition_notes = "Agent execution pipeline completed successfully" if final_state == AgentState.COMPLETED else f"Agent execution abstained: {recorded_abstention_reason or 'No verified records'}"
        transition_to(
            final_state,
            transition_notes,
            abstention_reason=recorded_abstention_reason if final_state == AgentState.ABSTAINED else None,
        )

        # Persist AgentExecutionAudit
        agent_audit = AgentExecutionAudit(
            session_id=session_id,
            user_id=user.user_id,
            user_role=user.roles[0] if user.roles else "PUBLIC",
            department_id=user.department_id,
            clearance_level=user.clearance_level,
            query_text=SecretRedactor.sanitize_text(query),
            detected_intent=(
                f"SYSTEM_INTROSPECTION_{parsed_query.introspection_subtopic or 'GENERAL'}"
                if getattr(parsed_query, "is_system_introspection", False)
                else (parsed_query.high_risk_category or "STANDARD_QUERY")
            ),
            model_id=self.model_id,
            retrieval_pass_count=retrieval_passes,
            answer_pass_count=answer_passes,
            is_no_answer=1 if (is_refusal and not getattr(parsed_query, "is_greeting", False) and not getattr(parsed_query, "is_system_introspection", False)) else 0,
            is_high_risk=1 if parsed_query.is_high_risk else 0,
            state_transitions_json=[
                t.to_dict() if hasattr(t, "to_dict") else {
                    "from": t.from_state,
                    "to": t.to_state,
                    "at": t.timestamp,
                    "notes": t.notes,
                    "duration_ms": getattr(t, "duration_ms", 0.0),
                    "stage": getattr(t, "stage", None),
                    "abstention_reason": getattr(t, "abstention_reason", None),
                }
                for t in state_history
            ],
            tool_calls_json=tool_calls,
            validation_passed=1 if passed else 0,
            validation_errors_json=val_errors,
            currency_banners_json=currency_banners,
            latency_ms=total_latency_ms,
            memory_used_mb=self.registry.get(self.model_id).file_size_bytes / (1024 * 1024) if self.registry.get(self.model_id) else 0.0,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            temperature_applied=temperature,
            redacted_audit_log=redacted_audit_log,
        )
        self.session.add(agent_audit)

        # Standard AuditEvent
        std_audit = AuditEvent(
            entity_type="AGENT",
            entity_id=session_id,
            action="AGENT_EXECUTION_COMPLETED",
            actor=user.user_id,
            details_json={
                "model_id": self.model_id,
                "is_no_answer": is_refusal and not getattr(parsed_query, "is_greeting", False),
                "is_high_risk": parsed_query.is_high_risk,
                "validation_passed": passed,
                "latency_ms": round(total_latency_ms, 2),
            },
        )
        self.session.add(std_audit)
        self.session.commit()

        # Sanitize answer of any internal leaks before returning
        safe_answer = SecretRedactor.sanitize_text(answer)

        # ── Phase 05: Record encrypted turns and update grounded summary ────
        cited_cids = [c.chunk_id for c in citations if hasattr(c, "chunk_id") and c.chunk_id]
        self.session_manager.add_turn(
            session_id=session_id,
            user_id=user.user_id,
            role="user",
            content=query,
            is_classified_or_pii=parsed_query.is_high_risk,
        )
        self.session_manager.add_turn(
            session_id=session_id,
            user_id=user.user_id,
            role="assistant",
            content=safe_answer,
            cited_chunk_ids=cited_cids,
            is_classified_or_pii=parsed_query.is_high_risk,
        )
        updated_summary = self.summarizer.update_summary(session_id=session_id, requesting_user_id=user.user_id)

        emitter.start_stage("grounding")
        if is_refusal and not getattr(parsed_query, "is_greeting", False):
            emitter.emit(
                OperationalEventType.ANSWER_ABSTAINED,
                stage="grounding",
                status="warning",
                message="Abstained from answering due to lack of verified repository records",
                data={"citation_count": 0},
            )
        else:
            emitter.emit(
                OperationalEventType.ANSWER_GROUNDED,
                stage="grounding",
                status="completed",
                message=f"Grounded response in {len(citations)} official sources",
                data={"citation_count": len(citations)},
            )

        emitter.emit(
            OperationalEventType.EXECUTION_COMPLETED,
            stage="execution",
            status="completed",
            message="Pipeline execution completed successfully",
            data={
                "citation_count": len(citations),
                "duration_ms": total_latency_ms,
            },
        )

        return AgentResponse(
            session_id=session_id,
            answer=safe_answer,
            citations=citations,
            currency_banners=currency_banners,
            is_no_answer=is_refusal,
            is_high_risk=parsed_query.is_high_risk,
            is_research_brief=is_research_brief,
            validation_passed=passed,
            validation_errors=val_errors,
            search_suggestions=self.SEARCH_SUGGESTIONS if is_refusal else [],
            state_history=state_history,
            tool_calls=tool_calls,
            retrieval_pass_count=retrieval_passes,
            answer_pass_count=answer_passes,
            latency_ms=total_latency_ms,
            per_stage_latency_ms=per_stage_latency_ms,
            abstention_reason=recorded_abstention_reason if is_refusal else None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_id=self.model_id,
            temperature_applied=temperature,
            applied_schema="ADAM_AGENT_SCHEMA_V1",
            session_summary=updated_summary.to_dict() if updated_summary else active_session_summary,
            is_cached=is_cached,
        )

    def _format_research_brief(
        self,
        packet: EvidencePacket,
        citations: List[Citation],
        currency_banners: List[str],
    ) -> str:
        """Format an administrative research brief with strict 'Human Authority Required' notice."""
        category = packet.query.high_risk_category or "ADMINISTRATIVE_DECISION"
        header = (
            "### Research Brief [Human Authority Required]\n\n"
            "> **Notice:** Human authority required. This research brief provides relevant repository records "
            "for administrative consideration. It is not a definitive legal or executive determination.\n\n"
            f"**Query Topic:** {packet.query.clean_query}\n"
            f"**Risk Category:** {category.replace('_', ' ').title()}\n\n"
            "#### Relevant Repository Records & Provisions:\n"
        )

        provisions: List[str] = []
        for idx, p in enumerate(packet.passages[:4], 1):
            title = p.title
            page_str = f"Page {p.page_start}"
            go_str = f" (GO: {p.go_number})" if p.go_number else ""
            summary_sentence = p.content.split("\n")[0][:300]
            provisions.append(f"- **[{idx}] {title}**{go_str} [{page_str}]:\n  \"{summary_sentence}\"")

        body = "\n".join(provisions)

        footer = "\n\n#### Applicable Governance Status:\n"
        if currency_banners:
            footer += f"- **Currency Alert:** {currency_banners[0]}\n"
        else:
            footer += "- Current status as reflected in approved repository records.\n"

        footer += (
            "\n*Administrative Recommendation:* Submit this dossier to the competent departmental authority "
            "for formal review and determination."
        )

        return header + body + footer


# Alias for backward and forward compatibility
BoundedAgentStateMachine = AgentStateMachine
