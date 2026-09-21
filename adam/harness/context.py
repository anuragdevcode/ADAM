"""Context formatting strategies for evidence presentation to language models.

Optimizes evidence presentation to avoid prompt inundation, repetitive metadata
noise, and forced citation hallucinations on small models (1.7B-4B).
"""

from __future__ import annotations

import re
from typing import List, Optional, Any, Dict
from adam.rag.models import EvidencePacket, EvidencePassage


class ContextStrategy:
    """Methods to format retrieved evidence into model-digestible text blocks."""

    @staticmethod
    def clean_passage_content(content: str, max_chars: int = 600) -> str:
        """Strip bureaucratic letterhead, repeated gazette headers, and noise."""
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        substantive_lines = []
        for line in lines:
            # Skip formal letterhead banners
            if re.match(
                r"^(?:GOVERNMENT OF|उत्तराखण्ड शासन|Directorate of|निदेशालय|राजस्व परिषद|General Administration|Rural Development)\b",
                line,
                re.IGNORECASE,
            ):
                continue
            if re.match(
                r"^(?:Order No|शासनादेश संख्या|अधिसूचना संख्या|Document Ref)\s*[:\-]",
                line,
                re.IGNORECASE,
            ):
                continue
            substantive_lines.append(line)

        cleaned = " ".join(substantive_lines) if substantive_lines else " ".join(lines)
        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rsplit(" ", 1)[0] + "..."
        return cleaned

    @classmethod
    def format_compact_evidence(
        cls,
        passages: List[EvidencePassage],
        max_passages: int = 4,
    ) -> str:
        """Render high-salience numbered passages avoiding redundant metadata."""
        if not passages:
            return "No official records available."

        blocks = []
        for idx, p in enumerate(passages[:max_passages], 1):
            clean_text = cls.clean_passage_content(p.content)
            title = p.title or "Uttarakhand Official Record"
            go_info = f" (GO: {p.go_number})" if p.go_number else ""
            page_info = f", Page {p.page_start}" if p.page_start else ""
            
            blocks.append(
                f"Passage [{idx}] [{title}{go_info}{page_info}]:\n{clean_text}"
            )

        return "\n\n".join(blocks)

    @classmethod
    def build_grounded_rag_prompt(
        cls,
        query: str,
        packet: EvidencePacket,
        max_passages: int = 4,
    ) -> str:
        """Create a clear grounded prompt that does not force all citations.

        Explicitly instructs the model to cite only relevant passages, preventing
        false citation inclusion of unneeded passages.
        """
        evidence_text = cls.format_compact_evidence(packet.passages, max_passages=max_passages)

        prompt = (
            f"Reference Records:\n"
            f"{evidence_text}\n\n"
            f"User Question: {query}\n\n"
            f"Instructions: Provide an accurate, clear answer strictly based on the reference records above. "
            f"Include exact citations like [1] or [2] only for the passages directly supporting each fact. "
            f"If the records do not contain the answer, state that you could not establish this from the approved repository."
        )
        return prompt
