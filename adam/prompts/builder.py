"""Composable PromptBuilder with XML boundary enforcement and multi-turn role structuring.

Enables fluent, type-safe construction of prompts incorporating governance
guardrails, evidence packets, deterministic calculation proofs, few-shot
exemplars, and automated critique feedback.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from adam.prompts.delimiters import PromptDelimiters, PromptSanitizer
from adam.prompts.few_shot import FewShotCatalog, FewShotExemplar
from adam.prompts.personas import AgentPersona, PersonaRegistry, PersonaRole
from adam.rag.models import EvidencePassage


class PromptBuilder:
    """Fluent, composable prompt constructor with XML container boundaries."""

    def __init__(self, persona: Optional[AgentPersona] = None):
        self.persona: AgentPersona = persona or PersonaRegistry.GOVERNED_RAG
        self.governance_rules: List[str] = []
        self.user_query: str = ""
        self.evidence_passages: List[EvidencePassage] = []
        self.external_passages: List[EvidencePassage] = []
        self.verified_calculations: List[Dict[str, Any]] = []
        self.precedent_notice: Optional[str] = None
        self.system_state_snapshot: Optional[str] = None
        self.few_shot_exemplars: List[FewShotExemplar] = []
        self.critique_feedback: Optional[str] = None
        self.output_instructions: Optional[str] = None
        self.execution_strategy: Optional[str] = None

    def with_persona(self, persona: AgentPersona) -> PromptBuilder:
        self.persona = persona
        return self

    def with_role(self, role: PersonaRole) -> PromptBuilder:
        self.persona = PersonaRegistry.get_persona(role)
        return self

    def with_governance_rules(self, rules: List[str]) -> PromptBuilder:
        self.governance_rules.extend(rules)
        return self

    def with_user_query(self, query: str) -> PromptBuilder:
        self.user_query = query.strip()
        return self

    def with_evidence(self, passages: List[EvidencePassage]) -> PromptBuilder:
        for p in passages:
            if getattr(p, "is_external", False):
                self.external_passages.append(p)
            else:
                self.evidence_passages.append(p)
        return self

    def with_calculations(self, calculations: List[Dict[str, Any]]) -> PromptBuilder:
        self.verified_calculations.extend(calculations)
        return self

    def with_precedent_notice(self, notice: Optional[str]) -> PromptBuilder:
        self.precedent_notice = notice
        return self

    def with_system_state(self, snapshot: Optional[str]) -> PromptBuilder:
        self.system_state_snapshot = snapshot
        return self

    def with_few_shot(self, exemplars: List[FewShotExemplar]) -> PromptBuilder:
        self.few_shot_exemplars.extend(exemplars)
        return self

    def with_few_shot_category(self, category: str) -> PromptBuilder:
        self.few_shot_exemplars.extend(FewShotCatalog.get_exemplars_for_category(category))
        return self

    def with_critique(self, critique: Optional[str]) -> PromptBuilder:
        self.critique_feedback = critique
        return self

    def with_execution_strategy(self, strategy: Optional[str]) -> PromptBuilder:
        self.execution_strategy = strategy
        return self

    def with_output_instructions(self, instructions: Optional[str]) -> PromptBuilder:
        self.output_instructions = instructions
        return self

    def build_system_prompt(self) -> str:
        """Compose the top-level system prompt with persona and governance rules."""
        base_prompt = self.persona.build_system_prompt(self.governance_rules)
        return base_prompt

    def build_user_prompt(self) -> str:
        """Compose the user prompt with securely delimited context blocks."""
        sections: List[str] = []

        # 1. Execution strategy / operational overview
        if self.execution_strategy:
            strategy_clean = PromptSanitizer.sanitize(self.execution_strategy)
            sections.append(f"Execution Strategy: {strategy_clean}\n")

        # 2. System Introspection Snapshot (if present)
        if self.system_state_snapshot:
            snap_clean = PromptSanitizer.sanitize(self.system_state_snapshot, escape_xml_tags=False)
            sections.append(
                f"=== AUTHORITATIVE SYSTEM STATE SNAPSHOT ===\n"
                f"{snap_clean}\n"
                f"===========================================\n"
            )

        # 3. Precedent / Currency Notice
        if self.precedent_notice:
            notice_clean = PromptSanitizer.sanitize(self.precedent_notice)
            sections.append(
                f"{PromptDelimiters.PRECECDENT_NOTICE_OPEN}\n"
                f"{notice_clean}\n"
                f"{PromptDelimiters.PRECECDENT_NOTICE_CLOSE}\n"
            )

        # 4. Verified Sandbox Calculations
        if self.verified_calculations:
            calc_lines = []
            for idx, c in enumerate(self.verified_calculations, start=1):
                val = c.get("formatted") or c.get("value")
                stdout = c.get("output", "").strip()
                stdout_str = f" | Output: {stdout}" if stdout else ""
                calc_lines.append(f"[{idx}] Result: {val}{stdout_str}")
            calcs_content = "\n".join(calc_lines)
            sections.append(
                f"{PromptDelimiters.VERIFIED_CALCULATIONS_OPEN}\n"
                f"{calcs_content}\n"
                f"{PromptDelimiters.VERIFIED_CALCULATIONS_CLOSE}\n"
            )

        # 5. Authoritative Local Evidence Passages
        if self.evidence_passages:
            evidence_blocks = []
            for idx, p in enumerate(self.evidence_passages, start=1):
                clean_content = PromptSanitizer.sanitize(p.content)
                go_attr = f' go_number="{p.go_number}"' if p.go_number else ""
                dept_attr = f' dept="{p.department_id}"' if p.department_id else ""
                passage_block = (
                    f'<evidence_passage id="{idx}" doc="{p.document_id}"{go_attr}{dept_attr}>\n'
                    f"{clean_content}\n"
                    f"</evidence_passage>"
                )
                evidence_blocks.append(passage_block)
            all_evidence = "\n\n".join(evidence_blocks)
            sections.append(
                f"{PromptDelimiters.APPROVED_EVIDENCE_OPEN}\n"
                f"{all_evidence}\n"
                f"{PromptDelimiters.APPROVED_EVIDENCE_CLOSE}\n"
            )

        # 6. External Web Findings
        if self.external_passages:
            ext_blocks = []
            for idx, p in enumerate(self.external_passages, start=1):
                clean_content = PromptSanitizer.sanitize(p.content)
                dom = getattr(p, "external_domain", "") or ""
                url = getattr(p, "external_url", "") or getattr(p, "source_url", "") or ""
                ext_block = (
                    f'<external_passage id="WEB-{idx}" title="{p.title}" domain="{dom}" url="{url}">\n'
                    f"{clean_content}\n"
                    f"</external_passage>"
                )
                ext_blocks.append(ext_block)
            all_ext = "\n\n".join(ext_blocks)
            sections.append(
                f"{PromptDelimiters.EXTERNAL_FINDINGS_OPEN}\n"
                f"{all_ext}\n"
                f"{PromptDelimiters.EXTERNAL_FINDINGS_CLOSE}\n"
            )

        # 7. Few-Shot Exemplars
        if self.few_shot_exemplars:
            few_shot_text = FewShotCatalog.format_exemplars(self.few_shot_exemplars)
            sections.append(
                f"{PromptDelimiters.FEW_SHOT_EXAMPLES_OPEN}\n"
                f"{few_shot_text}\n"
                f"{PromptDelimiters.FEW_SHOT_EXAMPLES_CLOSE}\n"
            )

        # 8. Critique Feedback (for self-correction turns)
        if self.critique_feedback:
            clean_critique = PromptSanitizer.sanitize(self.critique_feedback, escape_xml_tags=False)
            sections.append(
                f"{PromptDelimiters.CRITIQUE_FEEDBACK_OPEN}\n"
                f"{clean_critique}\n"
                f"{PromptDelimiters.CRITIQUE_FEEDBACK_CLOSE}\n"
            )

        # 9. Clean User Query
        clean_q = PromptSanitizer.sanitize(self.user_query)
        sections.append(
            f"{PromptDelimiters.USER_QUERY_OPEN}\n"
            f"{clean_q}\n"
            f"{PromptDelimiters.USER_QUERY_CLOSE}\n"
        )

        # 10. Output formatting instructions
        inst = self.output_instructions or (
            "Instructions:\n"
            "1. Synthesize a direct, authoritative, and strictly evidence-grounded response.\n"
            "2. Cite local public records using [1], [2] matching <evidence_passage id='...'>.\n"
            "3. Cite external web findings using [WEB-1], [WEB-2] matching <external_passage id='...'>.\n"
            "4. Incorporate verified mathematical calculations verbatim if present.\n"
            "5. If evidence is insufficient, state: 'I could not establish this from the approved repository.'\n"
            "6. Do NOT output chain-of-thought or raw thought markers."
        )
        sections.append(
            f"{PromptDelimiters.OUTPUT_FORMAT_OPEN}\n"
            f"{inst}\n"
            f"{PromptDelimiters.OUTPUT_FORMAT_CLOSE}"
        )

        return "\n".join(sections)

    def build_messages(self) -> List[Dict[str, str]]:
        """Produce standard OpenAI/Gemini/v1 compatible chat messages list."""
        return [
            {"role": "system", "content": self.build_system_prompt()},
            {"role": "user", "content": self.build_user_prompt()},
        ]
