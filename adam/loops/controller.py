"""Plan-Execute-Verify (PEV) Autonomous Loop Controller for ADAM.

Coordinates multi-step agent actions with real-time reflection, cycle detection,
local evidence sufficiency checks, and critique-driven self-correction.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from adam.agent.planner import AgentExecutionPlan, PlanStep, StepStatus, TaskComplexity
from adam.agent.tools import ReadOnlyToolRegistry
from adam.loops.budget import ExecutionBudgetWatchdog
from adam.loops.cycles import CycleDetector
from adam.loops.refinement import RefinementLoopController, RefinementResult
from adam.model.runtime import BaseModelRuntime
from adam.observability.events import (
    OperationalEvent,
    OperationalEventEmitter,
    OperationalEventType,
)
from adam.prompts.personas import PersonaRole
from adam.rag.models import EvidencePacket, EvidencePassage, UserContext
from adam.vocabularies import AgentToolName

logger = logging.getLogger(__name__)


@dataclass
class LoopExecutionTrace:
    """Detailed audit trace of an autonomous execution loop."""
    steps_attempted: int
    steps_completed: int
    steps_skipped_cycle: int
    early_exited: bool
    early_exit_reason: Optional[str]
    elapsed_seconds: float
    total_tokens: int
    refinement_result: Optional[RefinementResult] = None


class PlanExecuteVerifyLoop:
    """Manages the full Plan -> Execute Steps -> Intermediate Verify -> Synthesize -> Refine loop."""

    def __init__(
        self,
        session: Session,
        runtime: BaseModelRuntime,
        max_runtime_seconds: float = 25.0,
        max_steps: int = 6,
        emitter: Optional[OperationalEventEmitter] = None,
    ):
        self.session = session
        self.runtime = runtime
        self.emitter = emitter
        self.watchdog = ExecutionBudgetWatchdog(
            max_runtime_seconds=max_runtime_seconds,
            max_steps=max_steps,
        )
        self.cycle_detector = CycleDetector(max_cycle_length=3, max_action_frequency=3)
        self.refinement_controller = RefinementLoopController(runtime=runtime, max_refinements=2)

    def execute_pev_loop(
        self,
        plan: AgentExecutionPlan,
        user_context: UserContext,
        step_executor: Callable[[PlanStep, ExecutionBudgetWatchdog], Dict[str, Any]],
        synthesis_handler: Callable[[AgentExecutionPlan, ExecutionBudgetWatchdog], Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], LoopExecutionTrace]:
        """Execute action steps within guarded loop, followed by synthesis and refinement."""
        start_time = time.perf_counter()
        action_steps = [s for s in plan.steps if s.action_type != "synthesize"]
        completed_steps = 0
        skipped_cycle_steps = 0
        early_exited = False
        early_exit_reason = None

        for step in action_steps:
            # 1. Budget and convergence checks
            allowed, block_reason = self.watchdog.is_action_allowed(step.action_type)
            if not allowed:
                step.status = StepStatus.ABSTAINED
                step.result_summary = f"Step halted by budget watchdog: {block_reason}"
                early_exited = True
                early_exit_reason = block_reason
                break

            # 2. Early-exit if evidence has converged
            budget_status = self.watchdog.get_status()
            if budget_status.can_early_exit:
                step.status = StepStatus.COMPLETED
                step.result_summary = "Bypassed remaining exploratory steps: evidence converged."
                early_exited = True
                early_exit_reason = budget_status.early_exit_reason
                break

            # 3. Cycle and loop prevention
            should_terminate, cycle_reason = self.cycle_detector.should_terminate(
                action_type=step.action_type,
                tool_args=step.tool_args,
            )
            if should_terminate:
                step.status = StepStatus.COMPLETED
                step.result_summary = f"Skipped: {cycle_reason}"
                skipped_cycle_steps += 1
                continue

            # Record action in cycle detector and watchdog
            self.cycle_detector.record_action(
                step_id=step.step_id,
                action_type=step.action_type,
                tool_args=step.tool_args,
                timestamp=time.perf_counter(),
            )
            self.watchdog.record_step(step.action_type)

            # Execute the step
            step.status = StepStatus.IN_PROGRESS
            try:
                res = step_executor(step, self.watchdog)
                step.status = StepStatus.VERIFIED if res.get("verified") else StepStatus.COMPLETED
                completed_steps += 1
            except Exception as e:
                logger.error("Error executing step %d (%s): %s", step.step_id, step.action_type, e)
                step.status = StepStatus.FAILED
                step.error = str(e)

        # 4. Final Synthesis Step
        synthesis_res = synthesis_handler(plan, self.watchdog)

        # 5. Check if Refinement Loop is required
        refinement_res: Optional[RefinementResult] = None
        if not synthesis_res.get("validation_passed") and synthesis_res.get("packet"):
            logger.info("Validation failure detected. Engaging RefinementLoopController.")
            packet: EvidencePacket = synthesis_res["packet"]
            initial_answer: str = synthesis_res.get("answer", "")
            initial_errors: List[str] = synthesis_res.get("validation_errors", [])
            calcs: List[Dict[str, Any]] = synthesis_res.get("verified_calculations", [])

            role = (
                PersonaRole.SYSTEM_INTROSPECTION
                if plan.complexity == TaskComplexity.SYSTEM_INTROSPECTION
                else (
                    PersonaRole.ADMINISTRATIVE_REASONING
                    if plan.complexity == TaskComplexity.QUANTITATIVE_COMPUTATION
                    else PersonaRole.GOVERNED_RAG
                )
            )

            refinement_res = self.refinement_controller.run_refinement_loop(
                initial_answer=initial_answer,
                initial_passed=False,
                initial_errors=initial_errors,
                query=plan.query,
                packet=packet,
                verified_calculations=calcs,
                budget_watchdog=self.watchdog,
                role=role,
            )

            # Apply refined answer and updated validation status
            synthesis_res["answer"] = refinement_res.final_answer
            synthesis_res["validation_passed"] = refinement_res.validation_passed
            synthesis_res["validation_errors"] = refinement_res.remaining_errors
            synthesis_res["was_refined"] = refinement_res.was_refined
            if refinement_res.fell_back_to_abstention:
                synthesis_res["is_no_answer"] = True

        trace = LoopExecutionTrace(
            steps_attempted=len(action_steps),
            steps_completed=completed_steps,
            steps_skipped_cycle=skipped_cycle_steps,
            early_exited=early_exited,
            early_exit_reason=early_exit_reason,
            elapsed_seconds=round(time.perf_counter() - start_time, 2),
            total_tokens=self.watchdog.total_tokens,
            refinement_result=refinement_res,
        )

        return synthesis_res, trace
