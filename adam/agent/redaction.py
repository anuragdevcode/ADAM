"""Sanitization and redaction engine for system prompts, API keys, credentials, and secrets.

Per Phase 04 specification:
- 'Enforce temperature 0–0.2, output schema and token limit; redact system prompts and keys.'
"""

import re
from typing import Any, Dict, List, Union

from adam.config import SIGNING_SECRET

# Regex patterns for sensitive keys, tokens, and secrets
SECRET_PATTERNS = [
    # API keys / Bearer tokens
    (re.compile(r"(?i)(?:bearer\s+[a-z0-9_\-\.]{15,}|api[_-]?key\s*[:=]\s*['\"]?[a-z0-9_\-\.]{15,}['\"]?)"), "[REDACTED_API_KEY]"),
    # Google Gemini / Firebase API keys
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{20,40}\b"), "[REDACTED_API_KEY]"),
    # General secret keys / signing secrets
    (re.compile(r"(?i)(?:signing[_-]?secret\s*[:=]\s*['\"]?[a-z0-9_\-\.]{10,}['\"]?|secret[_-]?key\s*[:=]\s*['\"]?[a-z0-9_\-\.]{10,}['\"]?)"), "[REDACTED_SECRET_KEY]"),
    # Configured ADAM signing secret
    (re.compile(re.escape(SIGNING_SECRET)), "[REDACTED_SIGNING_SECRET]"),
    # Default ADAM signing secret literal
    (re.compile(r"adam-uk-gov-default-auth-secret-key-2026"), "[REDACTED_SIGNING_SECRET]"),
    # Passwords in URLs or strings
    (re.compile(r"(?i)(?:password\s*[:=]\s*['\"]?[^\s'\"]{6,}['\"]?|:\/\/[^:]+:([^@]+)@)"), "[REDACTED_PASSWORD]"),
    # Private SSH or RSA keys
    (re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # AWS / Cloud Secret Keys
    (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"), "[REDACTED_AWS_SECRET]"),
]

# Patterns for system prompt leakage
SYSTEM_PROMPT_PATTERNS = [
    (re.compile(r"<\|im_start\|>system[\s\S]*?<\|im_end\|>", re.IGNORECASE), "[REDACTED_SYSTEM_PROMPT]"),
    (re.compile(r"<start_of_turn>user\s*You are ADAM[\s\S]*?<end_of_turn>", re.IGNORECASE), "[REDACTED_SYSTEM_PROMPT]"),
    (re.compile(r"<\|start_header_id\|>system<\|end_header_id\|>[\s\S]*?<\|eot_id\|>", re.IGNORECASE), "[REDACTED_SYSTEM_PROMPT]"),
    (re.compile(r"You are ADAM, an authorized AI assistant[\s\S]*?research brief marked 'Human Authority Required'\.", re.IGNORECASE), "[REDACTED_SYSTEM_PROMPT]"),
    (re.compile(r"You are ADAM, an authorized AI assistant[^\n\r]*", re.IGNORECASE), "[REDACTED_SYSTEM_PROMPT]"),
]


class SecretRedactor:
    """Redacts system prompts, authentication tokens, signing keys, and secrets."""

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        """Redact API keys, tokens, passwords, and signing secrets."""
        if not text:
            return ""
        result = text
        for pattern, replacement in SECRET_PATTERNS:
            result = pattern.sub(replacement, result)

        try:
            import adam.agent.redaction as _redaction_mod
            current_secret = getattr(_redaction_mod, "SIGNING_SECRET", None)
            if current_secret and current_secret in result:
                result = re.sub(re.escape(current_secret), "[REDACTED_SIGNING_SECRET]", result)
            from adam.config import SIGNING_SECRET as _config_secret
            if _config_secret and _config_secret in result:
                result = re.sub(re.escape(_config_secret), "[REDACTED_SIGNING_SECRET]", result)
        except Exception:
            pass

        return result

    @classmethod
    def redact_system_prompt(cls, text: str) -> str:
        """Redact system prompt instructions and internal steering tags."""
        if not text:
            return ""
        result = text
        for pattern, replacement in SYSTEM_PROMPT_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Apply full redaction of both secrets and system prompts."""
        if not text:
            return ""
        sanitized = cls.redact_secrets(text)
        sanitized = cls.redact_system_prompt(sanitized)
        return sanitized

    @classmethod
    def sanitize_data(cls, data: Any) -> Any:
        """Recursively sanitize strings in nested dictionaries, lists, and tuples."""
        if isinstance(data, str):
            return cls.sanitize_text(data)
        elif isinstance(data, dict):
            return {k: cls.sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(cls.sanitize_data(item) for item in data)
        return data
