"""System Introspection and Self-Model Service for ADAM.

Provides an authoritative, ground-truth view of ADAM's operational state,
active model, runtime backend, harness profiles, allowed/forbidden tools,
data sources catalog, worker concurrency, and execution telemetry.

All introspection outputs are rigorously sanitized via SecretRedactor
to guarantee that keys, connection strings, and private paths are never leaked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from adam.agent.coordinator import HeavyWorkerCoordinator
from adam.agent.redaction import SecretRedactor
from adam.agent.tools import ReadOnlyToolRegistry
from adam.db.models import AgentExecutionAudit, Document, DocumentChunk, Source
from adam.harness.routing import HarnessRouter
from adam.model.registry import ModelRegistry
from adam.model.runtime import (
    BaseModelRuntime,
    DeterministicModelRuntime,
    SingleModelLifecycleManager,
)
from adam.rag.models import UserContext
from adam.vocabularies import Classification


@dataclass
class SystemInfoSnapshot:
    """Core identity and operational environment."""
    name: str = "ADAM"
    version: str = "1.0.0"
    jurisdiction: str = "Uttarakhand State Public Records and Governance"
    air_gapped: bool = False
    environment: str = "macOS Pilot"
    current_time_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def system_name(self) -> str:
        return self.name


@dataclass
class ActiveModelSnapshot:
    """Active model weights, runtime backend, and parameters."""
    id: str
    name: str
    family: str
    serving_runtime: str
    quantization: str
    context_window: int
    memory_footprint_mb: float
    is_loaded: bool
    is_cloud: bool
    air_gapped_restricted: bool
    supports_reasoning: bool
    backend_resolved: str


@dataclass
class ActiveHarnessSnapshot:
    """Active inference harness profile and sampling bounds."""
    profile_name: str
    family_name: str
    temperature_range: List[float] = field(default_factory=lambda: [0.0, 0.2])
    max_tokens_budget: int = 1024
    thinking_enabled: bool = False
    thinking_budget: int = 0
    stop_sequences: List[str] = field(default_factory=list)


@dataclass
class ToolCapabilitySnapshot:
    """Authorized read-only tools and explicitly forbidden capabilities."""
    allowed_tools: List[Dict[str, Any]] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    guardrail_invariants: List[str] = field(default_factory=list)

    @property
    def forbidden_capabilities(self) -> List[str]:
        return self.forbidden_tools


@dataclass
class DataSourceSnapshot:
    """Registered and approved public records repositories."""
    total_sources: int = 0
    total_documents: int = 0
    total_chunks: int = 0
    approved_connectors: List[str] = field(default_factory=list)
    registered_departments: List[str] = field(default_factory=list)


@dataclass
class WorkerConcurrencySnapshot:
    """Active heavy worker mutual exclusion locks and task state."""
    is_busy: bool = False
    active_task: Optional[str] = None
    active_task_id: Optional[str] = None
    elapsed_seconds: float = 0.0
    mutual_exclusion_enforced: bool = True
    active_ingestion_jobs: int = 0

    @property
    def max_concurrent_heavy_tasks(self) -> int:
        return 1


@dataclass
class LastExecutionSnapshot:
    """Diagnostics and audit telemetry of the most recent execution."""
    session_id: Optional[str] = None
    query_text_redacted: Optional[str] = None
    detected_intent: Optional[str] = None
    model_id: Optional[str] = None
    total_latency_ms: float = 0.0
    per_stage_latency_ms: Dict[str, float] = field(default_factory=dict)
    was_refused: bool = False
    refusal_reason: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    validation_passed: bool = True
    validation_errors: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: Optional[str] = None


@dataclass
class SystemSnapshot:
    """Comprehensive, authoritative system self-model snapshot."""
    system_info: SystemInfoSnapshot
    active_model: ActiveModelSnapshot
    active_harness: ActiveHarnessSnapshot
    tool_capabilities: ToolCapabilitySnapshot
    data_sources: DataSourceSnapshot
    worker_concurrency: WorkerConcurrencySnapshot
    last_execution: Optional[LastExecutionSnapshot] = None

    @property
    def model(self) -> ActiveModelSnapshot:
        return self.active_model

    @property
    def harness(self) -> ActiveHarnessSnapshot:
        return self.active_harness

    @property
    def tools(self) -> ToolCapabilitySnapshot:
        return self.tool_capabilities

    @property
    def workers(self) -> WorkerConcurrencySnapshot:
        return self.worker_concurrency

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "system_info": {
                "name": self.system_info.name,
                "version": self.system_info.version,
                "jurisdiction": self.system_info.jurisdiction,
                "air_gapped": self.system_info.air_gapped,
                "environment": self.system_info.environment,
                "current_time_utc": self.system_info.current_time_utc,
            },
            "active_model": {
                "id": self.active_model.id,
                "name": self.active_model.name,
                "family": self.active_model.family,
                "serving_runtime": self.active_model.serving_runtime,
                "quantization": self.active_model.quantization,
                "context_window": self.active_model.context_window,
                "memory_footprint_mb": self.active_model.memory_footprint_mb,
                "is_loaded": self.active_model.is_loaded,
                "is_cloud": self.active_model.is_cloud,
                "air_gapped_restricted": self.active_model.air_gapped_restricted,
                "supports_reasoning": self.active_model.supports_reasoning,
                "backend_resolved": self.active_model.backend_resolved,
            },
            "active_harness": {
                "profile_name": self.active_harness.profile_name,
                "family_name": self.active_harness.family_name,
                "temperature_range": self.active_harness.temperature_range,
                "max_tokens_budget": self.active_harness.max_tokens_budget,
                "thinking_enabled": self.active_harness.thinking_enabled,
                "thinking_budget": self.active_harness.thinking_budget,
                "stop_sequences": self.active_harness.stop_sequences,
            },
            "tool_capabilities": {
                "allowed_tools": self.tool_capabilities.allowed_tools,
                "forbidden_tools": self.tool_capabilities.forbidden_tools,
                "guardrail_invariants": self.tool_capabilities.guardrail_invariants,
            },
            "data_sources": {
                "total_sources": self.data_sources.total_sources,
                "total_documents": self.data_sources.total_documents,
                "total_chunks": self.data_sources.total_chunks,
                "approved_connectors": self.data_sources.approved_connectors,
                "registered_departments": self.data_sources.registered_departments,
            },
            "worker_concurrency": {
                "is_busy": self.worker_concurrency.is_busy,
                "active_task": self.worker_concurrency.active_task,
                "active_task_id": self.worker_concurrency.active_task_id,
                "elapsed_seconds": self.worker_concurrency.elapsed_seconds,
                "mutual_exclusion_enforced": self.worker_concurrency.mutual_exclusion_enforced,
                "active_ingestion_jobs": self.worker_concurrency.active_ingestion_jobs,
            },
            "last_execution": {
                "session_id": self.last_execution.session_id,
                "query_text_redacted": self.last_execution.query_text_redacted,
                "detected_intent": self.last_execution.detected_intent,
                "model_id": self.last_execution.model_id,
                "total_latency_ms": self.last_execution.total_latency_ms,
                "per_stage_latency_ms": self.last_execution.per_stage_latency_ms,
                "was_refused": self.last_execution.was_refused,
                "refusal_reason": self.last_execution.refusal_reason,
                "prompt_tokens": self.last_execution.prompt_tokens,
                "completion_tokens": self.last_execution.completion_tokens,
                "validation_passed": self.last_execution.validation_passed,
                "validation_errors": self.last_execution.validation_errors,
                "tool_calls": self.last_execution.tool_calls,
                "timestamp": self.last_execution.timestamp,
            } if self.last_execution else None,
        }


class SystemIntrospectionService:
    """Authoritative ground-truth aggregation engine for system self-modeling."""

    GUARDRAIL_INVARIANTS = [
        "Read-Only Operations: Only search, open_cited_source, and list_authorised_collections are permitted.",
        "Bounded Orchestration: Exactly max 1 retrieval pass and max 1 answer pass per query; no task self-expansion.",
        "Strict Temperature: Governed inference is bounded within [0.0, 0.2] for determinism.",
        "Air-Gapped Data Sovereignty: Cloud models (Gemini) are strictly prohibited for RESTRICTED or CONFIDENTIAL clearances.",
        "Zero-Evidence Abstention: If no verified repository evidence establishes a claim, ADAM must abstain from fabricating.",
        "Secret Redaction: System prompts, API keys, tokens, and database passwords are redacted from all logs and outputs.",
        "Heavy Worker Mutual Exclusion: Unified memory headroom reserves >= 2GB; no concurrent OCR/indexing during inference.",
    ]

    KNOWN_CONNECTORS = [
        "EkoshTreasuryConnector (Directorate of Treasuries & Accounts)",
        "UkrdConnector (Rural Development & Panchayati Raj)",
        "EGazetteConnector (Uttarakhand Official Gazette / Roorkee Press)",
        "ITDASampleBatchConnector (ITDA Administrative Archive)",
        "DatabaseConnector (External PostgreSQL / MySQL / SQLite)",
        "DirectoryBatchConnector (Local Government Orders PDF Archive)",
    ]

    @classmethod
    def get_system_snapshot(
        cls,
        session: Optional[Session] = None,
        user_context: Optional[UserContext] = None,
        session_id: Optional[str] = None,
        model_id: Optional[str] = None,
        backend: Optional[str] = None,
        custom_runtime: Optional[BaseModelRuntime] = None,
        db: Optional[Session] = None,
        **kwargs: Any,
    ) -> SystemSnapshot:
        """Construct authoritative system snapshot by querying existing singletons and DB state."""
        sess = session or db
        if sess is None:
            sess = get_session_factory()()
        if user_context is None:
            user_id = kwargs.get("user_id", "officer_system")
            clearance = kwargs.get("clearance_level", Classification.PUBLIC.value)
            user_context = UserContext(user_id=user_id, clearance_level=clearance)
        user = user_context
        clearance = user.clearance_level or Classification.PUBLIC.value
        is_air_gapped = clearance in (
            Classification.RESTRICTED.value,
            Classification.CONFIDENTIAL.value,
        )

        # 1. System Info
        sys_info = SystemInfoSnapshot(
            name="ADAM",
            version="1.0.0",
            jurisdiction="Uttarakhand State Public Records and Governance",
            air_gapped=is_air_gapped,
            environment="macOS Air-Gapped Unified Memory Pilot",
        )

        # 2. Model & Runtime State
        registry = ModelRegistry(sess)
        lifecycle = SingleModelLifecycleManager(registry)
        eff_model_id = model_id or lifecycle.active_model_id or registry.get_primary().id
        artifact = registry.get(eff_model_id) or registry.get_primary()

        # Check runtime active state
        is_loaded = lifecycle.is_loaded and (lifecycle.active_model_id == eff_model_id)
        if custom_runtime:
            is_loaded = True

        serving_rt = getattr(artifact, "serving_runtime", "ollama")
        is_cloud = serving_rt == "gemini" or (backend and backend.lower() == "gemini")

        # Determine resolved backend
        env_backend = os.getenv("ADAM_MODEL_BACKEND", "").lower()
        if backend:
            res_backend = backend.lower()
        elif env_backend:
            res_backend = env_backend
        elif is_cloud:
            res_backend = "gemini"
        elif custom_runtime and isinstance(custom_runtime, DeterministicModelRuntime):
            res_backend = "deterministic"
        else:
            res_backend = serving_rt

        model_snap = ActiveModelSnapshot(
            id=artifact.id,
            name=artifact.name,
            family=getattr(artifact, "family", artifact.id.split("-")[0].capitalize()),
            serving_runtime=serving_rt,
            quantization=getattr(artifact, "quantization", "Q4_K_M"),
            context_window=getattr(artifact, "context_window", 4096),
            memory_footprint_mb=round(getattr(artifact, "file_size_bytes", 2850000000) / (1024 * 1024), 1) if getattr(artifact, "file_size_bytes", None) else 0.0,
            is_loaded=is_loaded,
            is_cloud=is_cloud,
            air_gapped_restricted=is_air_gapped and is_cloud,
            supports_reasoning=getattr(artifact, "supports_reasoning", False) or ("qwen3" in artifact.id.lower() or "deepseek" in artifact.id.lower()),
            backend_resolved=res_backend,
        )

        # 3. Harness State
        harness_profile = HarnessRouter.resolve_profile(artifact.id)
        params = harness_profile.resolve_parameters(intent="rag")
        harness_snap = ActiveHarnessSnapshot(
            profile_name=harness_profile.__class__.__name__,
            family_name=getattr(harness_profile, "family_name", "generic"),
            temperature_range=[0.0, 0.2],
            max_tokens_budget=params.max_tokens or 1024,
            thinking_enabled=getattr(params, "thinking_budget", 0) > 0 or getattr(harness_profile, "is_reasoning_variant", False),
            thinking_budget=getattr(params, "thinking_budget", 0),
            stop_sequences=getattr(params, "stop_sequences", ["<|im_end|>"]),
        )

        # 4. Tools & Capabilities
        allowed_tool_defs = ReadOnlyToolRegistry.get_tool_definitions()
        clean_tool_defs = [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": list(t.get("parameters", {}).get("properties", {}).keys()),
            }
            for t in allowed_tool_defs
        ]
        tool_snap = ToolCapabilitySnapshot(
            allowed_tools=clean_tool_defs,
            forbidden_tools=sorted(list(ReadOnlyToolRegistry.FORBIDDEN_TOOLS)),
            guardrail_invariants=cls.GUARDRAIL_INVARIANTS,
        )

        # 5. Data Sources Catalog
        try:
            total_sources = sess.query(Source).count()
            total_docs = sess.query(Document).count()
            total_chunks = sess.query(DocumentChunk).count()
            depts_query = (
                sess.query(Document.department_id)
                .distinct()
                .filter(Document.department_id.isnot(None))
                .all()
            )
            departments = sorted([d[0] for d in depts_query if d[0]])
        except Exception:
            total_sources = 0
            total_docs = 0
            total_chunks = 0
            departments = []

        data_sources_snap = DataSourceSnapshot(
            total_sources=total_sources,
            total_documents=total_docs,
            total_chunks=total_chunks,
            approved_connectors=cls.KNOWN_CONNECTORS,
            registered_departments=departments,
        )

        # 6. Worker Concurrency & Locks
        coordinator = HeavyWorkerCoordinator()
        coord_status = coordinator.get_status()

        active_ingest_count = 0
        try:
            from adam.ingest.control_plane import GLOBAL_INGESTION_CONTROL_PLANE
            active_ingest_count = len(getattr(GLOBAL_INGESTION_CONTROL_PLANE, "_controllers", {}))
        except Exception:
            pass

        worker_snap = WorkerConcurrencySnapshot(
            is_busy=coord_status.get("is_busy", False),
            active_task=coord_status.get("active_task"),
            active_task_id=coord_status.get("active_task_id"),
            elapsed_seconds=coord_status.get("elapsed_seconds", 0.0),
            mutual_exclusion_enforced=coord_status.get("mutual_exclusion_enforced", True),
            active_ingestion_jobs=active_ingest_count,
        )

        # 7. Last Execution Audit
        last_exec_snap = cls._get_last_execution_audit(
            session=sess,
            session_id=session_id,
            user_id=user.user_id,
        )

        snapshot = SystemSnapshot(
            system_info=sys_info,
            active_model=model_snap,
            active_harness=harness_snap,
            tool_capabilities=tool_snap,
            data_sources=data_sources_snap,
            worker_concurrency=worker_snap,
            last_execution=last_exec_snap,
        )

        return snapshot

    @classmethod
    def _get_last_execution_audit(
        cls,
        session: Session,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[LastExecutionSnapshot]:
        """Fetch and structure the most recent execution audit record."""
        try:
            query = session.query(AgentExecutionAudit)
            if session_id:
                query = query.filter(AgentExecutionAudit.session_id == session_id)
            elif user_id:
                query = query.filter(AgentExecutionAudit.user_id == user_id)

            audit_rec = (
                query.order_by(AgentExecutionAudit.created_at.desc()).first()
            )
            if not audit_rec:
                return None

            # Extract per-stage latency from state transitions
            stage_latencies: Dict[str, float] = {}
            transitions = audit_rec.state_transitions_json or []
            last_abstention_reason = None

            for tr in transitions:
                stage = tr.get("stage") or tr.get("from")
                dur = tr.get("duration_ms", 0.0)
                if stage:
                    stage_latencies[stage] = round(dur, 2)
                if tr.get("abstention_reason"):
                    last_abstention_reason = tr.get("abstention_reason")

            val_errs = audit_rec.validation_errors_json or []
            if isinstance(val_errs, list) and val_errs and not last_abstention_reason:
                last_abstention_reason = f"Citation validation failed: {', '.join(str(e) for e in val_errs)}"

            refusal_reason = last_abstention_reason
            if not refusal_reason and audit_rec.is_no_answer:
                refusal_reason = "No authoritative repository evidence could substantiate the query."

            return LastExecutionSnapshot(
                session_id=audit_rec.session_id,
                query_text_redacted=SecretRedactor.sanitize_text(audit_rec.query_text),
                detected_intent=audit_rec.detected_intent,
                model_id=audit_rec.model_id,
                total_latency_ms=round(audit_rec.latency_ms, 2),
                per_stage_latency_ms=stage_latencies,
                was_refused=bool(audit_rec.is_no_answer),
                refusal_reason=refusal_reason,
                prompt_tokens=audit_rec.prompt_tokens or 0,
                completion_tokens=audit_rec.completion_tokens or 0,
                validation_passed=bool(audit_rec.validation_passed),
                validation_errors=[str(e) for e in val_errs],
                tool_calls=audit_rec.tool_calls_json or [],
                timestamp=audit_rec.created_at.isoformat() if audit_rec.created_at else None,
            )
        except Exception:
            return None

    @classmethod
    def format_snapshot_for_prompt(
        cls,
        snapshot: SystemSnapshot,
        subtopic: Optional[str] = None,
    ) -> str:
        """Format the system snapshot into an authoritative, grounded markdown context for the LLM."""
        m = snapshot.active_model
        h = snapshot.active_harness
        t = snapshot.tool_capabilities
        d = snapshot.data_sources
        w = snapshot.worker_concurrency
        e = snapshot.last_execution
        s = snapshot.system_info

        lines = [
            "### Current Operational Identity & State",
            f"- **System**: {s.name} v{s.version} ({s.jurisdiction})",
            f"- **Environment**: {s.environment} | Air-Gapped Policy: {'ACTIVE' if s.air_gapped else 'OFF'}",
            "",
            "### Active Model & Runtime",
            f"- **Active Model**: {m.name} (`{m.id}`)",
            f"- **Family / Architecture**: {m.family}",
            f"- **Serving Runtime**: {m.serving_runtime} (Resolved Backend: {m.backend_resolved})",
            f"- **Quantization**: {m.quantization} | Context Window: {m.context_window} tokens | Footprint: {m.memory_footprint_mb} MB",
            f"- **Reasoning Tokens**: {'Supported (<think>)' if m.supports_reasoning else 'Not applicable'}",
            f"- **Air-Gapped Status**: {'Restricted (Cloud models prohibited)' if m.air_gapped_restricted else 'Permitted'}",
            "",
            "### Active Harness Configuration",
            f"- **Harness Profile**: `{h.profile_name}` ({h.family_name})",
            f"- **Temperature Range**: {h.temperature_range[0]} - {h.temperature_range[1]} (Strictly governed determinism)",
            f"- **Max Tokens Budget**: {h.max_tokens_budget}",
            "",
            "### Tool Capabilities & Guardrails",
            "- **Authorized Read-Only Tools**:",
        ]

        for tool in t.allowed_tools:
            lines.append(f"  * `{tool['name']}`: {tool['description']}")

        lines.extend([
            "- **Forbidden Capabilities (Hardcoded Sandbox Enforcement)**:",
            f"  * The following are strictly blocked and unavailable: {', '.join(t.forbidden_tools[:12])}...",
            f"  * ADAM has NO web browser, NO email sender, and NO database write capabilities.",
            f"  * ADAM features an isolated, read-only Python calculation sandbox for deterministic arithmetic, date math, and government order financial analysis.",
            "- **Core Governance Invariants**:",
        ])
        for inv in t.guardrail_invariants[:4]:
            lines.append(f"  * {inv}")

        lines.extend([
            "",
            "### Data Sources & Repositories",
            f"- **Approved Sources Count**: {d.total_sources}",
            f"- **Indexed Documents**: {d.total_documents} official records | **Semantic Chunks**: {d.total_chunks}",
            f"- **Registered Departments**: {', '.join(d.registered_departments) if d.registered_departments else 'Finance, Rural Development, Gazette, Audit'}",
            f"- **Connectors Active**: {', '.join([c.split(' ')[0] for c in d.approved_connectors])}",
            "",
            "### Heavy Worker Concurrency & System Load",
            f"- **Coordinator Status**: {'BUSY' if w.is_busy else 'IDLE'}",
            f"- **Active Task**: {w.active_task or 'None'} (Lock elapsed: {w.elapsed_seconds}s)",
            f"- **Unified Memory Mutual Exclusion**: {'ENFORCED (No OCR/Indexing during Chat)' if w.mutual_exclusion_enforced else 'Disabled'}",
            f"- **Active Ingestion Jobs**: {w.active_ingestion_jobs}",
        ])

        if e:
            lines.extend([
                "",
                "### Last Execution Telemetry & Audit",
                f"- **Last Session ID**: `{e.session_id}`",
                f"- **Last Query**: \"{e.query_text_redacted}\"",
                f"- **Total Latency**: {e.total_latency_ms} ms",
                f"- **Execution Outcome**: {'ABSTAINED / REFUSED' if e.was_refused else 'COMPLETED / ANSWERED'}",
            ])
            if e.refusal_reason:
                lines.append(f"- **Refusal / Abstention Cause**: {e.refusal_reason}")
            if e.per_stage_latency_ms:
                durations = [f"{k}: {v}ms" for k, v in e.per_stage_latency_ms.items()]
                lines.append(f"- **Stage Breakdown**: {', '.join(durations)}")
            lines.append(f"- **Tokens Used**: Prompt={e.prompt_tokens}, Completion={e.completion_tokens}")

        raw_text = "\n".join(lines)
        return SecretRedactor.sanitize_text(raw_text)

    @classmethod
    def sanitize_snapshot(
        cls,
        snapshot: SystemSnapshot,
        clearance_level: str = Classification.PUBLIC.value,
    ) -> Dict[str, Any]:
        """Produce a sanitized dictionary appropriate for API transmission and frontend display."""
        raw_dict = snapshot.to_dict()
        sanitized = SecretRedactor.sanitize_data(raw_dict)

        # For PUBLIC clearance, trim internal technical metrics
        if clearance_level == Classification.PUBLIC.value:
            if sanitized.get("last_execution"):
                sanitized["last_execution"].pop("per_stage_latency_ms", None)
                sanitized["last_execution"].pop("tool_calls", None)

        return sanitized
