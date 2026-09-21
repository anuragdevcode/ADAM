"""Prompt templates and role mapping for model-specific harnesses.

Ensures that:
1. System prompt aligns with the query intent (governed RAG vs conversational guidance).
2. Conversational turns do not contradict the system prompt.
3. ChatML / Turn-based role semantics match model expectations.
"""

from __future__ import annotations

from typing import Dict, Any, Optional


class PromptTemplateRegistry:
    """Provides prompt templates tailored by model family and intent."""

    # Governed RAG system prompt: concise, authoritative, grounding-focused
    GOVERNED_RAG_SYSTEM_PROMPT = (
        "You are ADAM, the authorized AI assistant for Uttarakhand State public records and governance. "
        "Your responses must be strictly grounded in the official repository evidence provided in each turn. "
        "Cite the relevant passages using [1], [2] when stating facts, dates, monetary amounts, or rule numbers. "
        "Do not invent facts or extrapolate beyond the provided records. "
        "If the records do not contain conclusive evidence, state clearly that you could not establish this from the approved repository."
    )

    # Conversational / General guidance system prompt: helpful, clear, non-contradictory
    CONVERSATIONAL_SYSTEM_PROMPT = (
        "You are ADAM, the authorized AI assistant for Uttarakhand State public records and governance. "
        "You provide helpful, concise, and professional assistance regarding Uttarakhand administrative procedures, "
        "Government Orders (GOs), service rules, and public documents. "
        "Be natural, accurate, and transparent about your identity. Do not fabricate government order numbers or citations."
    )

    # Reasoning / Multi-step system prompt
    REASONING_SYSTEM_PROMPT = (
        "You are an expert administrative reasoning and analysis engine for Uttarakhand governance records. "
        "Break down complex multi-part questions step-by-step. State assumptions clearly, verify arithmetic, "
        "and present conclusions with rigorous justification."
    )

    @classmethod
    def resolve_system_prompt(cls, intent: str = "rag") -> str:
        """Resolve system prompt according to query intent."""
        if intent == "conversational":
            return cls.CONVERSATIONAL_SYSTEM_PROMPT
        elif intent == "reasoning":
            return cls.REASONING_SYSTEM_PROMPT
        return cls.GOVERNED_RAG_SYSTEM_PROMPT

    @classmethod
    def format_conversational_turn(cls, query: str, model_mention: str = "ADAM") -> str:
        """Format clean conversational user turn without contradictory instruction blocks."""
        return (
            f"{query}\n\n"
            f"[Context: No specific repository document was referenced for this turn. "
            f"Respond clearly and concisely as {model_mention}. For administrative queries, "
            f"guide the user on how to locate the relevant Uttarakhand Government Order.]"
        )
