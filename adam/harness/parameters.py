"""Inference parameter abstraction for model-specific harnesses.

Provides dataclasses for configuring generation parameters across different model
families (Qwen, Llama, Gemma, Gemini) and task intents (governed RAG vs conversational).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelInferenceParameters:
    """Resolved model execution parameters.

    Attributes:
        temperature: Sampling temperature. Governed RAG keeps this low (e.g. 0.0-0.2)
            while reasoning/conversational tasks benefit from moderate variance (0.5-0.7).
        top_p: Nucleus sampling probability threshold (default 0.9).
        top_k: Top-k filtering limit (default 40).
        min_p: Minimum probability threshold relative to the most likely token (default 0.05).
        max_tokens: Maximum completion tokens (default 1024; expandable for reasoning models).
        context_size: Target context window in tokens (e.g. 4096 or 8192).
        thinking_enabled: Whether to permit internal thinking/scratchpad generation (<think>...</think>).
        thinking_budget: Reserved token headroom when thinking is enabled (default 1024).
        stop_sequences: Stop tokens preventing run-on completions.
        custom_options: Arbitrary backend options passed directly to the runtime.
    """

    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 40
    min_p: float = 0.05
    max_tokens: int = 1024
    context_size: int = 4096
    thinking_enabled: bool = False
    thinking_budget: int = 1024
    stop_sequences: List[str] = field(default_factory=lambda: ["<|im_end|>", "<|endoftext|>"])
    custom_options: Dict[str, Any] = field(default_factory=dict)

    def to_ollama_options(self) -> Dict[str, Any]:
        """Convert parameters to Ollama /api/chat 'options' payload."""
        total_predict = self.max_tokens
        if self.thinking_enabled:
            total_predict += self.thinking_budget

        options: Dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "num_predict": total_predict,
            "num_ctx": self.context_size,
        }
        if self.min_p > 0.0:
            options["min_p"] = self.min_p
        if self.stop_sequences:
            options["stop"] = list(self.stop_sequences)

        options.update(self.custom_options)
        return options

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "min_p": self.min_p,
            "max_tokens": self.max_tokens,
            "context_size": self.context_size,
            "thinking_enabled": self.thinking_enabled,
            "thinking_budget": self.thinking_budget,
            "stop_sequences": self.stop_sequences,
            "custom_options": self.custom_options,
        }
