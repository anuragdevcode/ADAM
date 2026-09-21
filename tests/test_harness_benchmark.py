"""Tests for the 24-prompt reproducible benchmark suite and evaluator."""

import pytest
from unittest.mock import patch, MagicMock

from adam.harness.benchmarks import (
    BENCHMARK_SUITE,
    BenchmarkPrompt,
    BenchmarkRunner,
    PromptEvaluationResult,
)


def test_benchmark_suite_covers_all_14_categories():
    assert len(BENCHMARK_SUITE) >= 20
    categories = {p.category for p in BENCHMARK_SUITE}
    required = {
        "General Conversation",
        "Reasoning",
        "Explanation",
        "Coding",
        "Long-Context",
        "Hindi",
        "English Precision",
        "Instruction Following",
        "Structured Response",
        "Administrative / Legal",
        "RAG Evidence",
        "Unanswerable",
        "Citation Accuracy",
        "Multi-Step Reasoning",
    }
    for req in required:
        assert req in categories, f"Missing category: {req}"


def test_evaluator_scores_passing_answer():
    runner = BenchmarkRunner()
    case = BenchmarkPrompt(
        id="test_pass",
        category="Reasoning",
        prompt="Sample",
        expected_substrings=["16", "combinations"],
    )
    score, passed, errors = runner._evaluate_answer(
        "There are 16 distinct combinations of 3 or more members.",
        case,
    )
    assert score == 1.0
    assert passed is True
    assert errors == []


def test_evaluator_fails_on_forbidden_substring():
    runner = BenchmarkRunner()
    case = BenchmarkPrompt(
        id="test_forbid",
        category="RAG Evidence",
        prompt="Sample",
        expected_substrings=["5,00,000"],
        forbidden_substrings=["50,00,000"],
    )
    score, passed, errors = runner._evaluate_answer(
        "The limit is 5,00,000 but another order says 50,00,000.",
        case,
    )
    assert passed is False
    assert any("forbidden" in e.lower() for e in errors)


def test_evaluator_checks_json_requirement():
    runner = BenchmarkRunner()
    case = BenchmarkPrompt(
        id="test_json",
        category="Structured Response",
        prompt="Sample",
        requires_json=True,
    )
    score_bad, passed_bad, _ = runner._evaluate_answer("Not json at all", case)
    assert passed_bad is False

    score_good, passed_good, _ = runner._evaluate_answer('{"department": "FIN", "status": "active"}', case)
    assert passed_good is True


def test_evaluator_checks_citation_requirement():
    runner = BenchmarkRunner()
    case = BenchmarkPrompt(
        id="test_cite",
        category="RAG Evidence",
        prompt="Sample",
        requires_citations=True,
    )
    _, passed_no_cite, _ = runner._evaluate_answer("Direct answer without citing anything.", case)
    assert passed_no_cite is False

    _, passed_with_cite, _ = runner._evaluate_answer("According to the official gazette [1], the limit is 5 Lakhs.", case)
    assert passed_with_cite is True


def test_benchmark_runner_full_suite_with_mock():
    """Verify full scorecard generation across modes using mock runner."""
    runner = BenchmarkRunner()

    with patch.object(
        runner,
        "_execute_ollama_call",
        return_value=(
            "Valid answer with [1] citation and 16 combinations for ADAM in Uttarakhand.",
            None,
            45.0,
            120,
            80,
        ),
    ):
        report = runner.run_full_benchmark(
            prompts=BENCHMARK_SUITE[:3],
            modes=["adam_baseline", "adam_harness"],
        )

    assert report["total_prompts"] == 3
    assert "adam_baseline" in report["summary"]
    assert "adam_harness" in report["summary"]
    assert report["summary"]["adam_harness"]["total"] == 3
