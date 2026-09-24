"""Critique and Self-Correction Prompt Templates for ADAM.

Enables iterative refinement loops by providing targeted, objective critique
feedback generated from automated validation failures (e.g., CitationValidator,
arithmetic verification, and supersession alerts).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from adam.prompts.delimiters import PromptDelimiters, PromptSanitizer


class CritiquePromptFactory:
    """Generates structured critique instructions for self-correction passes."""

    @classmethod
    def build_citation_critique(
        cls,
        draft_answer: str,
        validation_errors: List[str],
        evidence_summary: Optional[str] = None,
    ) -> str:
        """Construct critique feedback when CitationValidator finds ungrounded material claims."""
        clean_draft = PromptSanitizer.sanitize(draft_answer)
        clean_errors = [PromptSanitizer.sanitize(err) for err in validation_errors]

        critique_body = (
            "CRITIQUE NOTICE — UNGROUNDED MATERIAL CLAIMS DETECTED:\n"
            "The previous draft contained statements that violated the zero-hallucination policy.\n"
            "The following material claims could NOT be verified in the retrieved evidence passages:\n"
        )
        for err in clean_errors:
            critique_body += f"- {err}\n"

        critique_body += (
            "\nMandatory Revision Instructions:\n"
            "1. Remove or correct every ungrounded claim listed above.\n"
            "2. Do NOT invent dates, numbers, or rules from model memory.\n"
            "3. If the retrieved evidence does not explicitly support a claim, either omit it or state clearly: "
            "'I could not establish this from the approved repository.'\n"
            "4. Ensure all retained facts cite the correct passage numbers [1], [2].\n"
            "5. Provide the revised, fully verified response now."
        )

        wrapped_critique = PromptDelimiters.CRITIQUE_FEEDBACK_OPEN + "\n" + critique_body + "\n" + PromptDelimiters.CRITIQUE_FEEDBACK_CLOSE
        return (
            f"Previous Draft:\n{clean_draft}\n\n"
            f"{wrapped_critique}"
        )

    @classmethod
    def build_arithmetic_critique(
        cls,
        draft_answer: str,
        sandbox_outputs: List[Dict[str, Any]],
    ) -> str:
        """Construct critique feedback when text arithmetic contradicts sandbox proofs."""
        clean_draft = PromptSanitizer.sanitize(draft_answer)
        critique_body = (
            "CRITIQUE NOTICE — ARITHMETIC DISCREPANCY DETECTED:\n"
            "The figures stated in the draft contradicted the deterministic mathematical outputs from the secure sandbox.\n"
            "Deterministic Sandbox Ground Truth:\n"
        )
        for out in sandbox_outputs:
            critique_body += f"- Verified Output: {out.get('formatted') or out.get('value')} (Stdout: {out.get('output', '').strip()})\n"

        critique_body += (
            "\nMandatory Revision Instructions:\n"
            "1. Correct all numbers, percentages, and totals in the text to strictly match the sandbox outputs above.\n"
            "2. Show the exact step-by-step formula.\n"
            "3. Provide the revised, arithmetically consistent response now."
        )

        wrapped_critique = PromptDelimiters.CRITIQUE_FEEDBACK_OPEN + "\n" + critique_body + "\n" + PromptDelimiters.CRITIQUE_FEEDBACK_CLOSE
        return (
            f"Previous Draft:\n{clean_draft}\n\n"
            f"{wrapped_critique}"
        )

    @classmethod
    def build_supersession_critique(
        cls,
        draft_answer: str,
        superseding_go_number: str,
        superseding_date: str,
        currency_banner: str,
    ) -> str:
        """Construct critique when a draft failed to display a required currency warning."""
        clean_draft = PromptSanitizer.sanitize(draft_answer)
        critique_body = (
            "CRITIQUE NOTICE — MISSING CURRENCY BANNER:\n"
            f"The draft relied on an order that has been superseded.\n"
            f"Superseding Order: {superseding_go_number} dated {superseding_date}.\n"
            f"Mandatory Banner: {currency_banner}\n\n"
            "Mandatory Revision Instructions:\n"
            "1. Insert the Currency Notice prominently at the very top of your response.\n"
            "2. Clearly distinguish between the historical superseded rule and the current valid rule.\n"
            "3. Provide the revised response now."
        )

        wrapped_critique = PromptDelimiters.CRITIQUE_FEEDBACK_OPEN + "\n" + critique_body + "\n" + PromptDelimiters.CRITIQUE_FEEDBACK_CLOSE
        return (
            f"Previous Draft:\n{clean_draft}\n\n"
            f"{wrapped_critique}"
        )
