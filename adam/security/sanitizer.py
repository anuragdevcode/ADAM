"""Security, sanitization, XSS prevention, and prompt injection defense utilities for ADAM."""

import html
import re
from typing import Any, Dict, List, Optional, Tuple, Union

# High-risk prompt injection patterns found in adversarial user input or untrusted documents
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|directives|prompts|rules)\b"),
    re.compile(r"(?i)\b(?:system\s+override|admin\s+override|developer\s+mode|jailbreak)\b"),
    re.compile(r"(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(?:a|an|unrestricted|god\s+mode|dan)\b"),
    re.compile(r"(?i)\b(?:reveal|print|output|display|show|leak)\s+(?:your\s+)?(?:system\s+prompt|instructions|secret\s+key|password|api\s*key)\b"),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|start_header_id\|>|<\|eot_id\|>|\[SYSTEM\]|\[ADMIN\b"),
]

# Common XSS patterns
XSS_PATTERNS = [
    re.compile(r"(?i)<\s*script[^>]*>[\s\S]*?<\s*/\s*script\s*>"),
    re.compile(r"(?i)<\s*script[^>]*>"),
    re.compile(r"(?i)javascript\s*:\s*"),
    re.compile(r"(?i)on\w+\s*=\s*['\"][^'\"]*['\"]"),
    re.compile(r"(?i)<\s*(?:iframe|object|embed|applet|form|input|button)\b[^>]*>"),
]


class SecuritySanitizer:
    """Provides security checks, sanitization, and defense against XSS and injection attacks."""

    @classmethod
    def sanitize_xss(cls, text: str) -> str:
        """Strip dangerous HTML tags and escape remaining HTML entities to prevent XSS."""
        if not text:
            return ""
        cleaned = text
        for pat in XSS_PATTERNS:
            cleaned = pat.sub("", cleaned)
        return html.escape(cleaned, quote=True)

    @classmethod
    def contains_xss(cls, text: str) -> bool:
        """Detect if input text contains potential XSS vectors."""
        if not text:
            return False
        for pat in XSS_PATTERNS:
            if pat.search(text):
                return True
        return False

    @classmethod
    def detect_prompt_injection(cls, text: str) -> Tuple[bool, List[str]]:
        """Detect prompt injection attempts in text (user queries or document bodies)."""
        if not text:
            return False, []
        matched = []
        for pat in PROMPT_INJECTION_PATTERNS:
            if pat.search(text):
                matched.append(pat.pattern)
        return len(matched) > 0, matched

    @classmethod
    def quote_document_context(cls, text: str) -> str:
        """Safely enclose document context into quarantined boundary delimiters.

        Neutralizes delimiter-breaking tokens and treats text strictly as untrusted data.
        """
        if not text:
            return ""
        # Neutralize ChatML/delimiter tags
        safe_text = re.sub(r"<\|im_start\|>|<\|im_end\|>|<\|start_header_id\|>|<\|eot_id\|>", "[TAG_DEFUSED]", text)
        return f"=== BEGIN UNTRUSTED DOCUMENT PASSAGE ===\n{safe_text}\n=== END UNTRUSTED DOCUMENT PASSAGE ==="

    @classmethod
    def sanitize_error_message(cls, err: Union[Exception, str], is_public: bool = True) -> str:
        """Ensure no internal database table names, SQL statements, or stack traces leak."""
        err_str = str(err)
        # Sensitive internal identifiers to redact
        sensitive_terms = [
            "sqlite3", "psycopg2", "sqlalchemy", "traceback", "file \"",
            "select ", "insert ", "update ", "delete ", "from ", "where ",
            "password", "secret_key", "signing_secret", "bearer ", "token"
        ]
        lower_err = err_str.lower()
        for term in sensitive_terms:
            if term in lower_err:
                return "An internal system error occurred. Please contact the administrator with the trace ID."
        return err_str
