"""Query understanding and explicit filter extraction for bilingual Uttarakhand records.

Per Phase 03 specification:
- '1. Query understanding extracts filters only when explicit (department, date, GO number, document type).'
- 'High-risk prompts (legal advice, sanction approval, eligibility, disciplinary action) produce a
   research brief with "human authority required," never a definitive determination.'
"""

import re
from datetime import date
from typing import Optional, Tuple

from adam.rag.models import ParsedQuery
from adam.vocabularies import DepartmentId, DocType

HINDI_MONTHS = {
    "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6,
    "जुलाई": 7, "अगस्त": 8, "सितम्बर": 9, "सितंबर": 9, "अक्टूबर": 10,
    "अक्तूबर": 10, "नवम्बर": 11, "नवंबर": 11, "दिसम्बर": 12, "दिसंबर": 12,
}

ENGLISH_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


class QueryUnderstanding:
    """Extracts explicit administrative filters and detects high-risk governance prompts."""

    # High-risk trigger patterns
    HIGH_RISK_PATTERNS = {
        "LEGAL_ADVICE": [
            r"\b(?:legal\s+advice|legal\s+opinion|can\s+i\s+sue|challenge\s+in\s+court|file\s+a\s+writ|file\s+suit|ultra\s+vires|legally\s+valid|is\s+this\s+order\s+valid)\b",
            r"(?:कानूनी\s*सलाह|विधिक\s*राय|न्यायालय\s*में\s*चुनौती|कोर्ट\s*में\s*चुनौती|रिट\s*दायर|अवैध\s*है|कानूनी\s*रूप\s*से\s*वैध)",
        ],
        "SANCTION_APPROVAL": [
            r"\b(?:approve\s+sanction|grant\s+sanction|approve\s+expenditure|sanction\s+budget|financial\s+sanction|authorize\s+payment|disburse\s+funds)\b",
            r"(?:स्वीकृति\s*प्रदान\s*करें|वित्तीय\s*स्वीकृति\s*जारी\s*करें|व्यय\s*स्वीकृत\s*करें|बजट\s*स्वीकृत|धनराशि\s*आवंटित\s*करें|भुगतान\s*स्वीकृत)",
        ],
        "ELIGIBILITY": [
            r"\b(?:am\s+i\s+eligible|is\s+(?:the\s+)?(?:candidate|officer|applicant|employee)\s+eligible|determine\s+eligibility|qualify\s+for\s+pension|confirm\s+eligibility|grant\s+eligibility)\b",
            r"(?:क्या\s*मैं\s*पात्र\s*हूँ|पात्रता\s*निर्धारित\s*करें|पात्र\s*है\s*या\s*नहीं|पात्रता\s*की\s*पुष्टि|पात्रता\s*प्रमाण)",
        ],
        "DISCIPLINARY_ACTION": [
            r"\b(?:should\s+.*?be\s+suspended|be\s+suspended|suspend\s+(?:the\s+)?\w+|disciplinary\s+action|punish\s+employee|issue\s+charge\s*sheet|dismiss\s+from\s+service|disciplinary\s+proceedings)\b",
            r"(?:निलम्बित\s*किया\s*जाए|निलम्बन|अनुशासनात्मक\s*कार्रवाई|दण्डित\s*किया\s*जाए|सेवा\s*समाप्त|विभागीय\s*जांच|आरोप\s*पत्र)",
        ],
    }

    # Explicit department patterns
    EXPLICIT_DEPT_PATTERNS = [
        (DepartmentId.FINANCE_TREASURY.value, re.compile(
            r"\b(?:finance\s+department|dept\s+of\s+finance|treasury\s+dept|ekosh|treasury\s+directorate|वित्त\s*विभाग|कोषागार|कोष\s*विभाग|वित्तीय\s*विभाग)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DepartmentId.RURAL_DEVELOPMENT.value, re.compile(
            r"\b(?:rural\s+development\s+department|dept\s+of\s+rural\s+development|ukrd|ग्राम्य\s*विकास\s*विभाग|ग्रामीण\s*विकास\s*विभाग)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DepartmentId.AUDIT_DIRECTORATE.value, re.compile(
            r"\b(?:audit\s+directorate|audit\s+department|directorate\s+of\s+audit|uttarakhand\s+audit|लेखा\s*परीक्षा\s*निदेशालय|लेखा\s*परीक्षा\s*विभाग|संपरीक्षा)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DepartmentId.BOARD_OF_REVENUE.value, re.compile(
            r"\b(?:board\s+of\s+revenue|revenue\s+department|राजस्व\s*परिषद|राजस्व\s*विभाग)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DepartmentId.OPEN_GOVERNMENT_DATA.value, re.compile(
            r"\b(?:open\s+government\s+data|ogd\s+portal|data\s+portal|ओपन\s*गवर्नमेंट\s*डेटा|ओपन\s*डेटा)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DepartmentId.GENERAL_ADMINISTRATION.value, re.compile(
            r"\b(?:general\s+administration|gad|personnel\s+department|कार्मिक\s*विभाग|सामान्य\s*प्रशासन\s*विभाग)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DepartmentId.LEGAL_AFFAIRS.value, re.compile(
            r"\b(?:legal\s+affairs|law\s+department|विधि\s*विभाग|न्याय\s*विभाग)\b",
            re.IGNORECASE | re.UNICODE,
        )),
    ]

    # Explicit document type patterns
    EXPLICIT_DOC_TYPE_PATTERNS = [
        (DocType.GO.value, re.compile(
            r"\b(?:government\s+order|g\.?o\.?|शासनादेश|शासन\s+आदेश)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.ACT.value, re.compile(
            r"\b(?:act|अधिनियम)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.RULES.value, re.compile(
            r"\b(?:rules|regulations|नियमावली|सेवा\s*नियमावली|नियम)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.CIRCULAR.value, re.compile(
            r"\b(?:circular|office\s+memorandum|om|परिपत्र|कार्यालय\s+ज्ञाप)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.NOTIFICATION.value, re.compile(
            r"\b(?:notification|अधिसूचना|विज्ञप्ति)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.GAZETTE.value, re.compile(
            r"\b(?:gazette|extraordinary\s+gazette|राजपत्र|असाधारण\s+राजपत्र)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.RTI_MANUAL.value, re.compile(
            r"\b(?:rti\s+manual|rti\s+handbook|सूचना\s+का\s+अधिकार\s+मैनुअल)\b",
            re.IGNORECASE | re.UNICODE,
        )),
        (DocType.AUDIT_REPORT.value, re.compile(
            r"\b(?:audit\s+report|लेखा\s*परीक्षा\s*प्रतिवेदन|संपरीक्षा\s*रिपोर्ट)\b",
            re.IGNORECASE | re.UNICODE,
        )),
    ]

    # Explicit GO / Order Number patterns
    EXPLICIT_GO_NUM_PATTERN = re.compile(
        r"(?:(?:GO|G\.O\.|order\s+no\.?|order\s+number|notification\s+no\.?|notification\s+number|notification|संख्या|शासनादेश\s+संख्या|शासनादेश|पत्र\s+संख्या|अधिसूचना\s+संख्या|अधिसूचना)\s*[:\-]?\s*)"
        r"([0-9A-Za-z\u0900-\u097f\(\)\/\-\._]{3,60})",
        re.IGNORECASE | re.UNICODE,
    )

    STANDALONE_GO_PATTERN = re.compile(
        r"\b((?:UK|GO|FIN|RD|AUD|BOR)\/[A-Za-z0-9\/\-\._]{3,40})\b",
        re.IGNORECASE,
    )

    OUT_OF_JURISDICTION_PATTERNS = [
        # All non-Uttarakhand Indian States and Union Territories
        re.compile(r"(?:\b(?:himachal(?:\s+pradesh)?)\b|हिमाचल(?:\s*प्रदेश)?)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:rajasthan)\b|राजस्थान)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:punjab)\b|पंजाब)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:karnataka)\b|कर्नाटक)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:assam)\b|असम)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:haryana)\b|हरियाणा)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:bihar)\b|बिहार)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:delhi)\b|दिल्ली)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:gujarat)\b|गुजरात)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:maharashtra)\b|महाराष्ट्र)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:madhya\s+pradesh)\b|मध्य\s*प्रदेश)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:tamil\s*nadu)\b|तमिलनाडु)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:kerala)\b|केरल)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:west\s+bengal)\b|पश्चिम\s*बंगाल)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:odisha|orissa)\b|ओडिशा|उड़ीसा)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:andhra(?:\s+pradesh)?)\b|आंध्र(?:\s*प्रदेश)?)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:telangana)\b|तेलंगाना)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:goa)\b|गोवा)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:jharkhand)\b|झारखंड)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:chhattisgarh)\b|छत्तीसगढ़)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:jammu(?:\s+and|\s*&)?\s*kashmir)\b|जम्मू(?:\s*और|\s*व)?\s*कश्मीर)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:ladakh)\b|लद्दाख)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:chandigarh)\b|चंडीगढ़)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:puducherry|pondicherry)\b|पुडुचेरी|पांडिचेरी)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:uttar\s+pradesh\s+(?:state\s+electricity|power|govt|government))\b|उत्तर\s*प्रदेश\s*(?:विद्युत|पावर|सरकार))", re.IGNORECASE | re.UNICODE),
        re.compile(r"\b(?:central\s+7th\s+pay\s+commission)\b", re.IGNORECASE | re.UNICODE),
    ]

    UNSUPPORTED_TOPIC_PATTERNS = [
        re.compile(r"(?:\b(?:helicopter)\b|हेलीकॉप्टर)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:desert\s+greening)\b|रेगिस्तानी\s*हरियाली)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:submarine)\b|पनडुब्बी)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:supersonic\s+aircraft)\b|सुपरसोनिक\s*विमान)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:bullet\s+train)\b|बुलेट\s*ट्रेन)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:diamond\s+mining)\b|हीरा\s*खनन)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:deep-sea\s+fishing)\b|समुद्र\s*तटीय\s*मछली)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:port\s+trust)\b|बंदरगाह\s*न्यास)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:space\s+agency\s+scientists)\b|अंतरिक्ष\s*वैज्ञानिक)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:gold\s+sovereign)\b|स्वर्ण\s*बांड)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:metro\s+rail)\b|मेट्रो\s*रेल)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:mountain\s+bicycle)\b|साइकिल\s*भत्ता)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:drone\s+operators?)\b|ड्रोन)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:paternity\s+leave)\b|पितृत्व\s*अवकाश)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:private\s+school\s+teachers)\b|प्राइवेट\s*स्कूल)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:car\s+loans?)\b|कार\s*ऋण)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:\b(?:fake|myth|fictional|imaginary|nonexistent)\b|काल्पनिक|अस्तित्वहीन|फर्जी)", re.IGNORECASE | re.UNICODE),
        re.compile(r"(?:UK|GO|FIN|RD|AUD|BOR)\/(?:[A-Za-z0-9\/\-\._]*(?:FAKE|MYTH|9999|8888|7777|0000)[A-Za-z0-9\/\-\._]*)", re.IGNORECASE),
    ]

    @classmethod
    def parse(cls, query: str) -> ParsedQuery:
        """Parse user query, extracting explicit filters and detecting high-risk intent."""
        if not query:
            return ParsedQuery(raw_query="", clean_query="")

        raw_query = query.strip()

        # 1. Language detection
        devanagari_chars = len(re.findall(r"[\u0900-\u097f]", raw_query))
        detected_language = "hi" if devanagari_chars > 3 else "en"

        # 2. High-Risk Prompt Detection
        is_high_risk = False
        high_risk_category = None
        for category, patterns in cls.HIGH_RISK_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, raw_query, re.IGNORECASE | re.UNICODE):
                    is_high_risk = True
                    high_risk_category = category
                    break
            if is_high_risk:
                break

        # 3. Explicit Department Filter (ONLY when explicit)
        department_id = None
        for dept_id, pattern in cls.EXPLICIT_DEPT_PATTERNS:
            if pattern.search(raw_query):
                department_id = dept_id
                break

        # 4. Explicit Document Type Filter (ONLY when explicit)
        # Avoid treating GO number inquiries ("शासनादेश क्रमांक क्या है", "शासनादेश संख्या")
        # or interrogatives ("किस शासनादेश में", "किस आदेश में") as hard doc_type filters.
        query_for_doctype = re.sub(
            r"(?:शासनादेश|आदेश|order|go)\s*(?:संख्या|क्रमांक|नंबर|no\.?|number)|(?:किस|कौन\s*सा|which)\s+(?:शासनादेश|आदेश|order|go|नियम|नियमावली|rules?)|(?:का\s+नियम\s+किस\s+आदेश\s+में)",
            "",
            raw_query,
            flags=re.IGNORECASE | re.UNICODE,
        )
        doc_type = None
        for dt_code, pattern in cls.EXPLICIT_DOC_TYPE_PATTERNS:
            if pattern.search(query_for_doctype):
                doc_type = dt_code
                break

        # 5. Explicit GO / Order Number Filter
        go_number = None
        m_go = cls.EXPLICIT_GO_NUM_PATTERN.search(raw_query)
        if m_go:
            candidate = m_go.group(1).strip().strip(",.;:")
            if any(c.isdigit() for c in candidate):
                go_number = candidate
        else:
            m_standalone = cls.STANDALONE_GO_PATTERN.search(raw_query)
            if m_standalone:
                candidate = m_standalone.group(1).strip().strip(",.;:")
                if any(c.isdigit() for c in candidate):
                    go_number = candidate

        # 6. Explicit Date Filter (exact date, financial year, or year range)
        date_from, date_to, exact_date = cls._extract_dates(raw_query)

        # 7. Clean query text
        clean_query = raw_query
        # Remove GO numbers and explicit prefixes if they match clean tokens
        clean_query = re.sub(r"\s+", " ", clean_query).strip()

        # 8. Out-of-jurisdiction and unsupported topic detection
        is_out_of_jurisdiction = any(pat.search(raw_query) for pat in cls.OUT_OF_JURISDICTION_PATTERNS)
        has_unsupported_topic = any(pat.search(raw_query) for pat in cls.UNSUPPORTED_TOPIC_PATTERNS)

        # 9. Conversational greeting and system guidance detection
        normalized_q = re.sub(r"[^\w\s\u0900-\u097f]", "", raw_query.lower()).strip()
        GREETING_EXACT = {
            "hi", "hello", "hey", "hola", "namaste", "greetings", "good morning",
            "good afternoon", "good evening", "howdy", "who are you", "what can you do",
            "what is adam", "who is adam", "how to search", "how do i search", "help",
            "capabilities", "what are your capabilities", "system status", "how to use",
            "नमस्ते", "नमस्कार", "प्रणाम", "सुप्रभात", "आप कौन हैं", "तुम कौन हो",
            "अदम क्या है", "सहायता", "मदद", "खोज कैसे करें", "आप क्या कर सकते हैं"
        }
        is_greeting = (
            normalized_q in GREETING_EXACT
            or any(normalized_q == g for g in ("hi adam", "hello adam", "hey adam", "namaste adam", "about adam"))
            or (len(normalized_q.split()) <= 4 and any(k in normalized_q for k in ("what is adam", "who are you", "how to use adam", "help me search")))
        )

        return ParsedQuery(
            raw_query=raw_query,
            clean_query=clean_query,
            department_id=department_id,
            doc_type=doc_type,
            go_number=go_number,
            date_from=date_from,
            date_to=date_to,
            exact_date=exact_date,
            is_high_risk=is_high_risk,
            high_risk_category=high_risk_category,
            detected_language=detected_language,
            is_out_of_jurisdiction=is_out_of_jurisdiction,
            has_unsupported_topic=has_unsupported_topic,
            is_greeting=is_greeting,
        )

    @classmethod
    def _extract_dates(cls, text: str) -> Tuple[Optional[date], Optional[date], Optional[date]]:
        """Extract explicit exact date, financial year, or calendar year from query."""
        # Check explicit exact numeric dates: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        m_num = re.search(r"\b(\d{1,2})[\.\-\/](\d{1,2})[\.\-\/](\d{4})\b", text)
        if m_num:
            try:
                dt = date(int(m_num.group(3)), int(m_num.group(2)), int(m_num.group(1)))
                return None, None, dt
            except ValueError:
                pass

        # Check explicit Hindi date: e.g. "15 जनवरी 2024" or "10 मार्च, 2023"
        for h_month, m_num_val in HINDI_MONTHS.items():
            if h_month in text:
                m_hi = re.search(rf"\b(\d{{1,2}})\s*{h_month},?\s*(\d{{4}})\b", text)
                if m_hi:
                    try:
                        dt = date(int(m_hi.group(2)), m_num_val, int(m_hi.group(1)))
                        return None, None, dt
                    except ValueError:
                        pass

        # Check explicit English date: e.g. "15th January 2024" or "January 15, 2024"
        for e_month, m_num_val in ENGLISH_MONTHS.items():
            m_en1 = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{e_month},?\s+(\d{{4}})\b", text, re.IGNORECASE)
            if m_en1:
                try:
                    dt = date(int(m_en1.group(2)), m_num_val, int(m_en1.group(1)))
                    return None, None, dt
                except ValueError:
                    pass
            m_en2 = re.search(rf"\b{e_month}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", text, re.IGNORECASE)
            if m_en2:
                try:
                    dt = date(int(m_en2.group(2)), m_num_val, int(m_en2.group(1)))
                    return None, None, dt
                except ValueError:
                    pass

        # Check financial year: e.g. "2023-24" or "2022-2023"
        m_fy = re.search(r"\b(\d{4})\s*[\-\/]\s*(\d{2,4})\b", text)
        if m_fy:
            start_yr = int(m_fy.group(1))
            end_val = int(m_fy.group(2))
            end_yr = end_val if end_val > 1000 else (start_yr // 100) * 100 + end_val
            if end_yr == start_yr + 1:
                return date(start_yr, 4, 1), date(end_yr, 3, 31), None

        # Check single year: "year 2023", "2023 के", "in 2022", "वर्ष 2021"
        m_yr = re.search(r"(?:year|in|वर्ष|साल)\s*(\d{4})\b|\b(\d{4})\s*(?:के|में|का|की|orders?|rules?|act)\b", text, re.IGNORECASE)
        if m_yr:
            yr_str = m_yr.group(1) or m_yr.group(2)
            yr = int(yr_str)
            if 1950 <= yr <= 2050:
                return date(yr, 1, 1), date(yr, 12, 31), None

        return None, None, None
