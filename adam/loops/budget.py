"""Execution Budget and Convergence Watchdog for ADAM.

Enforces multi-dimensional resource controls (wall-clock latency, token usage,
tool invocation counts, refinement passes) and evaluates early-exit convergence
heuristics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class BudgetStatus:
    """Snapshot of current resource expenditure against allocated quotas."""
    elapsed_seconds: float
    max_runtime_seconds: float
    time_remaining_seconds: float
    is_time_exhausted: bool
    is_soft_deadline_reached: bool
    total_tokens_consumed: int
    max_total_tokens: int
    is_token_budget_exhausted: bool
    retrievals_used: int
    max_retrievals: int
    computations_used: int
    max_computations: int
    web_calls_used: int
    max_web_calls: int
    refinements_used: int
    max_refinements: int
    can_early_exit: bool
    early_exit_reason: Optional[str] = None


class ExecutionBudgetWatchdog:
    """Monitors real-time consumption of computational budgets and detects convergence."""

    def __init__(
        self,
        max_runtime_seconds: float = 25.0,
        max_total_tokens: int = 8192,
        max_steps: int = 6,
        max_retrievals: int = 3,
        max_computations: int = 2,
        max_web_calls: int = 3,
        max_subagents: int = 2,
        max_refinements: int = 2,
        soft_deadline_ratio: float = 0.80,
    ):
        self.max_runtime_seconds = max_runtime_seconds
        self.max_total_tokens = max_total_tokens
        self.max_steps = max_steps
        self.max_retrievals = max_retrievals
        self.max_computations = max_computations
        self.max_web_calls = max_web_calls
        self.max_subagents = max_subagents
        self.max_refinements = max_refinements
        self.soft_deadline_ratio = soft_deadline_ratio

        self.start_time: float = time.perf_counter()
        self.tokens_prompt: int = 0
        self.tokens_completion: int = 0
        self.steps_executed: int = 0
        self.retrievals_count: int = 0
        self.computations_count: int = 0
        self.web_calls_count: int = 0
        self.subagents_count: int = 0
        self.refinements_count: int = 0

        self.confidence_score: float = 0.0
        self.is_sufficient: bool = False
        self.convergence_achieved: bool = False

    def record_step(self, action_type: str) -> None:
        """Increment count for an action type."""
        self.steps_executed += 1
        if action_type == "search":
            self.retrievals_count += 1
        elif action_type in ("compute", "sandbox"):
            self.computations_count += 1
        elif action_type in ("web_search", "fetch_web_page", "web_research"):
            self.web_calls_count += 1
        elif action_type == "subagent":
            self.subagents_count += 1

    def record_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Update cumulative token counter."""
        self.tokens_prompt += prompt_tokens
        self.tokens_completion += completion_tokens

    def record_refinement(self) -> None:
        """Record a self-correction / refinement pass."""
        self.refinements_count += 1

    def update_convergence(self, is_sufficient: bool, confidence: float) -> None:
        """Update convergence status based on gathered evidence sufficiency."""
        self.is_sufficient = is_sufficient
        self.confidence_score = max(self.confidence_score, confidence)
        if is_sufficient and confidence >= 0.85:
            self.convergence_achieved = True

    @property
    def total_tokens(self) -> int:
        return self.tokens_prompt + self.tokens_completion

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.start_time

    def get_status(self) -> BudgetStatus:
        """Evaluate real-time budget status."""
        elapsed = self.elapsed_seconds
        remaining = max(0.0, self.max_runtime_seconds - elapsed)
        is_time_exhausted = elapsed >= self.max_runtime_seconds
        is_soft_deadline = elapsed >= (self.max_runtime_seconds * self.soft_deadline_ratio)
        is_token_exhausted = self.total_tokens >= self.max_total_tokens

        can_early_exit = self.convergence_achieved or (
            self.is_sufficient and self.confidence_score >= 0.80
        )
        early_exit_reason = None
        if can_early_exit:
            early_exit_reason = f"Evidence converged with confidence {self.confidence_score:.2f}."

        return BudgetStatus(
            elapsed_seconds=round(elapsed, 2),
            max_runtime_seconds=self.max_runtime_seconds,
            time_remaining_seconds=round(remaining, 2),
            is_time_exhausted=is_time_exhausted,
            is_soft_deadline_reached=is_soft_deadline,
            total_tokens_consumed=self.total_tokens,
            max_total_tokens=self.max_total_tokens,
            is_token_budget_exhausted=is_token_exhausted,
            retrievals_used=self.retrievals_count,
            max_retrievals=self.max_retrievals,
            computations_used=self.computations_count,
            max_computations=self.max_computations,
            web_calls_used=self.web_calls_count,
            max_web_calls=self.max_web_calls,
            refinements_used=self.refinements_count,
            max_refinements=self.max_refinements,
            can_early_exit=can_early_exit,
            early_exit_reason=early_exit_reason,
        )

    def is_action_allowed(self, action_type: str) -> Tuple[bool, Optional[str]]:
        """Check if an action is permitted under current budget constraints."""
        status = self.get_status()
        if status.is_time_exhausted:
            return False, f"Wall-clock deadline reached ({status.elapsed_seconds}s >= {self.max_runtime_seconds}s)"
        if status.is_token_budget_exhausted:
            return False, f"Token ceiling reached ({self.total_tokens} >= {self.max_total_tokens})"
        if self.steps_executed >= self.max_steps:
            return False, f"Maximum steps quota reached ({self.steps_executed} >= {self.max_steps})"

        if action_type == "search" and self.retrievals_count >= self.max_retrievals:
            return False, f"Retrieval budget exhausted ({self.retrievals_count} >= {self.max_retrievals})"
        if action_type in ("compute", "sandbox") and self.computations_count >= self.max_computations:
            return False, f"Computation budget exhausted ({self.computations_count} >= {self.max_computations})"
        if action_type in ("web_search", "fetch_web_page", "web_research") and self.web_calls_count >= self.max_web_calls:
            return False, f"Web research budget exhausted ({self.web_calls_count} >= {self.max_web_calls})"
        if action_type == "subagent" and self.subagents_count >= self.max_subagents:
            return False, f"Subagent invocation budget exhausted ({self.subagents_count} >= {self.max_subagents})"

        return True, None

    def is_refinement_allowed(self) -> Tuple[bool, Optional[str]]:
        """Check if another refinement pass can be executed."""
        if self.refinements_count >= self.max_refinements:
            return False, f"Max refinement passes reached ({self.refinements_count} >= {self.max_refinements})"
        status = self.get_status()
        if status.is_soft_deadline_reached:
            return False, "Soft latency deadline reached; bypassing further refinements"
        if status.is_token_budget_exhausted:
            return False, "Token budget exhausted; bypassing further refinements"
        return True, None
