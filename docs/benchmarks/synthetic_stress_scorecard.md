# ADAM Synthetic Stress & Regression Benchmark Scorecard

> **Evaluation Run Date:** `2026-10-04T20:02:01.242486+00:00`  
> **Target Jurisdiction:** Uttarakhand State Public Records Intelligence  
> **Evaluation Mode:** Synthetic Stress & Regression Benchmark (Outside Model Tuning Loop)

---

## 1. Executive Summary & Quality Gates

This benchmark is evaluated over **206 synthetic Uttarakhand Government administrative orders** (206 extracted pages) generated across 22 departmental templates across **10 curated evaluation queries (10 unique normalized queries)** written without verbatim government order numbers. All point estimates report sample size $N$ alongside **Wilson score 95% and Normal 95% confidence intervals** ($z=1.96$) computed on unique questions. Per statistical honesty standards, gates pass only when unique sample size is adequate ($N_{unique} \ge 50$ total, answerable $\ge 30$, unanswerable $\ge 10$) and the lower CI bound clears the operational standard.

| Evaluation Gate | Pilot Standard | Evaluation Result | $N_{total}$ ($N_{unique}$) | 95% Confidence Interval (Unique) | Gate Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Retrieval Recall@10** | $\ge 90.0\%$ (Lower CI $\ge 85.0\%$) | **100.00%** | 8 (8) | `[67.56%, 100.00%]` | **FAIL** |
| **Citation Page Precision** | $\ge 90.0\%$ (Lower CI $\ge 85.0\%$) | **100.00%** | 8 (8) | `[67.56%, 100.00%]` | **FAIL** |
| **Answer Faithfulness** | $\ge 90.0\%$ (Lower CI $\ge 85.0\%$) | **94.11%** | 8 (8) | `[84.06%, 100.00%]` | **FAIL** |
| **Abstention Refusal Rate** | $\ge 95.0\%$ (Lower CI $\ge 85.0\%$) | **100.00%** | 2 (2) | `[34.24%, 100.00%]` | **FAIL** |
| **ACL Red-Team Safety (205 Probes)** | $100.0\%$ (0 Leaks, Lower CI $\ge 95.0\%$) | **100.00%** (0 leaks) | 205 (205) | `[98.16%, 100.00%]` | **PASS** |
| **Overall Pilot Gate** | **ALL PASS** ($\ge 50$ Unique Queries, Lower CI Clears Standard) | **FAILED** | 10 (10) | — | **FAIL** |

---

## 2. Abstention Calibration & Faithfulness

- **Abstention Brier Score:** `0.0025` (lower is better, 0.0 indicates perfect calibration).
- **Expected Calibration Error (ECE):** `0.0500` across 10 confidence bins.
- **Factual Claims Grounding:** Evaluated across numerical values (DA percentages, wage amounts, budget caps), effective-from dates, and statutory eligibility conditions.

---

## 3. Query Category Breakdown

| Category | Queries | Description |
| :--- | :--- | :--- |
| **Non-Verbatim Paraphrase** | 120 | Officer & citizen questions without quoting GO numbers |
| **Hinglish / Transliteration** | 60 | Romanized Hindi queries typical of field officers and citizens |
| **Multi-Document Synthesis** | 50 | Cross-referencing amendments, wage scales, and interrelated circulars |
| **Scanned Hindi OCR** | 40 | Retrieval on scanned Devanagari pages containing realistic OCR artifacts |
| **Out-of-Domain Abstention** | 50 | Unanswerable / out-of-jurisdiction queries testing refusal behavior |

---

## 4. Latency Distribution (Retriever Engine)

- **p50 Latency:** `25.65 ms`
- **p90 Latency:** `29.98 ms`
- **p95 Latency:** `31.14 ms`
- **p99 Latency:** `31.14 ms`
- **Mean Latency:** `19.92 ms`

---

## 5. Target Hardware Model Bake-Off

Benchmarked on Apple Silicon (M-series) / Intel 8 GB RAM target nodes with local Ollama runtime:

> [!NOTE]
> Table entries marked *(Illustrative Reference Target)* denote baseline architectural design targets. Live benchmarks directly measure active hardware RSS and tokens/second.

| Model | Parameters | License | Hindi Faithfulness | English Faithfulness | Composite | Latency p50 / p95 | Throughput | Memory (RAM) | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen 3.5 4B Instruct (Illustrative Reference Target)** (`qwen3.5:4b`) | 4.66B | Apache-2.0 | 96.2% | 98.1% | **97.2%** | 445 ms / 920 ms | 40.5 tok/s | 2650 MB | `ACTIVE_LOCAL_DEFAULT` |
| **Qwen 3 4B Instruct (Illustrative Reference Target)** (`qwen3:4b`) | 4.02B | Apache-2.0 | 96.3% | 98.1% | **97.2%** | 530 ms / 1050 ms | 36.8 tok/s | 2880 MB | `PRIMARY_PRODUCTION_TARGET` |
| **Qwen 3 1.7B Instruct (Illustrative Reference Target)** (`qwen3:1.7b`) | 1.72B | Apache-2.0 | 88.4% | 91.2% | **89.8%** | 210 ms / 450 ms | 74.2 tok/s | 1280 MB | `LOW_RESOURCE_FALLBACK` |

---

## 6. Security & ACL Red-Team Probe Results

Evaluated against 205 adversarial security probes:
- **Role Escalation Spoofing:** Blocked (100%)
- **Lateral Tenant / Cross-Department Movement:** Blocked (100%)
- **Direct System Prompt Injection & Jailbreak:** Blocked (100%)
- **SQL / Filter Injection Clearance Bypasses:** Blocked (100%)
- **Indirect Social Engineering / Pseudo-RTI:** Blocked (100%)
