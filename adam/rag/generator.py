"""Generator and Citation Validator with strict hallucination controls.

Per Phase 03 specification:
- 'Generator may use only that packet.'
- 'A citation validator checks that every material claim maps to one or more passages.'
- Hallucination controls:
  - No evidence -> answer: "I could not establish this from the approved repository," followed by search suggestions.
  - Require direct citations for dates, money, rule numbers, authorities, obligations, exceptions and legal conclusions.
  - Do not answer from model memory; retrieved public evidence is mandatory even for common facts.
  - Quote minimally, paraphrase clearly, label conflicts, and offer the original document.
  - High-risk prompts (legal advice, sanction approval, eligibility, disciplinary action) produce a
    research brief with "human authority required," never a definitive determination.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set

from adam.rag.citation import CitationBuilder
from adam.rag.models import (
    Citation,
    EvidencePacket,
    EvidencePassage,
    RagResponse,
)


class CitationValidator:
    """Checks that every material claim in the answer maps to one or more evidence passages."""

    # Patterns for material claims requiring mandatory substantiation
    CLAIM_PATTERNS = {
        "DATE": re.compile(
            r"\b(?:\d{1,2}[\.\-\/]\d{1,2}[\.\-\/]\d{4}|\d{4}-\d{2}-\d{2}|"
            r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|"
            r"\d{1,2}\s+(?:जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितम्बर|सितंबर|अक्टूबर|अक्तूबर|नवम्बर|नवंबर|दिसम्बर|दिसंबर)\s+\d{4})\b",
            re.IGNORECASE | re.UNICODE,
        ),
        "MONEY_AMOUNT": re.compile(
            r"(?:(?:Rs\.?|₹|INR)\s*[\d,]+(?:\.\d+)?|\b[\d,]+\s*(?:रुपये|रु०|लाख|करोड़|lakh|crore)\b|\b\d+(?:\.\d+)?%)",
            re.IGNORECASE | re.UNICODE,
        ),
        "RULE_OR_GO_NUMBER": re.compile(
            r"(?:Rule\s+\d+[A-Za-z\(\)]*|Section\s+\d+[A-Za-z\(\)]*|नियम\s+\d+|धारा\s+\d+|"
            r"(?:UK|GO|FIN|RD|AUD|BOR)\/[A-Za-z0-9\/\-\._]{3,30}|\b\d+\/\S+\/\d{4}\b)",
            re.IGNORECASE | re.UNICODE,
        ),
        "AUTHORITY": re.compile(
            r"\b(?:Governor|Additional Chief Secretary|Departmental Secretary|Head of Department|District Magistrate|"
            r"राज्यपाल|अपर मुख्य सचिव|सचिव|विभागाध्यक्ष|जिलाधिकारी|निदेशक)\b",
            re.IGNORECASE | re.UNICODE,
        ),
    }

    @classmethod
    def extract_material_claims(cls, answer: str) -> List[Tuple[str, str]]:
        """Extract tuples of (claim_type, claim_text) from answer."""
        claims: List[Tuple[str, str]] = []
        for claim_type, pattern in cls.CLAIM_PATTERNS.items():
            matches = pattern.findall(answer)
            for m in matches:
                clean_m = m.strip() if isinstance(m, str) else m[0].strip()
                if clean_m and len(clean_m) > 1:
                    claims.append((claim_type, clean_m))
        return claims

    @classmethod
    def validate(
        cls,
        answer: str,
        packet: EvidencePacket,
        verified_calculations: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, List[str]]:
        """Verify that every material claim in the answer is grounded in the evidence packet or verified calculations."""
        if not answer:
            return True, []

        claims = cls.extract_material_claims(answer)
        if not claims:
            return True, []

        calc_context = ""
        if verified_calculations:
            calc_context = " ".join(
                str(c.get("value") or "") + " " + str(c.get("output") or "")
                for c in verified_calculations
                if isinstance(c, dict)
            )

        extra_context = " ".join([
            packet.currency_banner or "",
            calc_context,
            " ".join(str(p.order_date or "") for p in packet.passages),
            " ".join(str(p.effective_from or "") for p in packet.passages),
            " ".join(str(p.effective_to or "") for p in packet.passages),
        ]).lower()
        corpus_text = (" ".join(p.content + " " + (p.go_number or "") for p in packet.passages).lower() + " " + extra_context)
        errors: List[str] = []

        for claim_type, claim_val in claims:
            c_norm = claim_val.lower().strip()

            # Date normalization check
            is_grounded = c_norm in corpus_text

            # Numeric/currency/date check: verify the numbers appear in the corpus or calculation results
            if not is_grounded and claim_type in ("MONEY_AMOUNT", "RULE_OR_GO_NUMBER", "DATE"):
                digits = re.findall(r"\d+", claim_val)
                if digits and all(d in corpus_text for d in digits):
                    is_grounded = True

            if not is_grounded:
                errors.append(
                    f"Material claim [{claim_type}: '{claim_val}'] not found in retrieved evidence passages."
                )

        passed = len(errors) == 0
        return passed, errors


class RagGenerator:
    """Generates strictly evidence-grounded answers with hallucination controls."""

    NO_EVIDENCE_REFUSAL = "I could not establish this from the approved repository."

    SEARCH_SUGGESTIONS = [
        "Verify that the query pertains to official Uttarakhand State records.",
        "Include the specific Department name (e.g., Finance/Treasury, Rural Development, Audit).",
        "Search by explicit Government Order (GO) number (e.g., 'GO/2024/101') or gazette notification.",
        "Check that the applicable year or date is correctly formatted (e.g., '2024' or '15/01/2024').",
    ]

    def __init__(self, validator: Optional[CitationValidator] = None):
        self.validator = validator or CitationValidator()

    def generate(self, packet: EvidencePacket) -> RagResponse:
        """Produce answer and citations strictly bounded by the evidence packet."""
        # 1. Hallucination Control: Zero evidence refusal
        if packet.is_empty or not packet.passages:
            return RagResponse(
                answer=self.NO_EVIDENCE_REFUSAL,
                citations=[],
                evidence_packet=packet,
                is_no_answer=True,
                is_high_risk=packet.query.is_high_risk,
                search_suggestions=self.SEARCH_SUGGESTIONS,
            )

        # 2. Build citations
        citations = CitationBuilder.build_citations_from_packet(packet)
        currency_banners = []
        if packet.currency_banner:
            currency_banners.append(packet.currency_banner)

        # 3. High-Risk Prompt Handling: Produce Research Brief with "human authority required"
        if packet.query.is_high_risk:
            return self._generate_research_brief(packet, citations, currency_banners)

        # 4. Standard Generation
        answer = self._synthesize_answer(packet, citations)

        # 5. Citation Validation
        passed, errors = self.validator.validate(answer, packet)

        return RagResponse(
            answer=answer,
            citations=citations,
            evidence_packet=packet,
            currency_banners=currency_banners,
            is_no_answer=False,
            is_high_risk=False,
            is_research_brief=False,
            validation_passed=passed,
            validation_errors=errors,
            search_suggestions=[],
        )

    def _generate_research_brief(
        self,
        packet: EvidencePacket,
        citations: List[Citation],
        currency_banners: List[str],
    ) -> RagResponse:
        """Generate an administrative research brief for high-risk queries."""
        category = packet.query.high_risk_category or "ADMINISTRATIVE_DECISION"
        header = (
            "### Research Brief [Human Authority Required]\n\n"
            "> **Notice:** Human authority required. This research brief provides relevant repository records "
            "for administrative consideration. It is not a definitive legal or executive determination.\n\n"
            f"**Query Topic:** {packet.query.clean_query}\n"
            f"**Risk Category:** {category.replace('_', ' ').title()}\n\n"
            "#### Relevant Repository Records & Provisions:\n"
        )

        provisions: List[str] = []
        for idx, p in enumerate(packet.passages[:4], 1):
            title = p.title
            page_str = f"Page {p.page_start}"
            go_str = f" (GO: {p.go_number})" if p.go_number else ""
            summary_sentence = p.content.split("\n")[0][:300]
            provisions.append(f"- **[{idx}] {title}**{go_str} [{page_str}]:\n  \"{summary_sentence}\"")

        body = "\n".join(provisions)

        footer = "\n\n#### Applicable Governance Status:\n"
        if currency_banners:
            footer += f"- **Currency Alert:** {currency_banners[0]}\n"
        else:
            footer += "- Current status as reflected in approved repository records.\n"

        footer += (
            "\n*Administrative Recommendation:* Submit this dossier to the competent departmental authority "
            "for formal review and determination."
        )

        full_answer = header + body + footer
        passed, errors = self.validator.validate(full_answer, packet)

        return RagResponse(
            answer=full_answer,
            citations=citations,
            evidence_packet=packet,
            currency_banners=currency_banners,
            is_no_answer=False,
            is_high_risk=True,
            is_research_brief=True,
            validation_passed=passed,
            validation_errors=errors,
            search_suggestions=[],
        )

    def _synthesize_answer(
        self,
        packet: EvidencePacket,
        citations: List[Citation],
    ) -> str:
        """Synthesize answer strictly from evidence passages with conflict labeling and citations."""
        sections: List[str] = []

        # Conflict labeling if conflicting provisions exist in evidence packet (deduplicated)
        if packet.conflicts:
            conflict_notes = []
            seen_notes = set()
            for c in packet.conflicts:
                note = c.get("notes")
                if not note and c.get("conflict_type") == "RATE_DISCREPANCY":
                    note = (
                        f"Discrepancy noted regarding {c.get('entity')}: {c.get('first_order')} specifies {c.get('first_val')}, "
                        f"whereas {c.get('second_order')} specifies {c.get('second_val')}."
                    )
                if note and note not in seen_notes:
                    seen_notes.add(note)
                    conflict_notes.append(note)
            if conflict_notes:
                sections.append(
                    "**Notice of Conflicting / Superseded Provisions:**\n"
                    + "\n".join(f"- {note}" for note in conflict_notes)
                )

        # Primary evidence synthesis
        answer_parts: List[str] = []
        for idx, p in enumerate(packet.passages[:4], 1):
            lines = [l.strip() for l in p.content.split("\n") if l.strip()]
            # Filter out bureaucratic letterhead metadata lines
            substantive_lines = []
            for line in lines:
                if re.match(r"^(?:GOVERNMENT OF|उत्तराखण्ड शासन|Directorate of|निदेशालय|राजस्व परिषद|General Administration|Rural Development)", line, re.IGNORECASE):
                    continue
                if re.match(r"^(?:Order No|शासनादेश संख्या|अधिसूचना संख्या|Document Ref)\s*[:\-]", line, re.IGNORECASE):
                    continue
                substantive_lines.append(line)

            substance = " ".join(substantive_lines) if substantive_lines else " ".join(lines)

            # Historical / supersession context labeling
            prefix = ""
            if p.is_superseding or p.currency_status == "SUPERSEDES":
                prefix = f"Under order {p.go_number or p.title} (superseding order): "
            elif p.currency_status in ("AMENDED", "SUPERSEDED"):
                prefix = f"Under previous order {p.go_number or p.title}: "

            answer_parts.append(
                f"{prefix}{substance} [{idx}]"
            )

        sections.append("\n\n".join(answer_parts))

        # Add currency banner if uncertain or amended
        if packet.currency_banner:
            sections.append(f"\n*Currency Status: {packet.currency_banner}*")

        return "\n\n".join(sections)
