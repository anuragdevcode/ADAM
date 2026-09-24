"""XML Boundary Delimiters and Prompt Defense Sanitizers for ADAM.

Enforces strict isolation between system instructions, governance policies,
approved repository evidence, untrusted user inputs, and critique loops to
prevent indirect prompt injection attacks from malicious PDF documents or
adversarial queries.
"""

from __future__ import annotations

import html
import re
from typing import Optional


class PromptDelimiters:
    """Standard XML tag delimiters for structured prompt construction."""

    # Top-level container tags
    SYSTEM_INSTRUCTIONS_OPEN = "<system_instructions>"
    SYSTEM_INSTRUCTIONS_CLOSE = "</system_instructions>"

    GOVERNANCE_RULES_OPEN = "<governance_rules>"
    GOVERNANCE_RULES_CLOSE = "</governance_rules>"

    APPROVED_EVIDENCE_OPEN = "<approved_evidence>"
    APPROVED_EVIDENCE_CLOSE = "</approved_evidence>"

    EXTERNAL_FINDINGS_OPEN = "<external_findings>"
    EXTERNAL_FINDINGS_CLOSE = "</external_findings>"

    VERIFIED_CALCULATIONS_OPEN = "<verified_calculations>"
    VERIFIED_CALCULATIONS_CLOSE = "</verified_calculations>"

    PRECECDENT_NOTICE_OPEN = "<precedent_notice>"
    PRECECDENT_NOTICE_CLOSE = "</precedent_notice>"

    FEW_SHOT_EXAMPLES_OPEN = "<few_shot_examples>"
    FEW_SHOT_EXAMPLES_CLOSE = "</few_shot_examples>"

    USER_QUERY_OPEN = "<user_query>"
    USER_QUERY_CLOSE = "</user_query>"

    CRITIQUE_FEEDBACK_OPEN = "<critique_feedback>"
    CRITIQUE_FEEDBACK_CLOSE = "</critique_feedback>"

    OUTPUT_FORMAT_OPEN = "<output_format_instructions>"
    OUTPUT_FORMAT_CLOSE = "</output_format_instructions>"


class PromptSanitizer:
    """Sanitizes untrusted text (PDF chunks, user queries, external web pages)

    to prevent breakout of XML tags and model instruction hijacking.
    """

    # Delimiters that must never appear unescaped in untrusted inputs
    RESERVED_TAGS = [
        "system_instructions",
        "governance_rules",
        "approved_evidence",
        "external_findings",
        "verified_calculations",
        "precedent_notice",
        "few_shot_examples",
        "user_query",
        "critique_feedback",
        "output_format_instructions",
        "system",
        "prompt",
        "instruction",
    ]

    # Model-specific special tokens that could hijack the tokenizer
    SPECIAL_TOKENS_PATTERN = re.compile(
        r"(?:<\|im_start\|>|<\|im_end\|>|<\|eot_id\|>|<\|start_header_id\|>|<\|end_header_id\|>|"
        r"\[INST\]|\[\/INST\]|<s>|<\/s>|<end_of_turn>|<start_of_turn>)",
        re.IGNORECASE,
    )

    # Prompt injection / instruction override patterns common in adversarial inputs
    INJECTION_OVERRIDE_PATTERN = re.compile(
        r"(?:ignore\s+(?:all\s+)?(?:previous|above|system)\s+instructions|"
        r"disregard\s+(?:all\s+)?(?:prior|previous)\s+rules|"
        r"you\s+are\s+now\s+in\s+developer\s+mode|"
        r"jailbreak|override\s+system\s+prompt|"
        r"reveal\s+(?:the\s+)?system\s+prompt|"
        r"print\s+system\s+instructions|"
        r"system\s*:\s*you\s+are)",
        re.IGNORECASE,
    )

    @classmethod
    def sanitize(
        cls,
        text: Optional[str],
        escape_xml_tags: bool = True,
        neutralize_overrides: bool = True,
    ) -> str:
        """Sanitizes untrusted text before injecting it into any prompt context."""
        if not text:
            return ""

        clean = str(text)

        # 1. Strip special model tokens
        clean = cls.SPECIAL_TOKENS_PATTERN.sub("[REDACTED_SPECIAL_TOKEN]", clean)

        # 2. Escape reserved XML boundary tags to prevent container breakout
        if escape_xml_tags:
            for tag in cls.RESERVED_TAGS:
                clean = re.sub(
                    rf"<\s*/?\s*{tag}\b[^>]*>",
                    f"[ESCAPED_TAG:{tag}]",
                    clean,
                    flags=re.IGNORECASE,
                )

        # 3. Neutralize direct instruction overrides in untrusted text
        if neutralize_overrides:
            clean = cls.INJECTION_OVERRIDE_PATTERN.sub(
                "[SUSPICIOUS_OVERRIDE_ATTEMPT_NEUTRALIZED]",
                clean,
            )

        return clean.strip()

    @classmethod
    def wrap_tag(cls, tag_name: str, content: str, attributes: Optional[str] = None) -> str:
        """Wraps content within safe XML tags."""
        attr_str = f" {attributes}" if attributes else ""
        return f"<{tag_name}{attr_str}>\n{content}\n</{tag_name}>"
