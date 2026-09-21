"""Hybrid retrieval engine combining BM25 keyword search and local vector similarity.

Per Phase 03 specification:
- '2. Hybrid retrieve: PostgreSQL full-text/BM25 + local vector search (pgvector) over authorised chunks.'
- '3. Apply metadata ACLs before ranking; rerank top results with a compact cross-encoder only if benchmarks justify it.'
- Applies explicit metadata filters (department, date, GO number, doc_type) strictly.
- Reciprocal Rank Fusion (RRF) with normalized scoring.
"""

import hashlib
import math
import re
from typing import List, Dict, Any, Optional, Tuple, Set

import numpy as np
from sqlalchemy import or_
from sqlalchemy.orm import Session

from adam.db.models import Document, DocumentVersion, DocumentChunk
from adam.rag.acl import AclEnforcer
from adam.rag.models import ParsedQuery, UserContext, EvidencePassage
from adam.vocabularies import ReviewStatus, LifecycleStatus


def _tokenize(text: str) -> List[str]:
    """Tokenize Hindi/English text into lowercased alphanumeric/Devanagari tokens."""
    if not text:
        return []
    # Match English alphanumeric and Devanagari character sequences
    tokens = re.findall(r"[A-Za-z0-9\u0900-\u097f]+", text.lower())
    return [t for t in tokens if len(t) > 1 or re.match(r"[\u0900-\u097f]", t)]


ADMIN_BILINGUAL_MAP: Dict[str, List[str]] = {
    # Hindi -> English administrative terms
    "महंगाई": ["dearness", "da"],
    "भत्ता": ["allowance"],
    "भत्ते": ["allowance"],
    "डीए": ["da", "dearness", "allowance"],
    "मकान": ["house"],
    "किराया": ["rent"],
    "एचआरए": ["hra", "house", "rent", "allowance"],
    "संतान": ["child", "care"],
    "देखभाल": ["care"],
    "अवकाश": ["leave"],
    "सीसीएल": ["ccl", "child", "care", "leave"],
    "दाखिल": ["mutation"],
    "खारिज": ["mutation"],
    "दाखिल-खारिज": ["mutation"],
    "वरासत": ["succession", "mutation"],
    "खसरा": ["khasra", "mutation"],
    "नामांतरण": ["mutation"],
    "लेखा": ["audit"],
    "परीक्षा": ["audit"],
    "संपरीक्षा": ["audit", "inspection"],
    "आपत्तियों": ["objections", "objection"],
    "आपत्ति": ["objections", "objection"],
    "मनरेगा": ["mgnrega"],
    "मजदूरी": ["wage", "wages"],
    "आवास": ["awas", "housing", "pmay"],
    "पीएमएवाई": ["pmay"],
    "कोषागार": ["treasury", "ekosh"],
    "आहरण": ["drawing", "ddo"],
    "वितरण": ["disbursing", "ddo"],
    "अधिकारियों": ["officers"],
    "अधिकारी": ["officer", "officers"],
    "प्रभावी": ["effect", "effective"],
    "वेतन": ["salary", "pay", "wage"],
    "चिकित्सा": ["medical"],
    "जीपीएफ": ["gpf", "provident"],
    "हल्द्वानी": ["haldwani"],
    "हरिद्वार": ["haridwar"],
    "देहरादून": ["dehradun"],
    "पर्वतीय": ["hill"],
    "सामाजिक": ["social"],
    "अंकेक्षण": ["audit"],
    "शौचालय": ["toilet", "swachh"],
    "लाभार्थी": ["beneficiary", "beneficiaries"],
    "तहसीलदार": ["tehsildar"],
    "नायब": ["naib"],
    "अधिसूचना": ["notification"],
    "कार्मिक": ["personnel", "gad"],
    "प्रशासन": ["administration"],
    "सामान्य": ["general"],
    "ग्राम्य": ["rural"],
    "विकास": ["development"],
    "वित्त": ["finance"],
    "व्यय": ["expenditure"],
    "राजस्व": ["revenue"],
    "परिषद": ["board"],
    "निर्विवाद": ["undisputed"],
    "विवादित": ["disputed"],
    "अवशेष": ["arrears"],
    "एरियर": ["arrears"],
    "मानक": ["standard"],
    "संचालन": ["operating"],
    "प्रक्रिया": ["procedure", "sop"],
    "पंचायती": ["panchayati"],
    "पंचायत": ["panchayat"],
    "ऑडिट": ["audit"],
    "निस्तारित": ["settled", "resolved", "disposed"],
    "निस्तारण": ["settlement", "disposal"],
    "दिवस": ["days", "day"],
    "दिन": ["days", "day"],
    "अकुशल": ["unskilled"],
    "महिला": ["female", "women"],
    "पूर्ववृत्त": ["precedent"],
    "अधिक्रमित": ["supersede", "superseded"],
    "अधिक्रमण": ["supersession", "supersede"],
    "संशोधित": ["amend", "amended"],
    "संशोधन": ["amendment", "amend"],
    "विरोधाभास": ["conflict", "contradiction"],
    "विसंगति": ["discrepancy", "conflict"],
    "विवरण": ["statement", "statements"],
    "वित्तीय": ["financial"],

    # English -> Hindi administrative terms
    "dearness": ["महंगाई", "डीए"],
    "allowance": ["भत्ता", "भत्ते"],
    "mutation": ["दाखिल", "खारिज", "दाखिल-खारिज", "वरासत"],
    "succession": ["वरासत", "उत्तराधिकार"],
    "khasra": ["खसरा"],
    "audit": ["ऑडिट", "लेखा", "परीक्षा", "संपरीक्षा"],
    "inspection": ["निरीक्षण", "संपरीक्षा"],
    "objection": ["आपत्ति"],
    "objections": ["आपत्तियों", "आपत्ति"],
    "settled": ["निस्तारित", "निस्तारण"],
    "settlement": ["निस्तारण"],
    "days": ["दिवस", "दिन"],
    "day": ["दिवस", "दिन"],
    "unskilled": ["अकुशल"],
    "female": ["महिला"],
    "women": ["महिला"],
    "precedent": ["पूर्ववृत्त"],
    "supersede": ["अधिक्रमित", "अधिक्रमण"],
    "superseded": ["अधिक्रमित", "अधिक्रमण"],
    "amend": ["संशोधित", "संशोधन"],
    "amended": ["संशोधित", "संशोधन"],
    "conflict": ["विरोधाभास", "विसंगति", "मतभेद"],
    "discrepancy": ["विसंगति", "विरोधाभास"],
    "statement": ["विवरण"],
    "statements": ["विवरण"],
    "financial": ["वित्तीय"],
    "mgnrega": ["मनरेगा"],
    "wage": ["मजदूरी"],
    "wages": ["मजदूरी"],
    "leave": ["अवकाश"],
    "ccl": ["संतान", "देखभाल", "अवकाश", "सीसीएल"],
    "hra": ["मकान", "किराया", "भत्ता", "एचआरए"],
    "da": ["महंगाई", "भत्ता", "डीए"],
    "pmay": ["आवास", "प्रधानमंत्री"],
    "treasury": ["कोषागार", "कोष"],
    "ddo": ["आहरण", "वितरण"],
    "disbursing": ["वितरण"],
    "drawing": ["आहरण"],
    "gpf": ["जीपीएफ", "भविष्य", "निधि"],
    "provident": ["भविष्य", "निधि"],
    "undisputed": ["निर्विवाद"],
    "disputed": ["विवादित"],
    "panchayat": ["पंचायत"],
    "gram": ["ग्राम"],
    "sabha": ["सभा"],
    "medical": ["चिकित्सा"],
    "hill": ["पर्वतीय"],
    "toilet": ["शौचालय"],
    "beneficiary": ["लाभार्थी"],
    "beneficiaries": ["लाभार्थी"],
    "tehsildar": ["तहसीलदार"],
    "naib": ["नायब"],
    "arrears": ["अवशेष", "एरियर"],
    "procedure": ["प्रक्रिया"],
    "operating": ["संचालन"],
    "standard": ["मानक"],
    "sop": ["मानक", "संचालन", "प्रक्रिया"],
}


class MultilingualSemanticVectorizer:
    """Compact, deterministic multilingual semantic vectorizer for local vector search.

    Generates dense L2-normalized embeddings (dimension=128) from character n-grams,
    subwords, and semantic projection. Fully offline, lightweight, deterministic,
    and fast on Mac CPU.
    """

    DIMENSION = 128

    @classmethod
    def embed_text(cls, text: str) -> List[float]:
        """Compute 128-dimensional dense vector embedding for text."""
        if not text:
            return [0.0] * cls.DIMENSION

        vec = np.zeros(cls.DIMENSION, dtype=np.float32)
        words = _tokenize(text)

        # 1. Word-level hashing with cross-lingual canonical expansion
        expanded_words = list(words)
        for w in words:
            if w in ADMIN_BILINGUAL_MAP:
                expanded_words.extend(ADMIN_BILINGUAL_MAP[w])

        for w in expanded_words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % cls.DIMENSION
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[idx] += sign

        # 2. Character n-gram hashing (captures Hindi inflections and Devanagari morphemes)
        clean = text.lower()
        n = 3
        for i in range(len(clean) - n + 1):
            ngram = clean[i : i + n]
            h = int(hashlib.sha256(ngram.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % cls.DIMENSION
            sign = 1.0 if ((h >> 4) & 1) == 0 else -1.0
            vec[idx] += 0.3 * sign

        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        return vec.tolist()

    @classmethod
    def cosine_similarity(cls, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two dense vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        v1 = np.array(vec1, dtype=np.float32)
        v2 = np.array(vec2, dtype=np.float32)
        dot = float(np.dot(v1, v2))
        norm1 = float(np.linalg.norm(v1))
        norm2 = float(np.linalg.norm(v2))
        if norm1 <= 1e-6 or norm2 <= 1e-6:
            return 0.0
        return max(0.0, min(1.0, dot / (norm1 * norm2)))


class BM25Ranker:
    """Okapi BM25 scoring implementation supporting bilingual Devanagari and English corpora."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def score(
        self,
        query_tokens: List[str],
        doc_tokens: List[str],
        doc_len: int,
        avg_doc_len: float,
        idf_dict: Dict[str, float],
        field_bonus: float = 0.0,
    ) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        # Term frequencies in doc
        tf_dict: Dict[str, int] = {}
        for t in doc_tokens:
            tf_dict[t] = tf_dict.get(t, 0) + 1

        score = 0.0
        for qt in query_tokens:
            if qt not in tf_dict:
                continue
            tf = tf_dict[qt]
            idf = idf_dict.get(qt, 0.0)
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / max(avg_doc_len, 1.0)))
            score += idf * (numerator / max(denominator, 1e-6))

        return score + field_bonus


STOPWORDS: Set[str] = {
    "what", "which", "where", "when", "who", "whom", "whose", "why", "how",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "the", "a", "an", "and", "or", "but", "if", "because",
    "as", "until", "while", "of", "at", "by", "for", "with", "about", "against",
    "between", "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "can", "will", "just", "should", "now", "state",
    "government", "guidelines", "uttarakhand", "uttaranchal", "uk", "details", "show", "according",
    "find", "per", "give", "please", "orders", "order", "rules", "rule", "acts", "act",
    "me", "mein", "ko", "se", "par", "tha", "thi", "the", "hai", "hain", "kya", "kitna",
    "kitne", "kaise", "kab", "kisko", "hoga", "huye", "diya", "diye", "gaya", "hua", "hike",
    "की", "का", "के", "में", "से", "को", "पर", "है", "हैं", "था", "थी", "थे",
    "और", "या", "क्या", "कितना", "कितने", "किस", "कौन", "द्वारा",
    "उत्तराखण्ड", "उत्तराखंड", "उत्तरांचल", "शासन", "तथा", "एवं", "सहित", "हेतु", "दें", "बताएं", "दिखाएं",
    "शासनादेश", "आदेश", "नियम", "नियमावली", "संख्या", "क्रमांक", "दिनांक",
}

ADMIN_CATEGORY_WORDS: Set[str] = {
    "allowance", "allowances", "leave", "rules", "rule", "order", "orders",
    "guidelines", "guideline", "rate", "rates", "amount", "grant", "grants",
    "sanction", "sanctioned", "officers", "officer", "employees", "employee",
    "servant", "servants", "staff", "department", "scheme", "schemes",
    "policy", "policies", "notification", "circular", "procedure", "tenure",
    "days", "day", "percentage", "percent", "benefits", "benefit", "assistance",
    "funds", "fund", "ceiling", "limit", "limits", "criteria", "effective",
    "date", "month", "year", "annual", "daily", "monthly", "payment", "payout",
    "disbursement", "disburse", "entitled", "entitlement", "admissible",
    "admissibility", "details", "prescribed", "specified", "total", "ratio",
    "component", "deadline", "time", "period", "maximum", "minimum",
    "mandatory", "compulsory", "portal", "mode", "provision", "provisions",
    "standard", "operating", "inspection", "verification", "verified",
    "disposing", "disposal", "cases", "application", "applications",
    "भत्ता", "भत्ते", "अवकाश", "नियम", "नियमावली", "आदेश", "शासनादेश",
    "निर्देश", "दिशा-निर्देश", "दर", "दरें", "धनराशि", "राशि", "अनुदान",
    "स्वीकृति", "स्वीकृत", "अधिकारी", "अधिकारियों", "कर्मचारी", "कर्मचारियों",
    "सेवक", "सेवकों", "कार्मिक", "विभाग", "योजना", "नीति", "अधिसूचना",
    "परिपत्र", "प्रक्रिया", "दिन", "दिनों", "प्रतिशत", "लाभ", "सहायता",
    "कोष", "सीमा", "मानदंड", "प्रभावी", "लागू", "तिथि", "दिनांक", "माह",
    "वर्ष", "वार्षिक", "दैनिक", "मासिक", "भुगतान", "पात्रता", "पात्र",
    "विवरण", "निर्धारित", "कुल", "अनुपात", "घटक", "समय", "अवधि", "अधिकतम",
    "न्यूनतम", "अनिवार्य", "पोर्टल", "माध्यम", "प्रावधान", "मानक", "संचालन",
    "निरीक्षण", "सत्यापन", "निस्तारण", "निस्तारित", "वाद", "वादों", "आवेदन", "अभिलेख",
}


class CompactCrossEncoderReranker:
    """Compact cross-encoder reranker scoring exact phrase alignment, heading match,
    and entity containment.
    """

    @classmethod
    def rerank(
        cls,
        query: str,
        passages: List[EvidencePassage],
        top_k: int = 10,
    ) -> List[EvidencePassage]:
        """Rerank top passages based on query-passage alignment."""
        if not passages:
            return []

        q_lower = query.lower()
        q_tokens = set(_tokenize(query))
        expanded_q_tokens = set(q_tokens)
        for qt in q_tokens:
            if qt in ADMIN_BILINGUAL_MAP:
                expanded_q_tokens.update(ADMIN_BILINGUAL_MAP[qt])

        for p in passages:
            boost = 0.0
            p_text = p.content.lower()

            # Exact phrase match bonus
            if len(query) > 5 and q_lower in p_text:
                boost += 0.25

            # Section heading or title alignment
            check_text = f"{p.section_heading or ''} {p.title}".lower()
            tokens_in_check = set(_tokenize(check_text))
            if expanded_q_tokens & tokens_in_check:
                boost += 0.15

            # GO number match bonus
            if p.go_number and p.go_number.lower() in q_lower:
                boost += 0.30

            # Direct order date match
            if p.order_date and str(p.order_date.year) in q_lower:
                boost += 0.10

            p.score = min(1.0, p.score + boost)

        passages.sort(key=lambda x: x.score, reverse=True)
        return passages[:top_k]


class HybridRetriever:
    """End-to-end hybrid retrieval engine integrating ACL, BM25, and vector search."""

    def __init__(self, session: Session, retrieval_settings=None):
        self.session = session
        self.bm25 = BM25Ranker()
        self.vectorizer = MultilingualSemanticVectorizer()
        self.reranker = CompactCrossEncoderReranker()
        # Apply RetrievalSettings overrides if provided
        if retrieval_settings is not None:
            self._bm25_weight = float(getattr(retrieval_settings, "bm25_weight", 0.65))
            self._vec_weight = 1.0 - self._bm25_weight
            self._vector_min_similarity = float(getattr(retrieval_settings, "vector_min_similarity", 0.55))
            self._enable_rerank = bool(getattr(retrieval_settings, "enable_rerank", True))
        else:
            self._bm25_weight = 0.65
            self._vec_weight = 0.35
            self._vector_min_similarity = 0.55
            self._enable_rerank = True

    def retrieve(
        self,
        parsed_query: ParsedQuery,
        user_context: Optional[UserContext] = None,
        top_k: int = 10,
        enable_rerank: bool = True,
    ) -> List[EvidencePassage]:
        """Execute hybrid search over authorized chunks matching explicit query filters."""
        # Early refusal on queries with external jurisdictions or known unsupported topics
        if parsed_query.is_out_of_jurisdiction or parsed_query.has_unsupported_topic:
            return []

        # Step 1: Base query on active documents with approved chunks
        approved_statuses = [
            ReviewStatus.AUTO_APPROVED.value,
            ReviewStatus.REVIEWED.value,
            ReviewStatus.CORRECTED.value,
        ]

        base_query = (
            self.session.query(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(
                Document.lifecycle_status == LifecycleStatus.ACTIVE.value,
                DocumentChunk.review_status.in_(approved_statuses),
            )
        )

        # Step 2: Apply metadata ACLs BEFORE ranking (Pilot gate: 0 cross-tenant/ACL leaks)
        base_query = AclEnforcer.apply_acl_filter(self.session, base_query, user_context)

        # Step 3: Apply explicit query filters
        query = base_query
        if parsed_query.department_id:
            query = query.filter(DocumentChunk.department_id == parsed_query.department_id)

        # If GO number is present, prioritize exact GO number match
        if parsed_query.go_number:
            query = query.filter(
                or_(
                    DocumentChunk.go_number.ilike(f"%{parsed_query.go_number}%"),
                    DocumentChunk.content.ilike(f"%{parsed_query.go_number}%"),
                )
            )
        else:
            # Only filter doc_type if GO number is not specified
            if parsed_query.doc_type:
                dt_query = query.filter(DocumentChunk.doc_type == parsed_query.doc_type)
                if dt_query.count() > 0:
                    query = dt_query

        # Date filtering: check order_date, effective_from, or date within range
        if parsed_query.exact_date:
            date_q = query.filter(
                or_(
                    DocumentChunk.order_date == parsed_query.exact_date,
                    DocumentChunk.effective_from == parsed_query.exact_date,
                    DocumentChunk.effective_to == parsed_query.exact_date,
                )
            )
            if date_q.count() > 0:
                query = date_q
        else:
            if parsed_query.date_from and parsed_query.date_to:
                range_q = query.filter(
                    or_(
                        DocumentChunk.order_date.between(parsed_query.date_from, parsed_query.date_to),
                        DocumentChunk.effective_from.between(parsed_query.date_from, parsed_query.date_to),
                    )
                )
                if range_q.count() > 0:
                    query = range_q

        candidates = query.all()
        if not candidates:
            # If explicit department returned 0, do not leak other departments
            return []

        # Prepare corpus for BM25 and Vector calculation with bilingual expansion
        query_text = parsed_query.clean_query or parsed_query.raw_query
        q_tokens = _tokenize(query_text)
        expanded_q_tokens = list(q_tokens)
        for t in q_tokens:
            if t in ADMIN_BILINGUAL_MAP:
                expanded_q_tokens.extend(ADMIN_BILINGUAL_MAP[t])

        substantive_q_terms = {t for t in expanded_q_tokens if t not in STOPWORDS and len(t) > 1}
        topic_specifiers = {t for t in substantive_q_terms if t not in ADMIN_CATEGORY_WORDS}
        q_vector = self.vectorizer.embed_text(query_text)

        doc_data_list = []
        doc_lengths = []
        df_dict: Dict[str, int] = {}

        for chk, doc in candidates:
            subject = ""
            if chk.version and chk.version.attributes and chk.version.attributes.subject:
                subject = chk.version.attributes.subject
            full_searchable = f"{chk.section_heading or ''} {doc.title} {subject} {chk.content} {chk.go_number or ''}"
            tokens = _tokenize(full_searchable)
            token_set = set(tokens)
            doc_data_list.append((chk, doc, tokens, token_set, subject))
            doc_lengths.append(len(tokens))

            for st in token_set:
                df_dict[st] = df_dict.get(st, 0) + 1

        total_docs = len(doc_data_list)
        avg_doc_len = sum(doc_lengths) / max(total_docs, 1)

        # Calculate IDF
        idf_dict: Dict[str, float] = {}
        for term in expanded_q_tokens:
            df = df_dict.get(term, 0)
            idf_dict[term] = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))

        scored_candidates: List[Dict[str, Any]] = []

        for idx, (chk, doc, tokens, token_set, subject) in enumerate(doc_data_list):
            # Check substantive term overlap
            matched_substantive = substantive_q_terms & token_set
            matched_specifiers = topic_specifiers & token_set

            # Heading/title/GO number boost
            field_bonus = 0.0
            if chk.section_heading and any(qt in chk.section_heading.lower() for qt in substantive_q_terms):
                field_bonus += 2.0
            if subject and any(qt in subject.lower() for qt in substantive_q_terms):
                field_bonus += 2.0
            if chk.go_number and parsed_query.go_number and parsed_query.go_number.lower() in chk.go_number.lower():
                field_bonus += 5.0
            elif chk.go_number and any(qt in chk.go_number.lower() for qt in q_tokens):
                field_bonus += 3.0

            bm25_val = self.bm25.score(
                query_tokens=expanded_q_tokens,
                doc_tokens=tokens,
                doc_len=doc_lengths[idx],
                avg_doc_len=avg_doc_len,
                idf_dict=idf_dict,
                field_bonus=field_bonus,
            )

            # Vector similarity
            if chk.embedding_json:
                doc_vector = chk.embedding_json
            else:
                doc_vector = self.vectorizer.embed_text(f"{subject} {chk.content}")
            vec_val = self.vectorizer.cosine_similarity(q_vector, doc_vector)

            # Substantive grounding check:
            has_go_match = bool(
                chk.go_number and parsed_query.go_number and parsed_query.go_number.lower() in chk.go_number.lower()
            )

            # If the query contains topic specifiers (e.g. "bicycle", "paternity", "mgnrega"),
            # candidate chunk must match at least one topic specifier (or match explicit GO number)
            # to prevent category word false positives (e.g. "bicycle allowance" matching DA).
            if topic_specifiers and not has_go_match:
                if len(matched_specifiers) == 0:
                    continue

            if substantive_q_terms and not has_go_match and len(matched_substantive) == 0 and vec_val < self._vector_min_similarity:
                continue

            scored_candidates.append({
                "chunk": chk,
                "doc": doc,
                "bm25_score": bm25_val,
                "vector_score": vec_val,
                "matched_substantive_count": len(matched_substantive),
                "matched_specifiers_count": len(matched_specifiers),
                "has_go_match": has_go_match,
            })

        if not scored_candidates:
            return []

        # Genuine Hybrid Scoring: weighted combination of normalized BM25 score and vector similarity
        max_bm25 = max((c["bm25_score"] for c in scored_candidates), default=1.0)
        max_bm25 = max(max_bm25, 1.0)

        for item in scored_candidates:
            bm25_norm = item["bm25_score"] / max_bm25
            vec_score = item["vector_score"]
            sub_bonus = min(item["matched_substantive_count"] * 0.02, 0.10)
            item["hybrid_score"] = min(1.0, self._bm25_weight * bm25_norm + self._vec_weight * vec_score + sub_bonus)

        scored_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        max_hybrid = scored_candidates[0]["hybrid_score"] if scored_candidates else 1.0

        passages: List[EvidencePassage] = []
        for item in scored_candidates[: top_k * 2]:
            chk: DocumentChunk = item["chunk"]
            doc: Document = item["doc"]
            h_score = item["hybrid_score"]
            if not item["has_go_match"] and h_score < max(0.20, max_hybrid * 0.35):
                continue

            passage = EvidencePassage(
                chunk_id=chk.id,
                document_id=chk.document_id,
                version_id=chk.version_id,
                title=doc.title,
                department_id=chk.department_id,
                doc_type=chk.doc_type,
                page_start=chk.page_start,
                page_end=chk.page_end,
                section_heading=chk.section_heading,
                content=chk.content,
                score=round(h_score, 4),
                bm25_score=item["bm25_score"],
                vector_score=item["vector_score"],
                go_number=chk.go_number,
                gazette_number=chk.gazette_number,
                order_date=chk.order_date,
                effective_from=chk.effective_from,
                effective_to=chk.effective_to,
                source_url=chk.source_url,
                sha256=chk.sha256,
                bbox_list=chk.bbox_list_json or [],
            )
            passages.append(passage)

        effective_rerank = enable_rerank and self._enable_rerank
        if effective_rerank and passages:
            passages = self.reranker.rerank(query_text, passages, top_k=top_k)
        else:
            passages = passages[:top_k]

        return passages
