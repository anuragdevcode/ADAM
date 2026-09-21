"""Router mapping model identifiers and tags to their optimal HarnessProfile."""

from __future__ import annotations

from typing import Optional, Dict

from adam.harness.profiles import (
    BaseHarnessProfile,
    QwenHarnessProfile,
    LlamaHarnessProfile,
    GemmaHarnessProfile,
    GeminiHarnessProfile,
    DefaultHarnessProfile,
)


class HarnessRouter:
    """Resolves model artifacts, IDs, and tags to specialized harness profiles."""

    _cached_profiles: Dict[str, BaseHarnessProfile] = {}

    @classmethod
    def resolve_profile(cls, model_id_or_tag: Optional[str] = None) -> BaseHarnessProfile:
        """Resolve a model identifier or tag to its matching harness profile.

        Args:
            model_id_or_tag: String identifier like 'qwen2.5-3b-instruct-q4', 'qwen3:4b',
                'llama-3.2-3b-instruct-q4', 'gemini-3.6-flash', etc.

        Returns:
            The matching BaseHarnessProfile instance.
        """
        if not model_id_or_tag:
            return DefaultHarnessProfile()

        raw = model_id_or_tag.strip().lower()
        if raw in cls._cached_profiles:
            return cls._cached_profiles[raw]

        profile: BaseHarnessProfile
        if "gemini" in raw:
            profile = GeminiHarnessProfile()
        elif "qwen3" in raw or "deepseek-r1" in raw or "qwq" in raw:
            # Reasoning variants that emit thinking tokens
            profile = QwenHarnessProfile(is_reasoning_variant=True)
        elif "qwen" in raw:
            # Standard Qwen variants (e.g. Qwen2.5)
            profile = QwenHarnessProfile(is_reasoning_variant=False)
        elif "llama" in raw:
            profile = LlamaHarnessProfile()
        elif "gemma" in raw:
            profile = GemmaHarnessProfile()
        else:
            profile = DefaultHarnessProfile()

        cls._cached_profiles[raw] = profile
        return profile
