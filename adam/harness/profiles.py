"""Model family harness profiles.

Each profile encapsulates the optimal configuration for interacting with a specific
model architecture (Qwen, Llama, Gemma, Gemini) under governed ADAM constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from adam.harness.parameters import ModelInferenceParameters
from adam.harness.templates import PromptTemplateRegistry
from adam.harness.context import ContextStrategy
from adam.rag.models import EvidencePacket


class BaseHarnessProfile(ABC):
    """Abstract base profile for model interaction."""

    family_name: str = "generic"

    @abstractmethod
    def resolve_parameters(self, intent: str = "rag", **overrides: Any) -> ModelInferenceParameters:
        """Resolve model-appropriate inference parameters for the given task intent."""

    @abstractmethod
    def format_rag_prompt(self, query: str, packet: EvidencePacket) -> str:
        """Format a grounded RAG prompt suited to this model's attention capacity."""

    @abstractmethod
    def format_conversational_prompt(self, query: str) -> str:
        """Format a conversational turn prompt without contradictory directives."""

    def format_introspection_prompt(self, query: str, snapshot_context: str) -> str:
        """Format an authoritative introspection prompt suited to this model."""
        return PromptTemplateRegistry.format_introspection_turn(query, snapshot_context)

    @abstractmethod
    def resolve_system_prompt(self, intent: str = "rag") -> str:
        """Resolve system prompt aligned with intent."""


class QwenHarnessProfile(BaseHarnessProfile):
    """Harness profile tailored for Alibaba Cloud Qwen (Qwen2.5 and Qwen3 series).

    Characteristics:
    - ChatML prompt format.
    - Qwen3 supports internal reasoning via <think> tokens when enabled.
    - Benefits from nucleus sampling (top_p=0.9, top_k=40, min_p=0.05).
    - Avoids prompt stop collision (removes rigid `\\n\\nQuestion:` stop token).
    - Compact evidence formatting preventing prompt inundation.
    """

    family_name = "qwen"

    def __init__(self, is_reasoning_variant: bool = False):
        self.is_reasoning_variant = is_reasoning_variant

    def resolve_parameters(self, intent: str = "rag", **overrides: Any) -> ModelInferenceParameters:
        # For governed RAG: low temperature (0.2) to maintain strict grounding
        if intent in ("conversational", "coding", "general"):
            temp = overrides.get("temperature", 0.6)
            max_tokens = overrides.get("max_tokens", 1536)
        elif intent in ("reasoning", "multi_step"):
            temp = overrides.get("temperature", 0.4)
            max_tokens = overrides.get("max_tokens", 2048)
        elif intent == "introspection":
            temp = overrides.get("temperature", 0.1)
            max_tokens = overrides.get("max_tokens", 1024)
        else:  # "rag", "unanswerable", "citation", "administrative"
            temp = overrides.get("temperature", 0.2)
            max_tokens = overrides.get("max_tokens", 1024)

        thinking_enabled = self.is_reasoning_variant and overrides.get("thinking_enabled", True)

        params = ModelInferenceParameters(
            temperature=temp,
            top_p=overrides.get("top_p", 0.9),
            top_k=overrides.get("top_k", 40),
            min_p=overrides.get("min_p", 0.05),
            max_tokens=max_tokens,
            context_size=overrides.get("context_size", 8192),
            thinking_enabled=thinking_enabled,
            thinking_budget=overrides.get("thinking_budget", 1024 if thinking_enabled else 0),
            stop_sequences=overrides.get("stop_sequences", ["<|im_end|>", "<|endoftext|>"]),
        )
        return params

    def format_rag_prompt(self, query: str, packet: EvidencePacket) -> str:
        return ContextStrategy.build_grounded_rag_prompt(query, packet, max_passages=4)

    def format_conversational_prompt(self, query: str) -> str:
        return PromptTemplateRegistry.format_conversational_turn(query, model_mention="ADAM (Qwen)")

    def resolve_system_prompt(self, intent: str = "rag") -> str:
        return PromptTemplateRegistry.resolve_system_prompt(intent)


class LlamaHarnessProfile(BaseHarnessProfile):
    """Harness profile for Meta Llama 3.x series."""

    family_name = "llama"

    def resolve_parameters(self, intent: str = "rag", **overrides: Any) -> ModelInferenceParameters:
        temp = 0.2 if intent == "rag" else 0.5
        temp = overrides.get("temperature", temp)
        return ModelInferenceParameters(
            temperature=temp,
            top_p=overrides.get("top_p", 0.9),
            top_k=overrides.get("top_k", 40),
            min_p=0.0,
            max_tokens=overrides.get("max_tokens", 1024),
            context_size=overrides.get("context_size", 8192),
            thinking_enabled=False,
            stop_sequences=overrides.get("stop_sequences", ["<|eot_id|>", "<|end_of_text|>"]),
        )

    def format_rag_prompt(self, query: str, packet: EvidencePacket) -> str:
        return ContextStrategy.build_grounded_rag_prompt(query, packet, max_passages=4)

    def format_conversational_prompt(self, query: str) -> str:
        return PromptTemplateRegistry.format_conversational_turn(query, model_mention="ADAM (Llama)")

    def resolve_system_prompt(self, intent: str = "rag") -> str:
        return PromptTemplateRegistry.resolve_system_prompt(intent)


class GemmaHarnessProfile(BaseHarnessProfile):
    """Harness profile for Google Gemma 3 series."""

    family_name = "gemma"

    def resolve_parameters(self, intent: str = "rag", **overrides: Any) -> ModelInferenceParameters:
        temp = 0.2 if intent == "rag" else 0.4
        temp = overrides.get("temperature", temp)
        return ModelInferenceParameters(
            temperature=temp,
            top_p=overrides.get("top_p", 0.9),
            top_k=overrides.get("top_k", 40),
            min_p=0.0,
            max_tokens=overrides.get("max_tokens", 1024),
            context_size=overrides.get("context_size", 4096),
            thinking_enabled=False,
            stop_sequences=overrides.get("stop_sequences", ["<end_of_turn>"]),
        )

    def format_rag_prompt(self, query: str, packet: EvidencePacket) -> str:
        return ContextStrategy.build_grounded_rag_prompt(query, packet, max_passages=4)

    def format_conversational_prompt(self, query: str) -> str:
        return PromptTemplateRegistry.format_conversational_turn(query, model_mention="ADAM (Gemma)")

    def resolve_system_prompt(self, intent: str = "rag") -> str:
        return PromptTemplateRegistry.resolve_system_prompt(intent)


class GeminiHarnessProfile(BaseHarnessProfile):
    """Harness profile for Google Gemini cloud models."""

    family_name = "gemini"

    def resolve_parameters(self, intent: str = "rag", **overrides: Any) -> ModelInferenceParameters:
        temp = 0.15 if intent == "rag" else 0.2
        temp = overrides.get("temperature", temp)
        return ModelInferenceParameters(
            temperature=temp,
            top_p=overrides.get("top_p", 0.95),
            top_k=overrides.get("top_k", 40),
            min_p=0.0,
            max_tokens=overrides.get("max_tokens", 2048),
            context_size=overrides.get("context_size", 32768),
            thinking_enabled=False,
            stop_sequences=overrides.get("stop_sequences", ["\n\nUser:"]),
        )

    def format_rag_prompt(self, query: str, packet: EvidencePacket) -> str:
        return ContextStrategy.build_grounded_rag_prompt(query, packet, max_passages=6)

    def format_conversational_prompt(self, query: str) -> str:
        return PromptTemplateRegistry.format_conversational_turn(query, model_mention="ADAM (Gemini)")

    def resolve_system_prompt(self, intent: str = "rag") -> str:
        return PromptTemplateRegistry.resolve_system_prompt(intent)


class DefaultHarnessProfile(BaseHarnessProfile):
    """Safe universal fallback harness profile."""

    family_name = "default"

    def resolve_parameters(self, intent: str = "rag", **overrides: Any) -> ModelInferenceParameters:
        temp = 0.2 if intent == "rag" else 0.5
        temp = overrides.get("temperature", temp)
        return ModelInferenceParameters(
            temperature=temp,
            top_p=overrides.get("top_p", 0.9),
            top_k=overrides.get("top_k", 40),
            min_p=0.0,
            max_tokens=overrides.get("max_tokens", 1024),
            context_size=overrides.get("context_size", 4096),
            thinking_enabled=False,
            stop_sequences=overrides.get("stop_sequences", ["<|im_end|>", "<|endoftext|>"]),
        )

    def format_rag_prompt(self, query: str, packet: EvidencePacket) -> str:
        return ContextStrategy.build_grounded_rag_prompt(query, packet, max_passages=4)

    def format_conversational_prompt(self, query: str) -> str:
        return PromptTemplateRegistry.format_conversational_turn(query, model_mention="ADAM")

    def resolve_system_prompt(self, intent: str = "rag") -> str:
        return PromptTemplateRegistry.resolve_system_prompt(intent)
