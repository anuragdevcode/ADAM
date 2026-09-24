"""Administrative Few-Shot Exemplars for ADAM.

Provides realistic, verified few-shot examples of Uttarakhand Government Order
interpretations, financial calculations, superseded order reconciliation,
proper abstention, and bilingual Hindi administrative prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FewShotExemplar:
    """A verified input/output demonstration for in-context learning."""
    id: str
    title: str
    category: str  # financial_calculation, superseded_order, abstention, hindi_governance, high_risk
    user_query: str
    context_snippet: str
    exemplar_response: str
    learning_points: List[str]


class FewShotCatalog:
    """Curated collection of official administrative few-shot exemplars."""

    DA_CALCULATION_EXEMPLAR = FewShotExemplar(
        id="da_calc_7th_cpc",
        title="7th CPC Dearness Allowance Revision and Salary Increase Computation",
        category="financial_calculation",
        user_query="What is the revised DA rate for Uttarakhand state employees effective January 2024, and what is the monthly increase for an officer with a basic salary of ₹50,000?",
        context_snippet=(
            "Evidence Passage [1] (Doc: GO/FIN/2024/089, Dept: Finance):\n"
            "Government of Uttarakhand, Finance Department Order No. 89/XXVII(7)/2024 dated 15 March 2024. "
            "Subject: Revision of Dearness Allowance rates for State Government employees under 7th CPC. "
            "The Governor is pleased to sanction an increase in Dearness Allowance payable to State Government employees "
            "from the existing rate of 46% to 50% of Basic Pay with effect from 1st January 2024.\n"
            "Verified Calculations:\n"
            "Basic Pay: ₹50,000.00, Old DA (46%): ₹23,000.00, New DA (50%): ₹25,000.00, Monthly Increase (4%): ₹2,000.00"
        ),
        exemplar_response=(
            "As per Finance Department Government Order No. 89/XXVII(7)/2024 dated 15 March 2024 [1]:\n\n"
            "1. **Revised Rate:** The Dearness Allowance (DA) for Uttarakhand State Government employees under the 7th CPC "
            "has been increased from **46% to 50%** of Basic Pay [1].\n"
            "2. **Effective Date:** This revision is effective from **1st January 2024** [1].\n"
            "3. **Financial Impact for Basic Pay of ₹50,000:**\n"
            "   - **Old DA (46%):** ₹23,000.00 per month\n"
            "   - **New DA (50%):** ₹25,000.00 per month\n"
            "   - **Net Monthly Increase (4%):** **₹2,000.00** per month [1].\n"
            "   - **Revised Gross Salary (Basic + DA):** ₹75,000.00 per month."
        ),
        learning_points=[
            "Directly quotes the official GO number and date.",
            "Includes specific percentages (46% -> 50%) and effective date.",
            "Integrates verified mathematical calculations with clear currency formatting (₹).",
            "Cites [1] for all material facts.",
        ],
    )

    SUPERSEDED_ORDER_EXEMPLAR = FewShotExemplar(
        id="superseded_order_procurement",
        title="Superseded Procurement Limit Reconciliation with Currency Alert",
        category="superseded_order",
        user_query="What is the financial ceiling for direct procurement without tender under Uttarakhand Procurement Rules?",
        context_snippet=(
            "Evidence Passage [1] (Doc: GO/FIN/2018/104, Dept: Finance):\n"
            "GO No. 104/2018: Direct purchase of goods without quotation is permitted up to ₹25,000 per occasion.\n"
            "Evidence Passage [2] (Doc: GO/FIN/2023/312, Dept: Finance):\n"
            "GO No. 312/XXVII(2)/2023 dated 12 October 2023. In supersession of GO No. 104/2018, the Governor is pleased "
            "to enhance the limit for direct procurement of goods without quotation under Uttarakhand Procurement Rules to ₹50,000.\n"
            "Currency Notice: GO/FIN/2018/104 is SUPERSEDED by GO/FIN/2023/312."
        ),
        exemplar_response=(
            "> **Currency Notice:** Government Order No. 104/2018 has been superseded by GO No. 312/XXVII(2)/2023 [2].\n\n"
            "The current financial limit for direct procurement without quotations under the Uttarakhand Procurement Rules is **₹50,000** per occasion [2].\n\n"
            "- **Current Valid Provision:** GO No. 312/XXVII(2)/2023 dated 12 October 2023 enhanced this ceiling to ₹50,000 [2].\n"
            "- **Superseded Provision:** The previous limit of ₹25,000 under GO No. 104/2018 is no longer legally operational [1], [2]."
        ),
        learning_points=[
            "Displays prominent Currency Notice block.",
            "Explicitly differentiates between active/valid provision and historical superseded provision.",
            "Cites both old [1] and new [2] orders appropriately.",
        ],
    )

    PROPER_ABSTENTION_EXEMPLAR = FewShotExemplar(
        id="rigorous_abstention",
        title="Zero-Hallucination Rejection for Missing Repository Records",
        category="abstention",
        user_query="What are the specific guidelines for electric vehicle subsidy disbursement for commercial taxis issued by Uttarakhand Transport Department in August 2014?",
        context_snippet="(No evidence passages found in repository matching query criteria.)",
        exemplar_response=(
            "I could not establish this from the approved repository.\n\n"
            "The official repository does not contain records regarding electric vehicle subsidy guidelines for commercial taxis for August 2014.\n\n"
            "**Suggested Search Strategies:**\n"
            "- Verify whether the guidelines were issued under the Transport Department or the Energy/Renewable Energy Department (UREDA).\n"
            "- Search using the official scheme name or relevant policy notification year (e.g., Uttarakhand EV Policy 2018 onwards).\n"
            "- Check if a specific Government Order (GO) number is referenced in departmental correspondence."
        ),
        learning_points=[
            "Uses the mandatory zero-evidence formula verbatim: 'I could not establish this from the approved repository.'",
            "Zero hallucination of fictional order numbers, dates, or amounts.",
            "Offers actionable administrative search suggestions.",
        ],
    )

    HINDI_DEVANAGARI_EXEMPLAR = FewShotExemplar(
        id="hindi_devanagari_governance",
        title="Bilingual Administrative Response in Devanagari Script",
        category="hindi_governance",
        user_query="उत्तराखंड शासन द्वारा राजकीय कर्मचारियों के लिए अवकाश यात्रा सुविधा (LTC) के संबंध में क्या नियम हैं?",
        context_snippet=(
            "Evidence Passage [1] (Doc: GO/PERS/2021/415, Dept: Personnel):\n"
            "उत्तराखंड शासन, कार्मिक विभाग, शासनादेश संख्या 415/XXX(2)/2021 दिनांक 10 नवम्बर 2021। "
            "विषय: राज्य कर्मचारियों के लिए अवकाश यात्रा सुविधा (LTC) अनुमन्यता। "
            "सम्यक विचारोपरांत राज्यपाल महोदय 4 वर्ष के ब्लॉक (वर्तमान ब्लॉक 2022-2025) में एक बार गृह जनपद तथा एक बार अखिल भारतीय यात्रा हेतु "
            "अवकाश यात्रा सुविधा (LTC) स्वीकृत करने की सहर्ष स्वीकृति प्रदान करते हैं। इसके लिए न्यूनतम 1 वर्ष की निरंतर संतोषजनक सेवा अनिवार्य है।"
        ),
        exemplar_response=(
            "कार्मिक विभाग के शासनादेश संख्या 415/XXX(2)/2021 दिनांक 10 नवम्बर 2021 के अनुसार [1]:\n\n"
            "1. **LTC का ब्लॉक एवं आवृत्ति:** राज्य कर्मचारियों को **4 वर्ष के ब्लॉक** (वर्तमान ब्लॉक 2022-2025) में:\n"
            "   - एक बार गृह जनपद (Home Town) यात्रा, तथा\n"
            "   - एक बार अखिल भारतीय (All India) यात्रा की सुविधा अनुमन्य है [1]।\n"
            "2. **पात्रता की शर्त:** इस सुविधा का लाभ प्राप्त करने के लिए कर्मचारी की **न्यूनतम 1 वर्ष की निरंतर संतोषजनक सेवा** पूर्ण होना अनिवार्य है [1]।\n"
            "3. **सक्षम प्राधिकारी:** यह स्वीकृति संबंधित विभागाध्यक्ष अथवा नियुक्तिकर्ता प्राधिकारी द्वारा दी जाएगी [1]।"
        ),
        learning_points=[
            "Flawless Devanagari administrative prose conforming to Uttarakhand Secretariat standards.",
            "Correct use of formal terms: शासनादेश, अनुमन्यता, विभागाध्यक्ष, ब्लॉक.",
            "Strict citation mapping [1].",
        ],
    )

    HIGH_RISK_RESEARCH_BRIEF_EXEMPLAR = FewShotExemplar(
        id="high_risk_brief",
        title="Human Authority Required Administrative Research Brief",
        category="high_risk",
        user_query="Can the Additional Secretary sanction a budget re-appropriation of ₹5 Crore from Capital Outlay to Revenue Expenditure under Rule 27?",
        context_snippet=(
            "Evidence Passage [1] (Doc: FINANCIAL_HANDBOOK_VOL_V, Dept: Finance):\n"
            "Rule 27 of Financial Handbook Vol V (Part I): Re-appropriation of funds from Capital head to Revenue head "
            "is strictly beyond the competency of any subordinate authority and can only be sanctioned by the State Legislature "
            "or with express concurrence of the Finance Department subject to Governor's approval."
        ),
        exemplar_response=(
            "### Research Brief [Human Authority Required]\n\n"
            "> **Notice:** Human authority required. This research brief provides relevant repository records for "
            "administrative consideration. It is not a definitive legal or executive determination.\n\n"
            "**Query Topic:** Sanction of budget re-appropriation from Capital Outlay to Revenue Expenditure\n"
            "**Risk Category:** Financial Sanction & Delegation of Powers\n\n"
            "#### Relevant Repository Records & Provisions:\n"
            "- **[1] Financial Handbook Vol V (Part I) [Rule 27]:**\n"
            "  \"Re-appropriation of funds from Capital head to Revenue head is strictly beyond the competency of any subordinate authority "
            "and can only be sanctioned by the State Legislature or with express concurrence of the Finance Department subject to Governor's approval.\"\n\n"
            "#### Applicable Governance Status:\n"
            "- Current status as reflected in approved repository records.\n\n"
            "*Administrative Recommendation:* Submit this dossier to the Finance Department (Audit & Budget Section) "
            "and the competent Secretariat authority for formal administrative review and legal determination."
        ),
        learning_points=[
            "Enforces mandatory disclaimer banner: 'Human authority required'.",
            "Neutral, objective synthesis without making unauthorized executive determinations.",
            "Recommends formal routing to the competent constitutional/secretariat authority.",
        ],
    )

    @classmethod
    def get_exemplars_for_category(cls, category: str) -> List[FewShotExemplar]:
        """Retrieve exemplars matching a specific task category."""
        all_exemplars = [
            cls.DA_CALCULATION_EXEMPLAR,
            cls.SUPERSEDED_ORDER_EXEMPLAR,
            cls.PROPER_ABSTENTION_EXEMPLAR,
            cls.HINDI_DEVANAGARI_EXEMPLAR,
            cls.HIGH_RISK_RESEARCH_BRIEF_EXEMPLAR,
        ]
        return [e for e in all_exemplars if e.category == category]

    @classmethod
    def format_exemplars(cls, exemplars: List[FewShotExemplar]) -> str:
        """Format a list of exemplars into a prompt-ready markdown string."""
        blocks: List[str] = []
        for idx, ex in enumerate(exemplars, start=1):
            block = (
                f"### Example {idx}: {ex.title}\n"
                f"**User Query:** {ex.user_query}\n\n"
                f"**Provided Evidence Context:**\n{ex.context_snippet}\n\n"
                f"**Expected Authoritative Response:**\n{ex.exemplar_response}\n"
            )
            blocks.append(block)
        return "\n---\n".join(blocks)
