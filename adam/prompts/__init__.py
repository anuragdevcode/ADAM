"""ADAM Structured Prompt Engineering Framework.

Provides composable personas, XML boundary delimiters, few-shot administrative
exemplars, critique/self-correction templates, and a centralized prompt catalog.
"""

from adam.prompts.delimiters import PromptDelimiters, PromptSanitizer
from adam.prompts.personas import AgentPersona, PersonaRegistry, PersonaRole
from adam.prompts.few_shot import FewShotCatalog, FewShotExemplar
from adam.prompts.critique import CritiquePromptFactory
from adam.prompts.builder import PromptBuilder
from adam.prompts.registry import PromptCatalog

__all__ = [
    "PromptDelimiters",
    "PromptSanitizer",
    "AgentPersona",
    "PersonaRegistry",
    "PersonaRole",
    "FewShotCatalog",
    "FewShotExemplar",
    "CritiquePromptFactory",
    "PromptBuilder",
    "PromptCatalog",
]
