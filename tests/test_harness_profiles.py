"""Tests for model-specific harness profiles, routing, and validators."""

import pytest
from adam.harness.parameters import ModelInferenceParameters
from adam.harness.routing import HarnessRouter
from adam.harness.profiles import (
    QwenHarnessProfile,
    LlamaHarnessProfile,
    GemmaHarnessProfile,
    GeminiHarnessProfile,
    DefaultHarnessProfile,
)
from adam.harness.context import ContextStrategy
from adam.harness.templates import PromptTemplateRegistry
from adam.harness.validators import HarnessOutputValidator
from adam.rag.models import EvidencePassage, EvidencePacket, ParsedQuery


# ── ModelInferenceParameters ────────────────────────────────────────────────

def test_inference_parameters_to_ollama_options():
    params = ModelInferenceParameters(
        temperature=0.2,
        top_p=0.9,
        top_k=40,
        min_p=0.05,
        max_tokens=1024,
        context_size=8192,
        thinking_enabled=False,
    )
    opts = params.to_ollama_options()
    assert opts["temperature"] == 0.2
    assert opts["top_p"] == 0.9
    assert opts["top_k"] == 40
    assert opts["min_p"] == 0.05
    assert opts["num_predict"] == 1024
    assert opts["num_ctx"] == 8192


def test_inference_parameters_with_thinking_budget():
    params = ModelInferenceParameters(
        temperature=0.4,
        max_tokens=1024,
        thinking_enabled=True,
        thinking_budget=1024,
    )
    opts = params.to_ollama_options()
    assert opts["num_predict"] == 2048  # max_tokens + thinking_budget


# ── HarnessRouter ───────────────────────────────────────────────────────────

def test_router_resolves_qwen_profiles():
    prof_std = HarnessRouter.resolve_profile("qwen2.5:3b")
    assert isinstance(prof_std, QwenHarnessProfile)
    assert prof_std.is_reasoning_variant is False

    prof_reasoning = HarnessRouter.resolve_profile("qwen3-4b-instruct-q4")
    assert isinstance(prof_reasoning, QwenHarnessProfile)
    assert prof_reasoning.is_reasoning_variant is True


def test_router_resolves_llama():
    prof = HarnessRouter.resolve_profile("llama-3.2-3b-instruct-q4")
    assert isinstance(prof, LlamaHarnessProfile)


def test_router_resolves_gemma():
    prof = HarnessRouter.resolve_profile("gemma-3-4b-it-q4")
    assert isinstance(prof, GemmaHarnessProfile)


def test_router_resolves_gemini():
    prof = HarnessRouter.resolve_profile("gemini-3.6-flash")
    assert isinstance(prof, GeminiHarnessProfile)


def test_router_resolves_default_fallback():
    prof = HarnessRouter.resolve_profile("some-unknown-model-xyz")
    assert isinstance(prof, DefaultHarnessProfile)


# ── QwenHarnessProfile ─────────────────────────────────────────────────────

def test_qwen_profile_rag_vs_conversational():
    profile = QwenHarnessProfile(is_reasoning_variant=False)

    rag_params = profile.resolve_parameters(intent="rag")
    assert rag_params.temperature == 0.2
    assert rag_params.max_tokens == 1024

    conv_params = profile.resolve_parameters(intent="conversational")
    assert conv_params.temperature == 0.6
    assert conv_params.max_tokens == 1536


# ── ContextStrategy ─────────────────────────────────────────────────────────

def test_context_clean_passage_content_strips_letterheads():
    raw = (
        "GOVERNMENT OF UTTARAKHAND\n"
        "Directorate of Finance & Treasury\n"
        "Order No: UK/FIN/2023/101\n"
        "The ceiling for direct purchase is Rs. 5,00,000."
    )
    cleaned = ContextStrategy.clean_passage_content(raw)
    assert "GOVERNMENT OF UTTARAKHAND" not in cleaned
    assert "Directorate of Finance" not in cleaned
    assert "ceiling for direct purchase is Rs. 5,00,000" in cleaned


def test_context_format_compact_evidence():
    passages = [
        EvidencePassage(
            chunk_id="c1",
            document_id="d1",
            version_id="v1",
            title="Procurement Rules 2023",
            department_id="FIN",
            doc_type="RULES",
            page_start=12,
            page_end=12,
            section_heading="Procurement",
            content="Procurement limit is Rs 5 Lakhs.",
            go_number="UK/FIN/101",
        ),
        EvidencePassage(
            chunk_id="c2",
            document_id="d2",
            version_id="v2",
            title="Works Code",
            department_id="PWD",
            doc_type="RULES",
            page_start=4,
            page_end=4,
            section_heading="Repairs",
            content="Emergency repair limit is Rs 2 Lakhs.",
            go_number="UK/PWD/45",
        ),
    ]
    formatted = ContextStrategy.format_compact_evidence(passages)
    assert "Passage [1] [Procurement Rules 2023 (GO: UK/FIN/101), Page 12]:" in formatted
    assert "Passage [2] [Works Code (GO: UK/PWD/45), Page 4]:" in formatted


def test_build_grounded_rag_prompt():
    packet = EvidencePacket(
        query=ParsedQuery(raw_query="What is the limit?", clean_query="What is the limit?"),
        passages=[
            EvidencePassage(
                chunk_id="c1",
                document_id="d1",
                version_id="v1",
                title="Rules",
                department_id="FIN",
                doc_type="RULES",
                page_start=1,
                page_end=1,
                section_heading="Limits",
                content="Limit is 5 Lakhs.",
            )
        ],
    )
    prompt = ContextStrategy.build_grounded_rag_prompt("What is the limit?", packet)
    assert "Reference Records:" in prompt
    assert "User Question: What is the limit?" in prompt
    assert "Cite only relevant passages [1]" in prompt or "citations like [1]" in prompt


# ── HarnessOutputValidator ─────────────────────────────────────────────────

def test_separate_thinking_tokens_complete_block():
    raw = "<think>\nThinking about the problem...\nStep 1: Calculate 5!\n</think>\nThe answer is 16."
    answer, thinking = HarnessOutputValidator.separate_thinking_tokens(raw)
    assert answer == "The answer is 16."
    assert "Thinking about the problem" in (thinking or "")
    assert "<think>" not in answer
    assert "</think>" not in answer


def test_separate_thinking_tokens_dangling_close():
    raw = "Thinking about steps...</think>The final result is 42."
    answer, thinking = HarnessOutputValidator.separate_thinking_tokens(raw)
    assert answer == "The final result is 42."
    assert "Thinking about steps" in (thinking or "")


def test_separate_thinking_tokens_no_thinking():
    raw = "Direct response without scratchpad."
    answer, thinking = HarnessOutputValidator.separate_thinking_tokens(raw)
    assert answer == "Direct response without scratchpad."
    assert thinking is None


def test_validate_citation_indices_all_valid():
    answer = "Under the procurement rules [1], the limit is 5 Lakhs. See also [2]."
    all_valid, valid, fab = HarnessOutputValidator.validate_citation_indices(answer, num_passages=4)
    assert all_valid is True
    assert valid == [1, 2]
    assert fab == []


def test_validate_citation_indices_fabricated():
    answer = "According to order [1] and non-existent passage [9], the rate is 10%."
    all_valid, valid, fab = HarnessOutputValidator.validate_citation_indices(answer, num_passages=4)
    assert all_valid is False
    assert valid == [1]
    assert fab == [9]


def test_validate_json_output_markdown_fence():
    text = "Here is the response:\n```json\n{\"status\": \"approved\", \"code\": 200}\n```"
    is_valid, data, err = HarnessOutputValidator.validate_json_output(text)
    assert is_valid is True
    assert data == {"status": "approved", "code": 200}
    assert err is None


def test_validate_json_output_invalid():
    text = "Not a json payload at all"
    is_valid, data, err = HarnessOutputValidator.validate_json_output(text)
    assert is_valid is False
    assert data is None
    assert err is not None
