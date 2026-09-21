"""Tests for fast-path system guidance and greeting detection."""
import pytest
from adam.rag.query import QueryUnderstanding


def test_greeting_exact_matches():
    exact_queries = [
        "hi", "hello", "hey", "namaste", "who are you", "what can you do",
        "what is adam", "how to search", "help", "capabilities",
        "नमस्ते", "नमस्कार", "प्रणाम", "आप कौन हैं", "अदम क्या है", "सहायता"
    ]
    for q in exact_queries:
        parsed = QueryUnderstanding.parse(q)
        assert parsed.is_greeting is True, f"Query '{q}' should be classified as is_greeting=True"


def test_greeting_short_variations():
    variations = [
        "hi adam", "hello adam", "about adam", "who is adam",
        "how do i search", "what are your capabilities", "help me search"
    ]
    for q in variations:
        parsed = QueryUnderstanding.parse(q)
        assert parsed.is_greeting is True, f"Query '{q}' should be classified as is_greeting=True"


def test_substantive_queries_not_greeting():
    substantive = [
        "What is the dearness allowance rate for 2024?",
        "Show financial sanction limits for Head of Department",
        "Procurement tender notice UK/FIN/2023/101",
        "वेतन आयोग की सिफारिशें क्या हैं?",
    ]
    for q in substantive:
        parsed = QueryUnderstanding.parse(q)
        assert parsed.is_greeting is False, f"Query '{q}' must NOT be classified as is_greeting"
