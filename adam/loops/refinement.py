"""Self-Correction and Iterative Refinement Loop for ADAM.

Orchestrates the Generate -> Validate -> Critique -> Refine cycle to resolve
citation validator errors, arithmetic discrepancies, and ungrounded assertions
with strict termination guarantees (max 2 iterations).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from adam.loops.budget import ExecutionBudgetWatchdog
from adam.model.runtime import BaseModelRuntime, ModelGenerationResult
from adam.prompts.builder import PromptBuilder
from adam.prompts.critique import CritiquePromptFactory
from adam.prompts.personas import PersonaRegistry, PersonaRole
from adam.rag.generator import CitationValidator
from adam.rag.models import EvidencePacket

logger = logging.getLogger(__name__)


@dataclass
class RefinementIteration:
    """Record of an individual refinement attempt."""
    iteration_index: int
    draft_answer: str
    validation_passed: bool
    validation_errors: List[str]
    critique_issued: Optional[str] = None
    tokens_prompt: int = 0
    tokens_completion: int = 0


@dataclass
class RefinementResult:
    """Consolidated outcome of the self-correction refinement loop."""
    final_answer: str
    initial_answer: str
    iterations_count: int
    validation_passed: bool
    remaining_errors: List[str]
    history: List[RefinementIteration] = field(default_factory=list)
    tokens_prompt: int = 0
    tokens_completion: int = 0
    was_refined: bool = False
    fell_back_to_abstention: bool = False


class RefinementLoopController:
    """Executes governed self-correction passes to eliminate hallucinated claims."""

    MAX_REFINEMENTS: int = 2
    FALLBACK_REFUSAL = "I could not establish this from the approved repository."

    def __init__(
        self,
        runtime: BaseModelRuntime,
        max_refinements: int = 2,
    ):
        self.runtime = runtime
        self.max_refinements = min(max_refinements, self.MAX_REFINEMENTS)

    def run_refinement_loop(
        self,
        initial_answer: str,
        initial_passed: bool,
        initial_errors: List[str],
        query: str,
        packet: EvidencePacket,
        verified_calculations: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        budget_watchdog: Optional[ExecutionBudgetWatchdog] = None,
        token_callback: Optional[Callable[[str], None]] = None,
        role: PersonaRole = PersonaRole.GOVERNED_RAG,
    ) -> RefinementResult:
        """Execute iterative critique-driven refinement if initial validation failed."""
        history: List[RefinementIteration] = []
        tot_p_tokens = 0
        tot_c_tokens = 0

        # Record initial turn
        history.append(
            RefinementIteration(
                iteration_index=0,
                draft_answer=initial_answer,
                validation_passed=initial_passed,
                validation_errors=list(initial_errors),
            )
        )

        # Fast path: initial draft passed validation
        if initial_passed:
            return RefinementResult(
                final_answer=initial_answer,
                initial_answer=initial_answer,
                iterations_count=0,
                validation_passed=True,
                remaining_errors=[],
                history=history,
                was_refined=False,
            )

        current_answer = initial_answer
        current_passed = initial_passed
        current_errors = list(initial_errors)

        for iteration in range(1, self.max_refinements + 1):
            # Check budget allowance
            if budget_watchdog:
                allowed, reason = budget_watchdog.is_refinement_allowed()
                if not allowed:
                    logger.warning("Refinement loop halted by budget: %s", reason)
                    break
                budget_watchdog.record_refinement()

            # 1. Build targeted critique
            critique = CritiquePromptFactory.build_citation_critique(
                draft_answer=current_answer,
                validation_errors=current_errors,
            )

            # 2. Build structured refinement prompt
            builder = (
                PromptBuilder()
                .with_role(role)
                .with_user_query(query)
                .with_evidence(packet.passages)
                .with_precedent_notice(packet.currency_banner)
                .with_critique(critique)
            )
            if verified_calculations:
                builder.with_calculations(verified_calculations)

            refinement_user_prompt = builder.build_user_prompt()
            refinement_sys_prompt = system_prompt or builder.build_system_prompt()

            # 3. Model generation pass with low temperature for precision
            gen_res: ModelGenerationResult = self.runtime.generate(
                user_prompt=refinement_user_prompt,
                system_prompt=refinement_sys_prompt,
                temperature=0.1,
                max_tokens=1024,
                token_callback=token_callback,
            )

            tot_p_tokens += gen_res.tokens_prompt
            tot_c_tokens += gen_res.tokens_completion
            if budget_watchdog:
                budget_watchdog.record_tokens(gen_res.tokens_prompt, gen_res.tokens_completion)

            current_answer = gen_res.answer

            # 4. Re-validate revised draft
            current_passed, current_errors = CitationValidator.validate(
                answer=current_answer,
                packet=packet,
                verified_calculations=verified_calculations,
            )

            history.append(
                RefinementIteration(
                    iteration_index=iteration,
                    draft_answer=current_answer,
                    validation_passed=current_passed,
                    validation_errors=list(current_errors),
                    critique_issued=critique,
                    tokens_prompt=gen_res.tokens_prompt,
                    tokens_completion=gen_res.tokens_completion,
                )
            )

            # If validation passed, terminate loop early
            if current_passed:
                logger.info("Refinement loop succeeded at iteration %d", iteration)
                return RefinementResult(
                    final_answer=current_answer,
                    initial_answer=initial_answer,
                    iterations_count=iteration,
                    validation_passed=True,
                    remaining_errors=[],
                    history=history,
                    tokens_prompt=tot_p_tokens,
                    tokens_completion=tot_c_tokens,
                    was_refined=True,
                    fell_back_to_abstention=False,
                )

        # If refinement did not clear all errors, safely abstain rather than emitting hallucinated claims
        logger.warning(
            "Refinement loop exhausted %d iterations with %d remaining errors. Falling back to abstention.",
            len(history) - 1,
            len(current_errors),
        )

        return RefinementResult(
            final_answer=self.FALLBACK_REFUSAL,
            initial_answer=initial_answer,
            iterations_count=len(history) - 1,
            validation_passed=False,
            remaining_errors=current_errors,
            history=history,
            tokens_prompt=tot_p_tokens,
            tokens_completion=tot_c_tokens,
            was_refined=True,
            fell_back_to_abstention=True,
        )
