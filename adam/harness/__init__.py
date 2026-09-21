"""Model-Specific Harness Architecture for ADAM.

Enables each model family (Qwen, Llama, Gemma, Gemini) to operate under its optimal
inference configuration, evidence presentation format, and sampling parameters,
while strictly preserving ADAM governance, citation verification, and air-gapped guarantees.
"""

from adam.harness.parameters import ModelInferenceParameters
from adam.harness.profiles import (
    BaseHarnessProfile,
    QwenHarnessProfile,
    LlamaHarnessProfile,
    GemmaHarnessProfile,
    GeminiHarnessProfile,
    DefaultHarnessProfile,
)
from adam.harness.routing import HarnessRouter
from adam.harness.context import ContextStrategy
from adam.harness.templates import PromptTemplateRegistry
from adam.harness.validators import HarnessOutputValidator
from adam.harness.benchmarks import (
    BenchmarkPrompt,
    PromptEvaluationResult,
    BenchmarkRunner,
    BENCHMARK_SUITE,
)

__all__ = [
    "ModelInferenceParameters",
    "BaseHarnessProfile",
    "QwenHarnessProfile",
    "LlamaHarnessProfile",
    "GemmaHarnessProfile",
    "GeminiHarnessProfile",
    "DefaultHarnessProfile",
    "HarnessRouter",
    "ContextStrategy",
    "PromptTemplateRegistry",
    "HarnessOutputValidator",
    "BenchmarkPrompt",
    "PromptEvaluationResult",
    "BenchmarkRunner",
    "BENCHMARK_SUITE",
]
