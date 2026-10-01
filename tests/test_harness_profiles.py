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


# ── Qwen 3.5 4B Key Capabilities Tests ──────────────────────────────────────

def test_qwen_profile_vision_multimodal_understanding():
    """Verify Capability 1: Native Vision-Language Understanding prompt formatting."""
    profile = QwenHarnessProfile(is_reasoning_variant=True)
    images = ["data:image/jpeg;base64,/9j/4AAQSkZJRg..."]

    # Test document understanding (OmniDocBench)
    doc_prompt = profile.format_vision_prompt("Read the GO stamp", images=images, task_type="document_understanding")
    assert "OmniDocBench" in doc_prompt
    assert "Extract exact tables, seals, signatures" in doc_prompt
    assert "Read the GO stamp" in doc_prompt

    # Test chart interpretation
    chart_prompt = profile.format_vision_prompt("Explain expenditure trend", images=images, task_type="chart_interpretation")
    assert "axis labels" in chart_prompt

    # Test parameter extraction with images
    params = profile.resolve_parameters(intent="rag", images=images)
    assert params.images == images


def test_qwen_profile_ultra_long_context_256k():
    """Verify Capability 2: Ultra-Long Context Processing up to 256k tokens."""
    profile = QwenHarnessProfile(is_reasoning_variant=True)

    long_ctx_params = profile.resolve_parameters(intent="long_context")
    assert long_ctx_params.context_size == 262_144
    assert long_ctx_params.max_tokens == 4096
    assert long_ctx_params.temperature == 0.1

    options = long_ctx_params.to_ollama_options()
    assert options["num_ctx"] == 262_144


def test_qwen_profile_coding_and_structured_outputs():
    """Verify Capability 3: Coding and Structured Outputs across languages."""
    profile = QwenHarnessProfile(is_reasoning_variant=True)

    # 1. Format coding prompt with unit test specification
    prompt = profile.format_coding_prompt(
        task="Write a Python class calculating Dearness Allowance.",
        language="python",
        test_spec="Verify 50% rate when basic >= 25000",
    )
    assert "[PYTHON]" in prompt
    assert "unit tests verifying" in prompt

    # 2. Syntax validation for Python
    valid_py = "def compute_da(basic: float) -> float:\n    return basic * 0.50\n"
    is_valid, err = HarnessOutputValidator.validate_code_syntax(valid_py, "python")
    assert is_valid is True
    assert err is None

    invalid_py = "def compute_da(basic: float)\n    return basic * 0.50"
    is_valid_bad, err_bad = HarnessOutputValidator.validate_code_syntax(invalid_py, "python")
    assert is_valid_bad is False
    assert "SyntaxError" in (err_bad or "")

    # 3. Syntax validation for SQL
    valid_sql = "SELECT id, title, page_number FROM public_records WHERE department_id = 'FINANCE' ORDER BY date DESC;"
    is_valid_sql, err_sql = HarnessOutputValidator.validate_code_syntax(valid_sql, "sql")
    assert is_valid_sql is True

    # 4. Code block extraction
    md_text = "Here is the implementation:\n```python\nx = 10\n```\nAnd SQL:\n```sql\nSELECT 1;\n```"
    blocks = HarnessOutputValidator.extract_code_blocks(md_text)
    assert len(blocks) == 2
    assert blocks[0]["language"] == "python"
    assert blocks[1]["language"] == "sql"

    # 5. Schema validation
    data = {"status": "approved", "score": 0.98}
    is_schema_ok, schema_err = HarnessOutputValidator.validate_json_schema(data, required_fields=["status", "score"])
    assert is_schema_ok is True
    assert schema_err is None


def test_qwen_profile_multilingual_coverage():
    """Verify Capability 4: Massive Multilingual Coverage and Devanagari regional scripts."""
    profile = QwenHarnessProfile(is_reasoning_variant=True)
    hindi_prompt = profile.format_multilingual_prompt("उत्तराखंड महंगाई भत्ता आदेश 2024", target_language="hi")
    assert "[HI]" in hindi_prompt
    assert "regional script" in hindi_prompt
    assert "उत्तराखंड महंगाई भत्ता आदेश 2024" in hindi_prompt


def test_qwen_profile_thinking_reasoning_mode():
    """Verify Capability 6: Thinking / Reasoning Mode (enable_thinking: true)."""
    profile = QwenHarnessProfile(is_reasoning_variant=True)

    # By default in chat / RAG mode, thinking is disabled to avoid high latency
    params_default = profile.resolve_parameters(intent="rag")
    assert params_default.thinking_enabled is False

    # Thinking enabled via intent or explicit parameter
    params_thinking = profile.resolve_parameters(intent="reasoning", thinking_budget=2048)
    assert params_thinking.thinking_enabled is True
    assert params_thinking.thinking_budget == 2048

    # Alias enable_thinking supported
    params_alias = profile.resolve_parameters(intent="rag", enable_thinking=True)
    assert params_alias.thinking_enabled is True

    # Explicitly disabled thinking overrides default
    params_disabled = profile.resolve_parameters(intent="reasoning", enable_thinking=False)
    assert params_disabled.thinking_enabled is False

    # Options include thinking budget in num_predict
    ollama_opts = params_thinking.to_ollama_options()
    assert ollama_opts["num_predict"] == 2048 + 2048  # max_tokens (2048) + thinking_budget (2048)


def test_autonomous_thinking_recommendation():
    """Verify autonomous detection when queries benefit from Deep Think mode."""
    from adam.rag.query import QueryUnderstanding

    # 1. STEM / Calculation queries
    rec_calc, reason_calc = QueryUnderstanding.detect_thinking_recommendation("Calculate the DA arrears for basic pay 45000")
    assert rec_calc is True
    assert "arithmetic" in (reason_calc or "").lower()

    rec_hi_calc, _ = QueryUnderstanding.detect_thinking_recommendation("कर्मचारी के महंगाई भत्ता की गणना कीजिए")
    assert rec_hi_calc is True

    # 2. Multi-hop comparison and reconciliation
    rec_comp, reason_comp = QueryUnderstanding.detect_thinking_recommendation("Compare the 2016 and 2023 procurement rules and resolve conflict")
    assert rec_comp is True
    assert "multi-hop" in (reason_comp or "").lower()

    rec_hi_comp, _ = QueryUnderstanding.detect_thinking_recommendation("दोनों शासनादेशों के बीच अंतर और संशोधन की तुलना करें")
    assert rec_hi_comp is True

    # 3. Structured coding / unit test queries
    rec_code, reason_code = QueryUnderstanding.detect_thinking_recommendation("Write a python script with unit test to validate GO format")
    assert rec_code is True
    assert "deductive" in (reason_code or "").lower()

    # 4. Standard conversational / factual query (should NOT trigger suggestion)
    rec_simple, reason_simple = QueryUnderstanding.detect_thinking_recommendation("What is the official holiday on 26 January?")
    assert rec_simple is False
    assert reason_simple is None


