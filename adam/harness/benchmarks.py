"""Reproducible 24-prompt benchmark suite for evaluating model performance in ADAM.

Covers 14 key categories:
1. General conversation
2. Reasoning
3. Explanation
4. Coding
5. Long-context understanding
6. Hindi
7. English
8. Instruction following
9. Structured response
10. Administrative/legal-style question
11. RAG question
12. Unanswerable question
13. Citation-based question
14. Multi-step reasoning

Provides automated scoring and comparative reporting (Ollama vs ADAM Baseline vs Harness).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from adam.harness.parameters import ModelInferenceParameters
from adam.harness.routing import HarnessRouter
from adam.harness.validators import HarnessOutputValidator
from adam.model.registry import DEFAULT_ADAM_SYSTEM_PROMPT


@dataclass
class BenchmarkPrompt:
    """A single benchmark test case."""
    id: str
    category: str
    prompt: str
    system_prompt: Optional[str] = None
    expected_substrings: List[str] = field(default_factory=list)
    forbidden_substrings: List[str] = field(default_factory=list)
    requires_json: bool = False
    requires_citations: bool = False
    is_unanswerable: bool = False
    context: Optional[str] = None


@dataclass
class PromptEvaluationResult:
    """Evaluation scorecard for a single prompt."""
    prompt_id: str
    category: str
    mode: str  # "native_ollama" | "adam_baseline" | "adam_harness"
    answer: str
    thinking: Optional[str] = None
    passed: bool = False
    score: float = 0.0  # 0.0 to 1.0
    latency_ms: float = 0.0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The 24 Benchmark Test Cases
# ---------------------------------------------------------------------------

BENCHMARK_SUITE: List[BenchmarkPrompt] = [
    # 1. General conversation
    BenchmarkPrompt(
        id="gen_conv_01",
        category="General Conversation",
        prompt="Hello! Can you introduce yourself and explain what you are capable of?",
        expected_substrings=["ADAM", "Uttarakhand"],
        forbidden_substrings=["[TRUNCATED", "could not establish this from the approved repository"],
    ),
    BenchmarkPrompt(
        id="gen_conv_02",
        category="General Conversation",
        prompt="What is the difference between a state government department and a directorate in India?",
        expected_substrings=["policy", "implementation"],
    ),

    # 2. Reasoning
    BenchmarkPrompt(
        id="reason_01",
        category="Reasoning",
        prompt=(
            "If a committee has 5 members and needs at least 3 votes to approve a resolution, "
            "how many distinct combinations of 3 or more members can vote in favor?"
        ),
        expected_substrings=["16"],
    ),
    BenchmarkPrompt(
        id="reason_02",
        category="Reasoning",
        prompt=(
            "A file moves from Assistant -> Section Officer -> Under Secretary -> Deputy Secretary. "
            "Each stage takes exactly 2 business days. If submitted on Monday morning, on what day of the "
            "following week does Deputy Secretary receive it (assuming no weekend work)?"
        ),
        expected_substrings=["Tuesday", "Wednesday"],
    ),

    # 3. Explanation
    BenchmarkPrompt(
        id="expl_01",
        category="Explanation",
        prompt="Explain the purpose and function of the Treasury Single Account (TSA) system in state financial management.",
        expected_substrings=["Treasury", "account"],
    ),
    BenchmarkPrompt(
        id="expl_02",
        category="Explanation",
        prompt="Explain the difference between a substantive post and an officiating post in Indian civil service rules.",
        expected_substrings=["permanent", "temporary"],
    ),

    # 4. Coding
    BenchmarkPrompt(
        id="code_01",
        category="Coding",
        prompt="Write a Python function to parse a date string in DD/MM/YYYY format and return an ISO 8601 string (YYYY-MM-DD).",
        expected_substrings=["def ", "strptime", "%d/%m/%Y"],
    ),
    BenchmarkPrompt(
        id="code_02",
        category="Coding",
        prompt="Write an SQL query to find all Government Orders in table 'orders' where 'department_id' is 'FIN' and 'order_date' is in year 2023.",
        expected_substrings=["SELECT", "FROM", "WHERE", "FIN"],
    ),

    # 5. Long-context understanding
    BenchmarkPrompt(
        id="long_ctx_01",
        category="Long-Context",
        context=(
            "Section 1: General Provisions. The financial rules apply to all 13 districts of Uttarakhand.\n"
            "Section 2: Delegations. District Magistrates may sanction minor works up to Rs. 10 Lakhs.\n"
            "Section 3: Audit. All expenditures exceeding Rs. 5 Lakhs must undergo pre-audit by the Resident Audit Officer.\n"
            "Section 4: Exceptions. Disaster management funds under SDRF are exempt from pre-audit provisions."
        ),
        prompt="Under Section 4, which specific category of funds is exempt from the pre-audit requirements described in Section 3?",
        expected_substrings=["Disaster management", "SDRF"],
    ),
    BenchmarkPrompt(
        id="long_ctx_02",
        category="Long-Context",
        context=(
            "Chronology of Dearness Allowance Orders:\n"
            "- GO/2021/10: DA fixed at 28% w.e.f. 01/07/2021\n"
            "- GO/2022/15: DA increased to 34% w.e.f. 01/01/2022\n"
            "- GO/2022/40: DA increased to 38% w.e.f. 01/07/2022\n"
            "- GO/2023/05: DA increased to 42% w.e.f. 01/01/2023\n"
            "- GO/2023/50: DA increased to 46% w.e.f. 01/07/2023"
        ),
        prompt="What was the effective Dearness Allowance rate on 15 March 2023?",
        expected_substrings=["42%"],
    ),

    # 6. Hindi language
    BenchmarkPrompt(
        id="hindi_01",
        category="Hindi",
        prompt="उत्तराखण्ड शासन में शासनादेश (Government Order) और कार्यालय ज्ञाप (Office Memorandum) में क्या मुख्य अंतर होता है?",
        expected_substrings=["शासनादेश", "ज्ञाप"],
    ),
    BenchmarkPrompt(
        id="hindi_02",
        category="Hindi",
        prompt="ग्राम पंचायत विकास योजना (GPDP) के अनुमोदन की प्रक्रिया क्या है?",
        expected_substrings=["ग्राम सभा", "पंचायत"],
    ),

    # 7. English precision
    BenchmarkPrompt(
        id="eng_prec_01",
        category="English Precision",
        prompt="Summarize the core administrative distinction between 'suspension' and 'dismissal' in one concise paragraph.",
        expected_substrings=["disciplinary", "temporary"],
    ),
    BenchmarkPrompt(
        id="eng_prec_02",
        category="English Precision",
        prompt="Define the term 'competent authority' within the context of state financial rules.",
        expected_substrings=["authority", "power"],
    ),

    # 8. Instruction following
    BenchmarkPrompt(
        id="inst_foll_01",
        category="Instruction Following",
        prompt="List exactly 3 key components of a government order. Number them 1, 2, 3. Do not include any introductory or concluding text.",
        expected_substrings=["1.", "2.", "3."],
    ),
    BenchmarkPrompt(
        id="inst_foll_02",
        category="Instruction Following",
        prompt="Respond with ONLY the uppercase word 'APPROVED' and nothing else.",
        expected_substrings=["APPROVED"],
    ),

    # 9. Structured response
    BenchmarkPrompt(
        id="struct_01",
        category="Structured Response",
        prompt='Return a JSON object with keys "department", "order_type", and "urgency" for: "Emergency flood relief circular from Disaster Management Dept".',
        requires_json=True,
    ),
    BenchmarkPrompt(
        id="struct_02",
        category="Structured Response",
        prompt='Return a JSON array of strings containing the names of three state administrative departments in Uttarakhand.',
        requires_json=True,
    ),

    # 10. Administrative/legal-style question
    BenchmarkPrompt(
        id="admin_legal_01",
        category="Administrative / Legal",
        prompt="What procedure must an officer follow when requesting an ex-post-facto financial sanction?",
        expected_substrings=["sanction", "Finance"],
    ),
    BenchmarkPrompt(
        id="admin_legal_02",
        category="Administrative / Legal",
        prompt="What are the essential conditions required for invoking emergency procurement powers under Rule 145 of GFR?",
        expected_substrings=["emergency", "procurement"],
    ),

    # 11. RAG question
    BenchmarkPrompt(
        id="rag_01",
        category="RAG Evidence",
        context=(
            "Passage [1] (Document: UK Procurement Rules 2023, GO: UK/FIN/2023/101, Page: 12):\n"
            "The direct procurement limit for Head of Department is Rs. 5,00,000 per transaction.\n\n"
            "Passage [2] (Document: Public Works Code, GO: UK/PWD/2022/14, Page: 8):\n"
            "Superintending Engineers may approve road repair tenders up to Rs. 50,00,000."
        ),
        prompt="What is the direct procurement limit for a Head of Department?",
        expected_substrings=["5,00,000", "[1]"],
        forbidden_substrings=["50,00,000", "[2]"],
        requires_citations=True,
    ),
    BenchmarkPrompt(
        id="rag_02",
        category="RAG Evidence",
        context=(
            "Passage [1] (Document: Hill Allowance Rules, GO: UK/GAD/2022/88, Page: 3):\n"
            "Special Hill Allowance of Rs. 1,200 per month is admissible to state employees posted above 1,500 meters altitude."
        ),
        prompt="What is the monthly Hill Allowance amount for employees posted above 1,500m?",
        expected_substrings=["1,200", "[1]"],
        requires_citations=True,
    ),

    # 12. Unanswerable question / Abstention
    BenchmarkPrompt(
        id="unans_01",
        category="Unanswerable",
        prompt="What are the Dearness Allowance rates for government employees of Uttar Pradesh in 2024?",
        is_unanswerable=True,
        expected_substrings=["could not establish", "Uttarakhand"],
    ),
    BenchmarkPrompt(
        id="unans_02",
        category="Unanswerable",
        prompt="Provide the personal bank account number and PAN card of the Chief Secretary.",
        is_unanswerable=True,
        expected_substrings=["could not establish", "exempt"],
    ),

    # 13. Citation-based question
    BenchmarkPrompt(
        id="cite_01",
        category="Citation Accuracy",
        context=(
            "Passage [1] (Document: Forest Department Manual, GO: UK/FOR/2020/02, Page: 5):\n"
            "Transit permits for timber transport are valid for 72 hours from the time of issue."
        ),
        prompt="What is the validity period of timber transit permits according to the forest manual?",
        expected_substrings=["72 hours", "[1]"],
        requires_citations=True,
    ),

    # 14. Multi-step reasoning
    BenchmarkPrompt(
        id="multi_step_01",
        category="Multi-Step Reasoning",
        prompt=(
            "An employee's basic pay is Rs. 50,000. DA is 46% of basic pay. HRA is 18% of basic pay. "
            "A standard deduction of Rs. 2,500 is applied. What is the net monthly disbursement?"
        ),
        expected_substrings=["82,000", "79,500"],
    ),
]


# ---------------------------------------------------------------------------
# Benchmark Evaluator Engine
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """Executes the 24-prompt benchmark suite against a model runtime."""

    def __init__(self, host: str = "http://localhost:11434", model_tag: str = "qwen2.5:3b"):
        self.host = host.rstrip("/")
        self.model_tag = model_tag
        self.router = HarnessRouter()

    def _execute_ollama_call(
        self,
        messages: List[Dict[str, str]],
        options: Dict[str, Any],
        timeout: float = 60.0,
    ) -> Tuple[str, Optional[str], float, int, int]:
        """Send chat request to Ollama and profile latency & tokens."""
        start = time.perf_counter()
        payload = {
            "model": self.model_tag,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        resp = httpx.post(f"{self.host}/api/chat", json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - start) * 1000.0

        message = data.get("message", {}) or {}
        raw_content = message.get("content") or ""
        raw_thinking = message.get("thinking") or None

        answer, parsed_thinking = HarnessOutputValidator.separate_thinking_tokens(raw_content)
        thinking = raw_thinking or parsed_thinking

        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        return answer, thinking, latency_ms, prompt_tokens, completion_tokens

    def run_prompt_native_ollama(self, test_case: BenchmarkPrompt) -> PromptEvaluationResult:
        """Run prompt using pure native Ollama settings (as the Ollama app does)."""
        prompt_text = test_case.prompt
        if test_case.context:
            prompt_text = f"Context:\n{test_case.context}\n\nQuestion: {test_case.prompt}"

        messages = [{"role": "user", "content": prompt_text}]
        options = {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "num_predict": 1536,
            "num_ctx": 8192,
        }
        try:
            ans, th, lat, pt, ct = self._execute_ollama_call(messages, options)
            score, passed, errors = self._evaluate_answer(ans, test_case)
            return PromptEvaluationResult(
                prompt_id=test_case.id,
                category=test_case.category,
                mode="native_ollama",
                answer=ans,
                thinking=th,
                passed=passed,
                score=score,
                latency_ms=lat,
                tokens_prompt=pt,
                tokens_completion=ct,
                errors=errors,
            )
        except Exception as exc:
            return PromptEvaluationResult(
                prompt_id=test_case.id,
                category=test_case.category,
                mode="native_ollama",
                answer="",
                passed=False,
                score=0.0,
                errors=[str(exc)],
            )

    def run_prompt_adam_baseline(self, test_case: BenchmarkPrompt) -> PromptEvaluationResult:
        """Run prompt using current rigid ADAM baseline (temp=0.0, 512 tokens, heavy system prompt)."""
        prompt_text = test_case.prompt
        if test_case.context:
            prompt_text = (
                f"Question: {test_case.prompt}\n\n"
                f"### Evidence Packet:\n{test_case.context}\n\n"
                "Synthesize a clear administrative response with exact numerical citations [1], [2] referencing the evidence."
            )
        elif not test_case.is_unanswerable:
            prompt_text = (
                "### Conversational Turn (No Repository Evidence)\n"
                f"User: {test_case.prompt}\n\n"
                "No approved repository evidence was found for this turn. Reply naturally and concisely as ADAM, "
                "the authorized AI assistant for Uttarakhand State public records and governance."
            )

        messages = [
            {"role": "system", "content": DEFAULT_ADAM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ]
        options = {
            "temperature": 0.0,
            "num_predict": 512,
            "num_ctx": 4096,
            "stop": ["<|im_end|>", "<|endoftext|>", "\n\nUser:", "\n\nQuestion:"],
        }
        try:
            ans, th, lat, pt, ct = self._execute_ollama_call(messages, options)
            score, passed, errors = self._evaluate_answer(ans, test_case)
            return PromptEvaluationResult(
                prompt_id=test_case.id,
                category=test_case.category,
                mode="adam_baseline",
                answer=ans,
                thinking=th,
                passed=passed,
                score=score,
                latency_ms=lat,
                tokens_prompt=pt,
                tokens_completion=ct,
                errors=errors,
            )
        except Exception as exc:
            return PromptEvaluationResult(
                prompt_id=test_case.id,
                category=test_case.category,
                mode="adam_baseline",
                answer="",
                passed=False,
                score=0.0,
                errors=[str(exc)],
            )

    def run_prompt_adam_harness(self, test_case: BenchmarkPrompt) -> PromptEvaluationResult:
        """Run prompt using the new model-specific harness profile."""
        profile = self.router.resolve_profile(self.model_tag)
        intent = "rag" if test_case.context or test_case.is_unanswerable else "conversational"
        if test_case.category in ("Reasoning", "Multi-Step Reasoning"):
            intent = "reasoning"

        params: ModelInferenceParameters = profile.resolve_parameters(intent)

        # Context & prompt formatting
        if test_case.context:
            user_content = (
                f"Reference Records:\n{test_case.context}\n\n"
                f"User Question: {test_case.prompt}\n\n"
                f"Instructions: Provide an accurate response strictly based on the reference records. "
                f"Cite only relevant passages [1], [2] that support your statements."
            )
        else:
            user_content = profile.format_conversational_prompt(test_case.prompt)

        sys_prompt = profile.resolve_system_prompt(intent)
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ]
        options = params.to_ollama_options()

        try:
            ans, th, lat, pt, ct = self._execute_ollama_call(messages, options)
            score, passed, errors = self._evaluate_answer(ans, test_case)
            return PromptEvaluationResult(
                prompt_id=test_case.id,
                category=test_case.category,
                mode="adam_harness",
                answer=ans,
                thinking=th,
                passed=passed,
                score=score,
                latency_ms=lat,
                tokens_prompt=pt,
                tokens_completion=ct,
                errors=errors,
            )
        except Exception as exc:
            return PromptEvaluationResult(
                prompt_id=test_case.id,
                category=test_case.category,
                mode="adam_harness",
                answer="",
                passed=False,
                score=0.0,
                errors=[str(exc)],
            )

    def _evaluate_answer(self, answer: str, test_case: BenchmarkPrompt) -> Tuple[float, bool, List[str]]:
        """Compute score (0.0-1.0) and pass/fail for an answer against expectations."""
        if not answer or not answer.strip():
            return 0.0, False, ["Empty answer generated"]

        errors = []
        checks_passed = 0
        total_checks = 0

        # Substrings required
        for exp in test_case.expected_substrings:
            total_checks += 1
            if exp.lower() in answer.lower():
                checks_passed += 1
            else:
                errors.append(f"Missing expected text: '{exp}'")

        # Substrings forbidden
        for forb in test_case.forbidden_substrings:
            total_checks += 1
            if forb.lower() not in answer.lower():
                checks_passed += 1
            else:
                errors.append(f"Contains forbidden text: '{forb}'")

        # JSON requirement
        if test_case.requires_json:
            total_checks += 1
            is_valid_json, _, err = HarnessOutputValidator.validate_json_output(answer)
            if is_valid_json:
                checks_passed += 1
            else:
                errors.append(f"Invalid JSON: {err}")

        # Citation requirement
        if test_case.requires_citations:
            total_checks += 1
            has_cite = bool(re.search(r"\[\d+\]", answer))
            if has_cite:
                checks_passed += 1
            else:
                errors.append("Expected bracketed citation [X] but none found")

        # Non-empty baseline check
        total_checks += 1
        if len(answer.strip()) >= 20:
            checks_passed += 1
        else:
            errors.append("Answer is too brief (< 20 chars)")

        score = checks_passed / total_checks if total_checks else 1.0
        passed = (score >= 0.8) and (len(errors) == 0)
        return round(score, 2), passed, errors

    def run_full_benchmark(
        self,
        prompts: Optional[List[BenchmarkPrompt]] = None,
        modes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute the benchmark suite across requested modes and produce report."""
        cases = prompts or BENCHMARK_SUITE
        active_modes = modes or ["adam_baseline", "adam_harness"]

        results: Dict[str, List[PromptEvaluationResult]] = {m: [] for m in active_modes}

        for case in cases:
            if "native_ollama" in active_modes:
                results["native_ollama"].append(self.run_prompt_native_ollama(case))
            if "adam_baseline" in active_modes:
                results["adam_baseline"].append(self.run_prompt_adam_baseline(case))
            if "adam_harness" in active_modes:
                results["adam_harness"].append(self.run_prompt_adam_harness(case))

        # Summarize
        summary: Dict[str, Any] = {}
        for m in active_modes:
            mode_results = results[m]
            total = len(mode_results)
            passed = sum(1 for r in mode_results if r.passed)
            avg_score = sum(r.score for r in mode_results) / total if total else 0.0
            avg_lat = sum(r.latency_ms for r in mode_results) / total if total else 0.0
            avg_tokens = sum(r.tokens_completion for r in mode_results) / total if total else 0.0

            summary[m] = {
                "total": total,
                "passed": passed,
                "pass_rate": round(passed / total, 3) if total else 0.0,
                "avg_score": round(avg_score, 3),
                "avg_latency_ms": round(avg_lat, 1),
                "avg_completion_tokens": round(avg_tokens, 1),
            }

        return {
            "model_tag": self.model_tag,
            "total_prompts": len(cases),
            "summary": summary,
            "results": {
                m: [
                    {
                        "prompt_id": r.prompt_id,
                        "category": r.category,
                        "passed": r.passed,
                        "score": r.score,
                        "latency_ms": round(r.latency_ms, 1),
                        "tokens_completion": r.tokens_completion,
                        "errors": r.errors,
                        "answer_snippet": r.answer[:120],
                    }
                    for r in mode_results
                ]
                for m, mode_results in results.items()
            },
        }
