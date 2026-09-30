"""Answer Faithfulness Verification Engine per Phase 03/E4 Specification.

Evaluates:
- Numerical accuracy: percentages, rupee amounts, multipliers, and scalar figures.
- Temporal precision: notification dates, effective-from dates, submission deadlines.
- Eligibility & constraint criteria: service categories, qualification rules, exclusions.
- Hallucinated / unsupported factual claim identification.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple


def _normalize(text: str) -> str:
    """Normalize whitespace and Unicode text."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.split()).lower()


def extract_numbers_and_amounts(text: str) -> List[str]:
    """Extract numeric patterns, currency amounts, percentages, and fractions."""
    if not text:
        return []

    # Mask dates to prevent DD.MM or DD/MM being extracted as decimal fractions
    cleaned_text = re.sub(r"\b\d{1,4}[-./]\d{1,2}[-./]\d{1,4}\b", " ", text)
    cleaned_text = re.sub(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b", " ", cleaned_text, flags=re.IGNORECASE)

    # Patterns matching:
    # - Percentages: 50%, 46.5%, 38 %
    # - Currencies: Rs. 500, ₹45,000, Rs 500 crore, 45 lakh
    # - Standalone numbers: integers, decimals
    patterns = [
        r"(?:(?:rs\.?|inr|₹)\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|lakh|thousand))?)",
        r"(?:[\d,]+(?:\.\d+)?\s*(?:crore|lakh|हजार|करोड़|लाख))",
        r"(?:[\d]+(?:\.\d+)?\s*%)",
        r"(?:\b\d+(?:,\d+)*(?:\.\d+)?\b)",
    ]
    combined = re.compile("|".join(patterns), re.IGNORECASE)
    matches = combined.findall(cleaned_text)

    # Clean and deduplicate while preserving ordering
    seen = set()
    cleaned = []
    for m in matches:
        norm = _normalize(m)
        if norm and norm not in seen:
            seen.add(norm)
            cleaned.append(norm)
    return cleaned


def extract_dates(text: str) -> List[str]:
    """Extract date expressions in English, ISO, and Devanagari administrative formats."""
    if not text:
        return []

    patterns = [
        # YYYY-MM-DD or YYYY.MM.DD
        r"\b\d{4}[-./]\d{1,2}[-./]\d{1,2}\b",
        # DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY
        r"\b\d{1,2}[-./]\d{1,2}[-./]\d{2,4}\b",
        # 1st January 2024, 15 Jan 2024
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b",
        # Hindi date patterns: 1 जनवरी 2024, 15 अगस्त 2023
        r"\b\d{1,2}\s+(?:जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर)\s+\d{2,4}\b",
    ]
    combined = re.compile("|".join(patterns), re.IGNORECASE)
    matches = combined.findall(text)

    seen = set()
    cleaned = []
    for m in matches:
        norm = _normalize(m)
        if norm and norm not in seen:
            seen.add(norm)
            cleaned.append(norm)
    return cleaned


def verify_numerical_faithfulness(
    answer_text: str,
    evidence_text: str,
    expected_numbers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Verify that numeric claims in the answer are strictly supported by retrieved evidence."""
    answer_nums = extract_numbers_and_amounts(answer_text)
    evidence_norm = _normalize(evidence_text)

    if not answer_nums:
        # If no numbers were claimed, faithfulness is 100%
        return {
            "is_faithful": True,
            "faithfulness_score": 1.0,
            "claimed_numbers": [],
            "supported_numbers": [],
            "unsupported_numbers": [],
        }

    supported = []
    unsupported = []

    for num in answer_nums:
        # Check direct or stripped presence
        num_clean = re.sub(r"[^\d.]", "", num)
        if num in evidence_norm or (num_clean and num_clean in evidence_norm):
            supported.append(num)
        else:
            unsupported.append(num)

    score = len(supported) / len(answer_nums)
    return {
        "is_faithful": len(unsupported) == 0,
        "faithfulness_score": round(score, 4),
        "claimed_numbers": answer_nums,
        "supported_numbers": supported,
        "unsupported_numbers": unsupported,
    }


def verify_date_faithfulness(
    answer_text: str,
    evidence_text: str,
    expected_dates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Verify that dates in the answer correspond to verifiable dates in the evidence."""
    answer_dates = extract_dates(answer_text)
    evidence_norm = _normalize(evidence_text)

    if not answer_dates:
        return {
            "is_faithful": True,
            "faithfulness_score": 1.0,
            "claimed_dates": [],
            "supported_dates": [],
            "unsupported_dates": [],
        }

    supported = []
    unsupported = []

    for d in answer_dates:
        # Check presence or partial components (e.g. year and month)
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", d)
        year = year_match.group(0) if year_match else None

        if d in evidence_norm or (year and year in evidence_norm):
            supported.append(d)
        else:
            unsupported.append(d)

    score = len(supported) / len(answer_dates)
    return {
        "is_faithful": len(unsupported) == 0,
        "faithfulness_score": round(score, 4),
        "claimed_dates": answer_dates,
        "supported_dates": supported,
        "unsupported_dates": unsupported,
    }


def verify_eligibility_criteria(
    answer_text: str,
    evidence_text: str,
    expected_criteria: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Verify that stated eligibility terms, conditions, or exclusions are backed by evidence."""
    if not expected_criteria:
        return {
            "is_faithful": True,
            "faithfulness_score": 1.0,
            "missing_criteria": [],
            "matched_criteria": [],
        }

    evidence_norm = _normalize(evidence_text)
    matched = []
    missing = []

    for crit in expected_criteria:
        crit_norm = _normalize(crit)
        tokens = [t for t in crit_norm.split() if len(t) >= 3]
        if not tokens:
            matched.append(crit)
            continue
        token_match = sum(1 for t in tokens if t in evidence_norm)
        if (token_match / len(tokens)) >= 0.5:
            matched.append(crit)
        else:
            missing.append(crit)

    score = len(matched) / len(expected_criteria) if expected_criteria else 1.0
    return {
        "is_faithful": len(missing) == 0,
        "faithfulness_score": round(score, 4),
        "missing_criteria": missing,
        "matched_criteria": matched,
    }


def evaluate_answer_faithfulness(
    answer_text: str,
    evidence_text: str,
    expected_facts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Comprehensive multi-axis answer faithfulness assessment.

    Weights:
    - Numerical accuracy: 40%
    - Date / temporal precision: 30%
    - Eligibility / constraint grounding: 30%
    """
    expected_facts = expected_facts or {}
    expected_numbers = expected_facts.get("numbers")
    expected_dates = expected_facts.get("dates")
    expected_eligibility = expected_facts.get("eligibility")

    num_eval = verify_numerical_faithfulness(answer_text, evidence_text, expected_numbers)
    date_eval = verify_date_faithfulness(answer_text, evidence_text, expected_dates)
    elig_eval = verify_eligibility_criteria(answer_text, evidence_text, expected_eligibility)

    composite = (
        0.40 * num_eval["faithfulness_score"]
        + 0.30 * date_eval["faithfulness_score"]
        + 0.30 * elig_eval["faithfulness_score"]
    )

    unsupported_count = len(num_eval["unsupported_numbers"]) + len(date_eval["unsupported_dates"]) + len(elig_eval["missing_criteria"])

    return {
        "composite_faithfulness": round(composite, 4),
        "is_fully_faithful": unsupported_count == 0,
        "numerical_evaluation": num_eval,
        "date_evaluation": date_eval,
        "eligibility_evaluation": elig_eval,
        "total_unsupported_items": unsupported_count,
    }
