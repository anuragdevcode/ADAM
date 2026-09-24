"""Central Prompt Catalog and Registry for ADAM.

Provides versioned, intent-aware access to system prompts, user turn formatting,
and domain-specific prompt assemblies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from adam.prompts.builder import PromptBuilder
from adam.prompts.delimiters import PromptDelimiters, PromptSanitizer
from adam.prompts.few_shot import FewShotCatalog, FewShotExemplar
from adam.prompts.personas import AgentPersona, PersonaRegistry, PersonaRole
from adam.rag.models import EvidencePacket, EvidencePassage


class PromptCatalog:
    """Central registry of prompts for all agent subsystems."""

    VERSION: str = "2.0.0"

    # Direct access to core system prompts
    GOVERNED_RAG_SYSTEM_PROMPT = PersonaRegistry.GOVERNED_RAG.build_system_prompt()
    CONVERSATIONAL_SYSTEM_PROMPT = PersonaRegistry.CONVERSATIONAL_GUIDE.build_system_prompt()
    REASONING_SYSTEM_PROMPT = PersonaRegistry.ADMINISTRATIVE_REASONING.build_system_prompt()
    INTROSPECTION_SYSTEM_PROMPT = PersonaRegistry.SYSTEM_INTROSPECTION.build_system_prompt()
    PRECEDENT_SYSTEM_PROMPT = PersonaRegistry.PRECEDENT_RECONCILIATION.build_system_prompt()
    WEB_RESEARCH_SYSTEM_PROMPT = PersonaRegistry.WEB_RESEARCH_SUBAGENT.build_system_prompt()
    DATA_ANALYSIS_SYSTEM_PROMPT = PersonaRegistry.DATA_ANALYSIS_SUBAGENT.build_system_prompt()

    @classmethod
    def resolve_system_prompt(cls, intent: str = "rag") -> str:
        """Resolve system prompt according to query intent or task type."""
        intent_lower = (intent or "rag").lower().strip()
        if intent_lower in ("conversational", "guidance"):
            return cls.CONVERSATIONAL_SYSTEM_PROMPT
        elif intent_lower in ("reasoning", "multi_step", "quantitative", "calculation"):
            return cls.REASONING_SYSTEM_PROMPT
        elif intent_lower in ("introspection", "system_state"):
            return cls.INTROSPECTION_SYSTEM_PROMPT
        elif intent_lower in ("precedent", "amendment", "supersession"):
            return cls.PRECEDENT_SYSTEM_PROMPT
        elif intent_lower in ("web_research", "external"):
            return cls.WEB_RESEARCH_SYSTEM_PROMPT
        elif intent_lower in ("data_analysis", "sandbox_math"):
            return cls.DATA_ANALYSIS_SYSTEM_PROMPT
        return cls.GOVERNED_RAG_SYSTEM_PROMPT

    @classmethod
    def create_builder(cls, intent: str = "rag") -> PromptBuilder:
        """Initialize a new PromptBuilder configured for the given intent."""
        intent_lower = (intent or "rag").lower().strip()
        if intent_lower in ("conversational", "guidance"):
            return PromptBuilder(PersonaRegistry.CONVERSATIONAL_GUIDE)
        elif intent_lower in ("reasoning", "quantitative", "calculation"):
            return PromptBuilder(PersonaRegistry.ADMINISTRATIVE_REASONING)
        elif intent_lower in ("introspection", "system_state"):
            return PromptBuilder(PersonaRegistry.SYSTEM_INTROSPECTION)
        elif intent_lower in ("precedent", "amendment", "supersession"):
            return PromptBuilder(PersonaRegistry.PRECEDENT_RECONCILIATION)
        return PromptBuilder(PersonaRegistry.GOVERNED_RAG)

    @classmethod
    def format_conversational_turn(cls, query: str, assistant_name: str = "ADAM") -> str:
        """Format a clean conversational user turn with boundary protection."""
        clean_q = PromptSanitizer.sanitize(query)
        builder = (
            cls.create_builder("conversational")
            .with_user_query(clean_q)
            .with_output_instructions(
                f"Respond directly and concisely as {assistant_name}. "
                "Provide an accurate, structured summary without introductory filler or fabricated citations."
            )
        )
        return builder.build_user_prompt()

    @classmethod
    def format_introspection_turn(cls, query: str, snapshot_context: str) -> str:
        """Format an authoritative introspection prompt enclosing system state snapshot."""
        clean_q = PromptSanitizer.sanitize(query)
        builder = (
            cls.create_builder("introspection")
            .with_user_query(clean_q)
            .with_system_state(snapshot_context)
            .with_output_instructions(
                "Use the authoritative system state snapshot above to answer the user's question directly, "
                "accurately, and concisely. Interpret this state objectively. "
                "Do not claim you could not establish this from the approved repository — this system snapshot is your approved ground truth."
            )
        )
        return builder.build_user_prompt()

    @classmethod
    def format_rag_turn(
        cls,
        query: str,
        packet: EvidencePacket,
        verified_calculations: Optional[List[Dict[str, Any]]] = None,
        include_few_shot: bool = False,
    ) -> str:
        """Format a complete RAG user prompt enclosing packet passages and calculation proofs."""
        clean_q = PromptSanitizer.sanitize(query)
        builder = (
            cls.create_builder("rag")
            .with_user_query(clean_q)
            .with_evidence(packet.passages)
            .with_precedent_notice(packet.currency_banner)
        )

        if verified_calculations:
            builder.with_calculations(verified_calculations)

        if include_few_shot:
            if "da" in query.lower() or "महंगाई" in query:
                builder.with_few_shot_category("financial_calculation")
            elif "supersed" in query.lower() or "निरस्त" in query:
                builder.with_few_shot_category("superseded_order")

        return builder.build_user_prompt()
