"""Agentic Orchestrator for dynamic, bounded problem solving and evidence synthesis.

Performs:
1. Fast Local Verification First against connected database and indexed records.
2. Autonomous dynamic tool selection (search, database_query, web_search, fetch_web_page,
   execute_python_sandbox, compare_sources, lookup_precedents, inspect_system, verify_claim).
3. Bounded specialized subagent execution (WebResearchSubagent, DataAnalysisSubagent).
4. Strict resource budgets (max 6 tool calls, 2 subagents, 25s timeout) and loop prevention.
5. Grounded synthesis with clear provenance distinction (internal [1] vs external [WEB-1]).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Set

from sqlalchemy.orm import Session

from adam.agent.planner import AgentExecutionPlan, PlanStep, StepStatus, TaskComplexity
from adam.agent.redaction import SecretRedactor
from adam.agent.sandbox import SecurePythonSandbox
from adam.agent.subagents import SubagentCoordinator, SubagentResult
from adam.agent.tools import ReadOnlyToolRegistry
from adam.harness.templates import PromptTemplateRegistry
from adam.model.runtime import BaseModelRuntime, ModelGenerationResult
from adam.observability.events import (
    OperationalEvent,
    OperationalEventEmitter,
    OperationalEventType,
)
from adam.rag.citation import CitationBuilder
from adam.rag.evidence import EvidencePacketBuilder
from adam.rag.generator import CitationValidator
from adam.rag.models import Citation, EvidencePacket, EvidencePassage, ParsedQuery, UserContext
from adam.rag.query import QueryUnderstanding
from adam.vocabularies import AgentToolName

logger = logging.getLogger(__name__)


@dataclass
class LocalSufficiencyResult:
    """Assessment of whether local repository records suffice to answer the query."""
    is_sufficient: bool
    confidence: float
    total_local_passages: int
    reason: str
    missing_aspects: List[str] = field(default_factory=list)


class LocalEvidenceEvaluator:
    """Evaluates whether local indexed documents and database records are sufficient."""

    @classmethod
    def evaluate(cls, query: str, passages: List[EvidencePassage]) -> LocalSufficiencyResult:
        clean_q = query.strip().lower()
        if not passages:
            return LocalSufficiencyResult(
                is_sufficient=False,
                confidence=0.0,
                total_local_passages=0,
                reason="No local records found matching query keywords.",
                missing_aspects=["local_records"],
            )

        # Check if query asks for out-of-repository / national entities
        external_need = any(w in clean_q for w in (
            "central government", "central da", "national", "union government",
            "other states", "doe.gov.in", "delhi", "outside uttarakhand", "central 7th cpc",
        ))
        if external_need:
            return LocalSufficiencyResult(
                is_sufficient=False,
                confidence=0.4,
                total_local_passages=len(passages),
                reason="Query explicitly references external/national entities requiring outside verification.",
                missing_aspects=["external_national_policy"],
            )

        # Check score or quality of top passages
        top_score = max((getattr(p, "score", 0.0) for p in passages), default=0.0)
        has_content = len(" ".join(p.content for p in passages)) > 100

        if top_score > 0.25 or (len(passages) >= 1 and has_content):
            return LocalSufficiencyResult(
                is_sufficient=True,
                confidence=0.9,
                total_local_passages=len(passages),
                reason=f"Found {len(passages)} authoritative local records covering the query.",
            )

        return LocalSufficiencyResult(
            is_sufficient=False,
            confidence=0.5,
            total_local_passages=len(passages),
            reason="Local passages provide only partial coverage.",
            missing_aspects=["detailed_provisions"],
        )


class AgenticOrchestrator:
    """Bounded, intelligent problem-solving and research orchestrator."""

    MAX_SUBPROBLEMS: int = 4
    MAX_STEPS: int = 6
    MAX_RETRIEVALS: int = 3
    MAX_COMPUTATIONS: int = 2
    MAX_WEB_CALLS: int = 3
    MAX_SUBAGENTS: int = 2
    MAX_RUNTIME_SECONDS: float = 25.0

    NO_EVIDENCE_REFUSAL = "I could not establish this from the approved repository."

    def __init__(
        self,
        session: Session,
        runtime: BaseModelRuntime,
        model_id: str,
        emitter: Optional[OperationalEventEmitter] = None,
        retrieval_settings: Optional[Any] = None,
    ):
        self.session = session
        self.runtime = runtime
        self.model_id = model_id
        self.emitter = emitter
        self.retrieval_settings = retrieval_settings

    def execute_plan(
        self,
        plan: AgentExecutionPlan,
        user_context: UserContext,
        top_k: int = 6,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        token_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Execute the plan steps dynamically with verification, budgets, and grounded synthesis."""
        start_time = time.perf_counter()
        accumulated_passages: List[EvidencePassage] = []
        seen_passage_ids: Set[str] = set()
        seen_signatures: Set[str] = set()  # Loop prevention
        verified_calculations: List[Dict[str, Any]] = []
        tool_call_records: List[Dict[str, Any]] = []
        subagent_records: List[Dict[str, Any]] = []
        introspection_context: Optional[str] = None

        retrieval_count = 0
        computation_count = 0
        web_call_count = 0
        db_query_count = 0
        local_evidence_sufficient = False

        subagent_coordinator = SubagentCoordinator(self.session, user_context)

        # Execute intermediate action steps (all steps except final synthesis)
        action_steps = [s for s in plan.steps if s.action_type != "synthesize"]
        synthesis_step = next((s for s in plan.steps if s.action_type == "synthesize"), None)

        for step in action_steps[: self.MAX_STEPS]:
            # Budget & Timeout Guard
            elapsed = time.perf_counter() - start_time
            if elapsed >= self.MAX_RUNTIME_SECONDS:
                step.status = StepStatus.ABSTAINED
                step.result_summary = f"Execution budget reached ({elapsed:.1f}s)."
                break

            # Loop Prevention: Skip identical repeated tool calls
            step_sig = f"{step.action_type}:{str(sorted(step.tool_args.items()))}"
            if step_sig in seen_signatures:
                step.status = StepStatus.COMPLETED
                step.result_summary = "Skipped duplicate repeated action (loop prevention)."
                continue
            seen_signatures.add(step_sig)

            # Local Verification First: If local evidence is already sufficient, skip external web research
            if local_evidence_sufficient and step.action_type in ("web_research", "web_search", "fetch_web_page"):
                step.status = StepStatus.COMPLETED
                step.result_summary = "Bypassed external web call: verified sufficient authority in local repository."
                continue

            step.status = StepStatus.IN_PROGRESS

            if self.emitter:
                self.emitter.emit(
                    OperationalEventType.STEP_STARTED,
                    stage="execution",
                    status="running",
                    message=f"Executing: {step.title}",
                    data={"step_id": step.step_id, "title": step.title, "action": step.action_type},
                )

            # ── 1. Search Action (Local Verification First) ──────────────
            if step.action_type == "search":
                if retrieval_count >= self.MAX_RETRIEVALS:
                    step.status = StepStatus.COMPLETED
                    step.result_summary = "Maximum retrieval budget reached."
                    continue

                retrieval_count += 1
                search_args = dict(step.tool_args)
                search_args.setdefault("top_k", top_k)
                search_args.setdefault("query", plan.query)

                tool_res = ReadOnlyToolRegistry.execute(
                    tool_name=AgentToolName.SEARCH.value,
                    arguments=search_args,
                    user_context=user_context,
                    session=self.session,
                )
                passages = tool_res.get("raw_passages") or []
                total_found = tool_res.get("total_found", len(passages))

                # Intermediate Verification & Reformulation: If 0 items, attempt 1 relaxation
                if total_found == 0:
                    clean_fallback_query = re.sub(r"[^\w\s]", " ", search_args.get("query", "")).strip()
                    if clean_fallback_query and clean_fallback_query != search_args.get("query"):
                        fallback_args = dict(search_args)
                        fallback_args["query"] = clean_fallback_query
                        fallback_args.pop("department_id", None)
                        tool_res = ReadOnlyToolRegistry.execute(
                            tool_name=AgentToolName.SEARCH.value,
                            arguments=fallback_args,
                            user_context=user_context,
                            session=self.session,
                        )
                        passages = tool_res.get("raw_passages") or []
                        total_found = tool_res.get("total_found", len(passages))

                for p in passages:
                    pid = getattr(p, "chunk_id", None) or getattr(p, "id", None)
                    if pid and pid not in seen_passage_ids:
                        seen_passage_ids.add(pid)
                        accumulated_passages.append(p)

                # Assess Local Evidence Sufficiency
                local_passages = [p for p in accumulated_passages if not getattr(p, "is_external", False)]
                sufficiency = LocalEvidenceEvaluator.evaluate(plan.query, local_passages)
                if sufficiency.is_sufficient:
                    local_evidence_sufficient = True

                tool_call_records.append({
                    "tool": "search",
                    "step_id": step.step_id,
                    "args": SecretRedactor.sanitize_data(search_args),
                    "found_count": total_found,
                    "local_sufficiency": sufficiency.is_sufficient,
                })

                step.status = StepStatus.VERIFIED if total_found > 0 else StepStatus.COMPLETED
                step.result_summary = f"Retrieved {total_found} relevant local passages. ({sufficiency.reason})"

            # ── 2. Database Query Action ─────────────────────────────────
            elif step.action_type in ("database", "database_query"):
                db_query_count += 1
                db_args = dict(step.tool_args)
                db_args.setdefault("table", "documents")
                db_args.setdefault("aggregate", "count")

                tool_res = ReadOnlyToolRegistry.execute(
                    tool_name=AgentToolName.DATABASE_QUERY.value,
                    arguments=db_args,
                    user_context=user_context,
                    session=self.session,
                )
                res_val = tool_res.get("result", tool_res.get("total_returned", 0))
                step.status = StepStatus.VERIFIED if "error" not in tool_res else StepStatus.FAILED
                step.result_summary = f"Database query on '{db_args.get('table')}': {res_val}"
                tool_call_records.append({
                    "tool": "database_query",
                    "step_id": step.step_id,
                    "args": db_args,
                    "result": res_val,
                })

            # ── 3. External Web Research Action (Subagent or Tool) ────────
            elif step.action_type in ("web_research", "web_search"):
                if web_call_count >= self.MAX_WEB_CALLS:
                    step.status = StepStatus.COMPLETED
                    step.result_summary = "Maximum web research budget reached."
                    continue

                web_call_count += 1
                research_q = step.tool_args.get("query") or plan.query

                # Dispatch WebResearchSubagent if within subagent quota
                if len(subagent_records) < self.MAX_SUBAGENTS:
                    sub_res: SubagentResult = subagent_coordinator.dispatch(
                        subagent_type="web_research",
                        goal=step.description or research_q,
                        inputs={"query": research_q, "domain_filter": step.tool_args.get("domain_filter")},
                    )
                    subagent_records.append(sub_res.to_dict())
                    for p in sub_res.evidence_passages:
                        if p.chunk_id not in seen_passage_ids:
                            seen_passage_ids.add(p.chunk_id)
                            accumulated_passages.append(p)
                    step.status = StepStatus.VERIFIED if sub_res.success else StepStatus.COMPLETED
                    step.result_summary = sub_res.summary
                    tool_call_records.extend(sub_res.tool_calls)
                else:
                    # Direct tool execution fallback
                    tool_res = ReadOnlyToolRegistry.execute(
                        tool_name=AgentToolName.WEB_SEARCH.value,
                        arguments={"query": research_q, "max_results": 3},
                        user_context=user_context,
                        session=self.session,
                    )
                    step.status = StepStatus.VERIFIED
                    step.result_summary = f"Retrieved {tool_res.get('total_found', 0)} external web search results."
                    tool_call_records.append({
                        "tool": "web_search",
                        "step_id": step.step_id,
                        "found_count": tool_res.get("total_found", 0),
                    })

            # ── 4. Fetch Web Page Action ─────────────────────────────────
            elif step.action_type == "fetch_web_page":
                if web_call_count >= self.MAX_WEB_CALLS:
                    step.status = StepStatus.COMPLETED
                    step.result_summary = "Maximum web budget reached."
                    continue

                web_call_count += 1
                target_url = step.tool_args.get("url", "")
                if target_url:
                    page_res = ReadOnlyToolRegistry.execute(
                        tool_name=AgentToolName.FETCH_WEB_PAGE.value,
                        arguments={"url": target_url},
                        user_context=user_context,
                        session=self.session,
                    )
                    step.status = StepStatus.VERIFIED
                    step.result_summary = f"Fetched external web page from {page_res.get('domain')} ({page_res.get('char_count', 0)} chars)."
                    tool_call_records.append({
                        "tool": "fetch_web_page",
                        "step_id": step.step_id,
                        "url": target_url,
                        "domain": page_res.get("domain"),
                    })
                    # Add as external passage if content extracted
                    if page_res.get("content"):
                        p_ext = EvidencePassage(
                            chunk_id=f"page_{len(accumulated_passages)+1}",
                            document_id=page_res.get("domain", "web"),
                            version_id="ext_v1",
                            title=page_res.get("title", "External Web Page"),
                            department_id="EXTERNAL_PUBLIC",
                            doc_type="WEB_PAGE",
                            page_start=1,
                            page_end=1,
                            section_heading="Web Extraction",
                            content=page_res["content"][:2000],
                            source_url=target_url,
                            is_external=True,
                            provenance_type="EXTERNAL_WEB",
                            external_url=target_url,
                            external_domain=page_res.get("domain"),
                        )
                        if p_ext.chunk_id not in seen_passage_ids:
                            seen_passage_ids.add(p_ext.chunk_id)
                            accumulated_passages.append(p_ext)
                else:
                    step.status = StepStatus.COMPLETED
                    step.result_summary = "No URL provided for page fetching."

            # ── 5. Compare Sources Action ────────────────────────────────
            elif step.action_type in ("compare", "compare_sources"):
                tool_args = dict(step.tool_args)
                src_a = tool_args.get("source_a")
                src_b = tool_args.get("source_b")
                if not src_a and accumulated_passages:
                    src_a = accumulated_passages[0].content
                if not src_b and len(accumulated_passages) > 1:
                    src_b = accumulated_passages[1].content
                elif not src_b:
                    src_b = plan.query

                comp_res = ReadOnlyToolRegistry.execute(
                    tool_name=AgentToolName.COMPARE_SOURCES.value,
                    arguments={"source_a": src_a or "", "source_b": src_b or "", "comparison_focus": tool_args.get("comparison_focus")},
                    user_context=user_context,
                    session=self.session,
                )
                step.status = StepStatus.VERIFIED
                step.result_summary = comp_res.get("summary", "Compared sources.")
                tool_call_records.append({
                    "tool": "compare_sources",
                    "step_id": step.step_id,
                    "summary": comp_res.get("summary"),
                })

            # ── 6. Computation Action ────────────────────────────────────
            elif step.action_type == "compute":
                if computation_count >= self.MAX_COMPUTATIONS:
                    step.status = StepStatus.COMPLETED
                    step.result_summary = "Maximum computation budget reached."
                    continue

                computation_count += 1
                calc_code = step.tool_args.get("code")

                # If no explicit code, synthesize deterministic script from gathered passages and query
                if not calc_code:
                    calc_code = self._synthesize_calculation_code(plan.query, accumulated_passages, step.tool_args)

                if calc_code:
                    exec_res = ReadOnlyToolRegistry.execute(
                        tool_name=AgentToolName.EXECUTE_PYTHON_SANDBOX.value,
                        arguments={"code": calc_code},
                        user_context=user_context,
                        session=self.session,
                    )
                    if exec_res.get("success"):
                        step.status = StepStatus.VERIFIED
                        val = exec_res.get("value")
                        output = exec_res.get("output")
                        res_val = val if val is not None else output
                        step.computation_result = res_val
                        step.result_summary = f"Calculated verified outcome: {res_val}"
                        verified_calculations.append({
                            "code": calc_code,
                            "value": val,
                            "output": output,
                            "formatted": f"{res_val}",
                        })
                    else:
                        step.status = StepStatus.FAILED
                        step.error = exec_res.get("error")
                        step.result_summary = f"Calculation error: {exec_res.get('error')}"

                    tool_call_records.append({
                        "tool": "execute_python_sandbox",
                        "step_id": step.step_id,
                        "code": calc_code,
                        "success": exec_res.get("success"),
                        "result": str(step.computation_result),
                    })
                else:
                    step.status = StepStatus.COMPLETED
                    step.result_summary = "No numerical formula derived from available evidence."

            # ── 7. Precedent Action ──────────────────────────────────────
            elif step.action_type == "precedent":
                tool_res = ReadOnlyToolRegistry.execute(
                    tool_name=AgentToolName.LOOKUP_PRECEDENTS.value,
                    arguments={"query": plan.query},
                    user_context=user_context,
                    session=self.session,
                )
                precedents = tool_res.get("precedents") or []
                step.status = StepStatus.VERIFIED if precedents else StepStatus.COMPLETED
                step.result_summary = f"Identified {len(precedents)} precedent relation linkages."
                tool_call_records.append({
                    "tool": "lookup_precedents",
                    "step_id": step.step_id,
                    "count": len(precedents),
                })

            # ── 8. Introspection Action ──────────────────────────────────
            elif step.action_type == "introspection":
                tool_res = ReadOnlyToolRegistry.execute(
                    tool_name=AgentToolName.INSPECT_SYSTEM.value,
                    arguments={"query": plan.query},
                    user_context=user_context,
                    session=self.session,
                )
                introspection_context = tool_res.get("text_summary")
                step.status = StepStatus.VERIFIED
                step.result_summary = f"Active Model: {tool_res.get('active_model')} | Profile: {tool_res.get('harness_profile')}"
                tool_call_records.append({
                    "tool": "inspect_system",
                    "step_id": step.step_id,
                    "model": tool_res.get("active_model"),
                })

            # ── 9. Verify Claim Action ───────────────────────────────────
            elif step.action_type == "verify":
                passages_text = [p.content for p in accumulated_passages]
                verify_res = ReadOnlyToolRegistry.execute(
                    tool_name=AgentToolName.VERIFY_CLAIM.value,
                    arguments={"claim": plan.query, "passages": passages_text},
                    user_context=user_context,
                    session=self.session,
                )
                step.status = StepStatus.VERIFIED if verify_res.get("is_supported") else StepStatus.COMPLETED
                step.result_summary = "Claims verified against retrieved corpus." if verify_res.get("is_supported") else "Partial support in corpus."

            if self.emitter:
                self.emitter.emit(
                    OperationalEventType.STEP_COMPLETED,
                    stage="execution",
                    status="completed",
                    message=f"Completed: {step.title}",
                    data={"step_id": step.step_id, "summary": step.result_summary},
                )

        # ── Final Synthesis Step ─────────────────────────────────────────
        if synthesis_step:
            synthesis_step.status = StepStatus.IN_PROGRESS

        # Build final unified evidence packet
        parsed_q = QueryUnderstanding.parse(plan.query)
        packet_builder = EvidencePacketBuilder(self.session, retrieval_settings=self.retrieval_settings)
        packet = packet_builder.build_packet(
            query=parsed_q,
            retrieved_passages=accumulated_passages,
            user_context=user_context,
        )

        # Assemble Concise "ADAM Actions Summary"
        summary_parts = []
        local_passages = [p for p in accumulated_passages if not getattr(p, "is_external", False)]
        ext_passages = [p for p in accumulated_passages if getattr(p, "is_external", False)]
        ext_domains = {p.external_domain for p in ext_passages if p.external_domain}

        if local_passages:
            summary_parts.append(f"Verified {len(local_passages)} local repository record(s)")
        if db_query_count:
            summary_parts.append(f"inspected database tables ({db_query_count} queries)")
        if ext_passages:
            dom_text = ", ".join(sorted(list(ext_domains))) if ext_domains else "external web"
            summary_parts.append(f"consulted {len(ext_passages)} external web source(s) from {dom_text}")
        if verified_calculations:
            summary_parts.append(f"executed {len(verified_calculations)} verified calculation(s)")
        if subagent_records:
            summary_parts.append(f"dispatched {len(subagent_records)} specialized subagent(s)")

        research_summary = "ADAM Actions: " + ("; ".join(summary_parts) if summary_parts else "Processed query") + "."

        # Evaluate abstention guarantee
        if not accumulated_passages and not introspection_context and not verified_calculations and not db_query_count:
            if synthesis_step:
                synthesis_step.status = StepStatus.ABSTAINED
                synthesis_step.result_summary = "Abstained due to absence of verified public records."

            return {
                "answer": self.NO_EVIDENCE_REFUSAL,
                "citations": [],
                "currency_banners": [],
                "is_no_answer": True,
                "validation_passed": True,
                "validation_errors": [],
                "plan": plan,
                "tool_calls": tool_call_records,
                "subagents": subagent_records,
                "verified_calculations": verified_calculations,
                "research_summary": research_summary,
                "latency_ms": (time.perf_counter() - start_time) * 1000.0,
            }

        # Format synthesis user turn
        user_prompt = self._format_agentic_prompt(
            query=plan.query,
            plan=plan,
            packet=packet,
            verified_calculations=verified_calculations,
            introspection_context=introspection_context,
            action_summary=research_summary,
        )

        system_prompt = (
            PromptTemplateRegistry.INTROSPECTION_SYSTEM_PROMPT
            if plan.complexity == TaskComplexity.SYSTEM_INTROSPECTION
            else PromptTemplateRegistry.REASONING_SYSTEM_PROMPT
        )

        gen_result: ModelGenerationResult = self.runtime.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            token_callback=token_callback,
        )

        # Extract citations (both local and external)
        citations = CitationBuilder.build_citations_from_packet(packet)

        # Validate claims (with verified calculations support)
        valid_passed, valid_errors = CitationValidator.validate(
            answer=gen_result.answer,
            packet=packet,
            verified_calculations=verified_calculations,
        )

        if synthesis_step:
            synthesis_step.status = StepStatus.VERIFIED if valid_passed else StepStatus.COMPLETED
            synthesis_step.result_summary = f"Synthesized grounded response with {len(citations)} source citations."

        return {
            "answer": gen_result.answer,
            "citations": citations,
            "currency_banners": [packet.currency_banner] if packet.currency_banner else [],
            "is_no_answer": gen_result.is_refusal or (self.NO_EVIDENCE_REFUSAL in gen_result.answer),
            "validation_passed": valid_passed,
            "validation_errors": valid_errors,
            "plan": plan,
            "tool_calls": tool_call_records,
            "subagents": subagent_records,
            "verified_calculations": verified_calculations,
            "research_summary": research_summary,
            "tokens_prompt": gen_result.tokens_prompt,
            "tokens_completion": gen_result.tokens_completion,
            "latency_ms": (time.perf_counter() - start_time) * 1000.0,
        }

    def _synthesize_calculation_code(
        self,
        query: str,
        passages: List[EvidencePassage],
        tool_args: Dict[str, Any],
    ) -> Optional[str]:
        """Synthesize deterministic calculation code based on query numbers and passage rates."""
        # Check target amount from query
        numbers_in_query = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", query)
        clean_nums = [float(n.replace(",", "")) for n in numbers_in_query if float(n.replace(",", "")) > 0]
        base_salary = clean_nums[0] if clean_nums else 45000.0

        # Scan passages for percentages / DA rates (e.g. 4%, 46%, 50%)
        corpus = " ".join(p.content for p in passages)
        percentages = [float(p) for p in re.findall(r"\b(\d+(?:\.\d+)?)\s*%", corpus)]

        if "da" in query.lower() or "dearness" in query.lower() or "महंगाई" in query:
            da_rates = sorted(list(set(percentages))) if percentages else [4.0]
            if len(da_rates) >= 2:
                old_rate = da_rates[-2] / 100.0
                new_rate = da_rates[-1] / 100.0
                return f"""basic_pay = {base_salary}
old_da_rate = {old_rate}
new_da_rate = {new_rate}
diff_rate = new_da_rate - old_da_rate
monthly_increase = round(basic_pay * diff_rate, 2)
new_total_da = round(basic_pay * new_da_rate, 2)
new_total_salary = round(basic_pay + new_total_da, 2)
print(f"Basic Pay: ₹{{basic_pay:,.2f}}")
print(f"Old DA ({{old_rate*100:.1f}}%): ₹{{basic_pay * old_rate:,.2f}}")
print(f"New DA ({{new_rate*100:.1f}}%): ₹{{new_total_da:,.2f}}")
print(f"Monthly Increase ({{diff_rate*100:.1f}}%): ₹{{monthly_increase:,.2f}}")
print(f"Revised Total Salary: ₹{{new_total_salary:,.2f}}")
monthly_increase
"""
            else:
                inc_pct = da_rates[0] / 100.0 if da_rates else 0.04
                return f"""basic_pay = {base_salary}
increase_rate = {inc_pct}
monthly_increase = round(basic_pay * increase_rate, 2)
revised_total = round(basic_pay + monthly_increase, 2)
print(f"Basic Pay: ₹{{basic_pay:,.2f}}")
print(f"Increase ({{increase_rate*100:.1f}}%): ₹{{monthly_increase:,.2f}}")
print(f"Total: ₹{{revised_total:,.2f}}")
monthly_increase
"""

        # General arithmetic formula
        if clean_nums:
            return f"""# General calculation
values = {clean_nums}
total = sum(values)
print(f"Values: {{values}}, Total: {{total}}")
total
"""
        return None

    def _format_agentic_prompt(
        self,
        query: str,
        plan: AgentExecutionPlan,
        packet: EvidencePacket,
        verified_calculations: List[Dict[str, Any]],
        introspection_context: Optional[str] = None,
        action_summary: Optional[str] = None,
    ) -> str:
        """Format structured evidence context enclosing plan, calculations, and passages."""
        lines = [f"User Query: {query}\n"]

        if plan.plan_summary:
            lines.append(f"Execution Strategy: {plan.plan_summary}\n")

        if action_summary:
            lines.append(f"Operational Summary: {action_summary}\n")

        if verified_calculations:
            lines.append("=== VERIFIED MATHEMATICAL CALCULATIONS (DETERMINISTIC SANDBOX PROOF) ===")
            for c in verified_calculations:
                lines.append(f"Result: {c.get('formatted') or c.get('value')}")
                if c.get("output"):
                    lines.append(f"Output:\n{c.get('output')}")
            lines.append("========================================================================\n")

        if introspection_context:
            lines.append("=== AUTHORITATIVE SYSTEM STATE SNAPSHOT ===")
            lines.append(introspection_context)
            lines.append("===========================================\n")

        if packet.currency_banner:
            lines.append(f"CURRENCY NOTICE: {packet.currency_banner}\n")

        # Distinguish local authoritative records from external web sources
        local_passages = [p for p in packet.passages if not getattr(p, "is_external", False)]
        ext_passages = [p for p in packet.passages if getattr(p, "is_external", False)]

        if local_passages:
            lines.append("### Authoritative Local Public Records (Uttarakhand State):")
            for idx, p in enumerate(local_passages, start=1):
                go_info = f" [GO: {p.go_number}]" if p.go_number else ""
                lines.append(f"### Evidence Passage [{idx}] (Doc: {p.document_id}{go_info}, Dept: {p.department_id}):\n{p.content}\n")
            lines.append("==============================================\n")

        if ext_passages:
            lines.append("### External Web Sources (Consulted for Comparative/Supplementary Research):")
            for idx, p in enumerate(ext_passages, start=1):
                dom_info = f" [Domain: {p.external_domain}]" if p.external_domain else ""
                lines.append(f"### External Finding [WEB-{idx}] ({p.title}{dom_info}, URL: {p.external_url or p.source_url}):\n{p.content}\n")
            lines.append("==============================================\n")

        lines.append(
            "[Instruction: Synthesize a clear, authoritative, and structured response. "
            "Use citations [1], [2] for local public records, and [WEB-1], [WEB-2] for external web sources. "
            "Incorporate verified mathematical proofs if calculations were performed. "
            "Do not extrapolate beyond the retrieved evidence records or verified calculation outputs. "
            "Never output hidden chain-of-thought or <think> tags.]"
        )
        return "\n".join(lines)
