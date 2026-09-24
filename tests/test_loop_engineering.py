"""Comprehensive Unit Tests for ADAM Loop Engineering Framework.

Validates:
1. Cycle and oscillation detection (exact duplicates, length-2 cycles, length-3 cycles).
2. Multi-dimensional execution budget watchdog (latency, tokens, quotas, soft deadlines).
3. Convergence detection and early-exit heuristics.
4. Self-correction and iterative refinement loop (Generate -> Validate -> Critique -> Refine).
5. Fallback abstention upon refinement exhaustion.
6. Autonomous Plan-Execute-Verify (PEV) coordinated loop execution.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from adam.agent.planner import AgentExecutionPlan, PlanStep, StepStatus, TaskComplexity
from adam.loops.budget import BudgetStatus, ExecutionBudgetWatchdog
from adam.loops.controller import LoopExecutionTrace, PlanExecuteVerifyLoop
from adam.loops.cycles import CycleDetector
from adam.loops.refinement import (
    RefinementIteration,
    RefinementLoopController,
    RefinementResult,
)
from adam.model.runtime import BaseModelRuntime, ModelGenerationResult
from adam.rag.models import EvidencePacket, EvidencePassage, ParsedQuery, UserContext


# ── 1. Cycle and Oscillation Detection Tests ─────────────────────────────────

def test_cycle_detector_suppresses_exact_duplicate():
    """Verify that calling the exact same tool with identical arguments is intercepted."""
    detector = CycleDetector()
    args = {"query": "DA revision 2024", "department_id": "FINANCE"}

    assert detector.is_exact_duplicate("search", args) is False
    detector.record_action(1, "search", args, time.perf_counter())

    # Second identical call must be flagged
    assert detector.is_exact_duplicate("search", args) is True
    should_term, reason = detector.should_terminate("search", args)
    assert should_term is True
    assert "Duplicate tool call suppressed" in reason


def test_cycle_detector_detects_length_2_oscillation():
    """Verify detection of alternating cycle: Search -> Precedent -> Search -> Precedent."""
    detector = CycleDetector(max_cycle_length=3)
    args_a = {"query": "GO 101"}
    args_b = {"go_number": "101"}

    # Turn 1: Action A
    detector.record_action(1, "search", args_a, time.perf_counter())
    assert detector.detect_cycle() is None

    # Turn 2: Action B
    detector.record_action(2, "precedent", args_b, time.perf_counter())
    assert detector.detect_cycle() is None

    # Turn 3: Action A
    detector.record_action(3, "search", args_a, time.perf_counter())
    assert detector.detect_cycle() is None

    # Turn 4: Action B -> completes cycle A -> B -> A -> B
    detector.record_action(4, "precedent", args_b, time.perf_counter())
    cycle = detector.detect_cycle()
    assert cycle is not None
    cycle_len, pattern = cycle
    assert cycle_len == 2
    assert len(pattern) == 2


def test_cycle_detector_detects_length_3_cycle():
    """Verify detection of 3-step cycle: A -> B -> C -> A -> B -> C."""
    detector = CycleDetector(max_cycle_length=3)
    a, b, c = {"q": "1"}, {"q": "2"}, {"q": "3"}

    # Pattern A, B, C
    detector.record_action(1, "search", a, time.perf_counter())
    detector.record_action(2, "compute", b, time.perf_counter())
    detector.record_action(3, "web_search", c, time.perf_counter())

    # Repeating Pattern A, B, C
    detector.record_action(4, "search", a, time.perf_counter())
    detector.record_action(5, "compute", b, time.perf_counter())
    detector.record_action(6, "web_search", c, time.perf_counter())

    cycle = detector.detect_cycle()
    assert cycle is not None
    assert cycle[0] == 3


def test_cycle_detector_action_frequency_ceiling():
    """Verify per-action frequency caps."""
    detector = CycleDetector(max_action_frequency=2)
    detector.record_action(1, "compute", {"code": "1+1"}, time.perf_counter())
    detector.record_action(2, "compute", {"code": "2+2"}, time.perf_counter())

    assert detector.is_frequency_exceeded("compute") is True
    should_term, reason = detector.should_terminate("compute", {"code": "3+3"})
    assert should_term is True
    assert "frequency ceiling reached" in reason


# ── 2. Multi-Dimensional Execution Budget Tests ──────────────────────────────

def test_budget_watchdog_quotas():
    """Verify step, retrieval, computation, and subagent invocation quota enforcement."""
    watchdog = ExecutionBudgetWatchdog(
        max_steps=3,
        max_retrievals=1,
        max_computations=1,
    )

    allowed, _ = watchdog.is_action_allowed("search")
    assert allowed is True
    watchdog.record_step("search")

    # Second search exceeds retrieval quota
    allowed, reason = watchdog.is_action_allowed("search")
    assert allowed is False
    assert "Retrieval budget exhausted" in reason

    # Computation is allowed
    allowed, _ = watchdog.is_action_allowed("compute")
    assert allowed is True
    watchdog.record_step("compute")

    # Exceeding computation quota
    allowed, reason = watchdog.is_action_allowed("compute")
    assert allowed is False
    assert "Computation budget exhausted" in reason


def test_budget_watchdog_convergence_and_early_exit():
    """Verify early exit triggers when evidence confidence crosses convergence threshold."""
    watchdog = ExecutionBudgetWatchdog()
    assert watchdog.get_status().can_early_exit is False

    # Mark evidence sufficient with 0.90 confidence
    watchdog.update_convergence(is_sufficient=True, confidence=0.90)
    status = watchdog.get_status()
    assert status.can_early_exit is True
    assert "Evidence converged" in (status.early_exit_reason or "")


def test_budget_watchdog_refinement_budget():
    """Verify that refinement passes are strictly capped at max_refinements."""
    watchdog = ExecutionBudgetWatchdog(max_refinements=2)
    assert watchdog.is_refinement_allowed()[0] is True
    watchdog.record_refinement()
    assert watchdog.is_refinement_allowed()[0] is True
    watchdog.record_refinement()

    # 3rd pass must be blocked
    allowed, reason = watchdog.is_refinement_allowed()
    assert allowed is False
    assert "Max refinement passes reached" in reason


# ── 3. Self-Correction Refinement Loop Tests ─────────────────────────────────

class MockRefiningRuntime(BaseModelRuntime):
    """Mock runtime simulating a draft that gets corrected in the second pass."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.call_count = 0

    def generate(self, user_prompt: str, **kwargs) -> ModelGenerationResult:
        resp = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return ModelGenerationResult(
            answer=resp,
            raw_completion=resp,
            tokens_prompt=50,
            tokens_completion=50,
            model_id="mock_model",
            latency_ms=10.0,
            temperature=0.1,
            finish_reason="stop",
            is_refusal=False,
        )

    def is_available(self) -> bool:
        return True


def test_refinement_loop_fast_path_when_passed():
    """Verify that when initial draft is already valid, 0 refinement iterations are run."""
    mock_rt = MockRefiningRuntime(["Unused"])
    controller = RefinementLoopController(runtime=mock_rt)

    packet = EvidencePacket(
        query=ParsedQuery(raw_query="q", clean_query="q"),
        passages=[],
    )
    result = controller.run_refinement_loop(
        initial_answer="Valid initial answer.",
        initial_passed=True,
        initial_errors=[],
        query="What is the rule?",
        packet=packet,
    )

    assert result.was_refined is False
    assert result.iterations_count == 0
    assert result.validation_passed is True
    assert mock_rt.call_count == 0


def test_refinement_loop_successfully_resolves_error():
    """Verify that critique feedback successfully corrects an ungrounded claim."""
    # Passage contains 50% DA
    passage = EvidencePassage(
        chunk_id="c1",
        document_id="doc1",
        version_id="v1",
        title="DA Order",
        department_id="FIN",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="DA",
        content="DA rate is 50% effective from 01-01-2024 under GO/FIN/2024/01.",
        go_number="GO/FIN/2024/01",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="What is the DA rate?", clean_query="What is the DA rate?"),
        passages=[passage],
    )

    # Initial draft had hallucinated 55%
    initial_draft = "The DA rate is 55% as per GO/FIN/2024/01 [1]."
    initial_errors = ["Material claim [MONEY_AMOUNT: '55%'] not found in retrieved evidence passages."]

    # Second pass corrects to 50%
    corrected_draft = "The DA rate is 50% as per GO/FIN/2024/01 [1]."
    mock_rt = MockRefiningRuntime([corrected_draft])

    controller = RefinementLoopController(runtime=mock_rt, max_refinements=2)
    result = controller.run_refinement_loop(
        initial_answer=initial_draft,
        initial_passed=False,
        initial_errors=initial_errors,
        query="What is the DA rate?",
        packet=packet,
    )

    assert result.was_refined is True
    assert result.validation_passed is True
    assert result.iterations_count == 1
    assert "50%" in result.final_answer
    assert mock_rt.call_count == 1


def test_refinement_loop_falls_back_to_abstention_on_exhaustion():
    """Verify that if model fails to fix hallucinations within 2 passes, it safely abstains."""
    passage = EvidencePassage(
        chunk_id="c1",
        document_id="doc1",
        version_id="v1",
        title="DA Order",
        department_id="FIN",
        doc_type="ORDER",
        page_start=1,
        page_end=1,
        section_heading="DA",
        content="DA rate is 50% effective from 01-01-2024.",
    )
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="What is the DA rate?", clean_query="What is the DA rate?"),
        passages=[passage],
    )

    # Runtime repeatedly hallucinates ungrounded amounts
    stubborn_runtime = MockRefiningRuntime([
        "The DA rate is 60% on 2025-01-01.",
        "The DA rate is 65% on 2026-01-01.",
    ])

    controller = RefinementLoopController(runtime=stubborn_runtime, max_refinements=2)
    result = controller.run_refinement_loop(
        initial_answer="Initial hallucinated 58%.",
        initial_passed=False,
        initial_errors=["Material claim [MONEY_AMOUNT: '58%'] not found."],
        query="What is the DA rate?",
        packet=packet,
    )

    assert result.was_refined is True
    assert result.validation_passed is False
    assert result.fell_back_to_abstention is True
    assert result.final_answer == "I could not establish this from the approved repository."
    assert stubborn_runtime.call_count == 2


# ── 4. Plan-Execute-Verify (PEV) Loop Controller Tests ───────────────────────

def test_pev_loop_skips_cyclic_steps_and_synthesizes():
    """Verify that the PEV loop skips cyclic steps and executes synthesis cleanly."""
    plan = AgentExecutionPlan(
        query="Verify procurement rules",
        complexity=TaskComplexity.MULTI_STEP_ANALYSIS,
        plan_summary="Two searches and synthesis",
        steps=[
            PlanStep(1, "Search 1", "Search rules", "search", {"query": "rules"}),
            PlanStep(2, "Search 1 Duplicate", "Duplicate search", "search", {"query": "rules"}),
            PlanStep(3, "Synthesize", "Final output", "synthesize"),
        ],
    )

    mock_rt = MockRefiningRuntime(["Under procurement rules [1], limit is ₹50,000."])
    pev = PlanExecuteVerifyLoop(
        session=MagicMock(),
        runtime=mock_rt,
        max_runtime_seconds=10.0,
    )

    def dummy_executor(step: PlanStep, watchdog: ExecutionBudgetWatchdog):
        return {"verified": True}

    def dummy_synthesis(p: AgentExecutionPlan, watchdog: ExecutionBudgetWatchdog):
        return {
            "answer": "Grounded answer under rules [1].",
            "validation_passed": True,
            "validation_errors": [],
        }

    user = UserContext()
    res, trace = pev.execute_pev_loop(
        plan=plan,
        user_context=user,
        step_executor=dummy_executor,
        synthesis_handler=dummy_synthesis,
    )

    assert trace.steps_completed == 1
    assert trace.steps_skipped_cycle == 1
    assert plan.steps[1].status == StepStatus.COMPLETED
    assert "Skipped: Duplicate tool call suppressed" in plan.steps[1].result_summary
    assert res["validation_passed"] is True
