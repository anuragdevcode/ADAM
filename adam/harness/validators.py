"""Deterministic host-side validators for model outputs.

Shifts verification responsibility from the model to deterministic Python logic:
- Citation index verification against retrieved passages
- Parsing and segregation of internal <think>...</think> reasoning traces
- JSON output validation
- Length and boundary sanity checks
"""

from __future__ import annotations

import json
import re
from typing import List, Tuple, Optional, Dict, Any


class HarnessOutputValidator:
    """Performs deterministic verification on raw generation outputs."""

    # Matches citations of form [1], [2], [1, 2], [1]-[3]
    CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
    THINK_BLOCK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)

    @classmethod
    def separate_thinking_tokens(cls, raw_text: str) -> Tuple[str, Optional[str]]:
        """Separate internal thinking scratchpad from final answer.

        Returns:
            Tuple of (clean_answer, thinking_trace)
        """
        if not raw_text:
            return "", None

        text = raw_text.strip()
        thinking_parts: List[str] = []

        # 1. Match complete <think>...</think> blocks
        matches = cls.THINK_BLOCK_PATTERN.findall(text)
        if matches:
            thinking_parts.extend(m.strip() for m in matches if m.strip())
            text = cls.THINK_BLOCK_PATTERN.sub("", text).strip()

        # 2. Handle dangling closing tag </think> (model started in thinking mode)
        if "</think>" in text:
            before, after = text.rsplit("</think>", 1)
            clean_before = before.replace("<think>", "").strip()
            if clean_before:
                thinking_parts.append(clean_before)
            text = after.strip()

        # 3. Handle unclosed opening tag <think> (model output was truncated while thinking)
        if "<think>" in text:
            before, after = text.split("<think>", 1)
            if after.strip():
                thinking_parts.append(after.strip())
            text = before.strip()

        thinking_trace = "\n\n".join(thinking_parts) if thinking_parts else None
        return text, thinking_trace

    @classmethod
    def validate_citation_indices(
        cls,
        answer: str,
        num_passages: int,
    ) -> Tuple[bool, List[int], List[int]]:
        """Verify that all numerical citations in the answer point to valid passages.

        Args:
            answer: Generated answer text.
            num_passages: Number of passages provided in context (e.g. 4).

        Returns:
            Tuple of (all_valid, valid_indices, fabricated_indices).
        """
        cited_indices: List[int] = []
        for match in cls.CITATION_PATTERN.finditer(answer):
            raw_nums = match.group(1).split(",")
            for n in raw_nums:
                try:
                    idx = int(n.strip())
                    if idx not in cited_indices:
                        cited_indices.append(idx)
                except ValueError:
                    continue

        valid_indices = [idx for idx in cited_indices if 1 <= idx <= num_passages]
        fabricated_indices = [idx for idx in cited_indices if idx < 1 or idx > num_passages]

        all_valid = len(fabricated_indices) == 0
        return all_valid, valid_indices, fabricated_indices

    @classmethod
    def validate_json_output(cls, text: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Attempt to extract and parse valid JSON from text.

        Handles markdown code fences (```json ... ```) automatically.
        """
        clean_text = text.strip()
        # Look for code block fence
        match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1).strip()

        try:
            parsed = json.loads(clean_text)
            return True, parsed, None
        except Exception as exc:
            return False, None, str(exc)

    @classmethod
    def extract_code_blocks(cls, text: str, language: Optional[str] = None) -> List[Dict[str, str]]:
        """Extract tagged code blocks from markdown fences (e.g. ```python ... ```)."""
        pattern = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
        blocks = []
        for match in pattern.finditer(text):
            lang = match.group(1).strip().lower()
            code = match.group(2).strip()
            if not language or lang == language.lower():
                blocks.append({"language": lang, "code": code})
        return blocks

    @classmethod
    def validate_code_syntax(cls, code: str, language: str = "python") -> Tuple[bool, Optional[str]]:
        """Validate standard syntax across languages (Python, C++, JavaScript, TypeScript, SQL).

        Returns:
            Tuple of (is_valid, error_message)
        """
        clean_code = code.strip()
        lang = language.strip().lower()

        if lang in ("python", "py"):
            import ast
            try:
                ast.parse(clean_code)
                return True, None
            except SyntaxError as e:
                return False, f"Python SyntaxError: {e}"

        elif lang in ("sql", "postgresql", "sqlite"):
            # Ensure balanced quotes and parentheses
            if clean_code.count("(") != clean_code.count(")"):
                return False, "Unbalanced parentheses in SQL query"
            if clean_code.count("'") % 2 != 0:
                return False, "Unterminated single quote in SQL string literal"
            keywords = ("select", "insert", "update", "delete", "create", "alter", "with", "drop")
            if not any(k in clean_code.lower() for k in keywords):
                return False, "Missing standard SQL operation keyword (SELECT, INSERT, WITH, etc.)"
            return True, None

        elif lang in ("javascript", "typescript", "js", "ts"):
            # Check balanced brackets, braces, and parentheses
            stack = []
            matching = {")": "(", "}": "{", "]": "["}
            for char in clean_code:
                if char in matching.values():
                    stack.append(char)
                elif char in matching.keys():
                    if not stack or stack.pop() != matching[char]:
                        return False, f"Mismatched bracket/brace '{char}' in {lang.upper()}"
            if stack:
                return False, f"Unclosed block delimiters in {lang.upper()}"
            return True, None

        elif lang in ("c++", "cpp", "c"):
            # Check balanced brackets, braces, and parentheses
            stack = []
            matching = {")": "(", "}": "{", "]": "["}
            for char in clean_code:
                if char in matching.values():
                    stack.append(char)
                elif char in matching.keys():
                    if not stack or stack.pop() != matching[char]:
                        return False, f"Mismatched bracket/brace '{char}' in C++"
            if stack:
                return False, "Unclosed block delimiters in C++"
            return True, None

        return True, None

    @classmethod
    def validate_json_schema(
        cls,
        data: Any,
        required_fields: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate parsed JSON data against required keys."""
        if not isinstance(data, dict):
            return False, f"Expected JSON object (dict), got {type(data).__name__}"
        if required_fields:
            missing = [k for k in required_fields if k not in data]
            if missing:
                return False, f"Missing required fields in JSON schema: {missing}"
        return True, None

