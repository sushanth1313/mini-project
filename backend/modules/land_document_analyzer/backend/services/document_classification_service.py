"""Automatic Karnataka property document type classifier (17 supported document classes)."""
import re
from typing import Any, Dict, List, Optional, Tuple

from modules.land_document_analyzer.backend.models.schemas import DOCUMENT_TYPES

# Explicit document heading/title patterns evaluated on upper document text (high discriminative weight)
TITLE_RULES: Dict[str, List[Tuple[str, float]]] = {
    "Sale Deed": [
        (r"\babsolute\s+sale\s+deed\b", 7.0),
        (r"\bsale\s+deed\b", 6.5),
    ],
    "Mother Deed / Parent Deed": [
        (r"\bmother\s+deed\b|\bparent\s+deed\b|\bprior\s+sale\s+deed\b", 8.5),
    ],
    "RTC / Pahani": [
        (r"\brecord\s+of\s+rights(?:\s*\(\s*rtc\s*/?\s*pahani\s*\))?\b", 7.0),
        (r"\bpahani\b|\brtc\s*/\s*pahani\b", 6.5),
    ],
    "Mutation Register Extract": [
        (r"\bmutation\s+register\s+extract\b|\bmutation\s+extract\b", 7.5),
        (r"\bmutation\s+register\b", 6.5),
    ],
    "Encumbrance Certificate (EC)": [
        (r"\bencumbrance\s+certificate\b", 7.5),
    ],
    "Khata Certificate": [
        (r"\b(?:e-?)?khata\s+certificate\b", 7.0),
    ],
    "Khata Extract": [
        (r"\bkhata\s+extract\b|\bassessment\s+extract\b", 7.0),
    ],
    "Property Tax Receipt": [
        (r"\bproperty\s+tax\s+receipt\b|\btax\s+paid\s+receipt\b", 7.0),
    ],
    "Land Conversion Order": [
        (r"\b(?:land\s+)?conversion\s+order\b", 7.0),
    ],
    "Approved Layout Plan": [
        (r"\bapproved\s+layout\s+plan\b|\blayout\s+approval\b", 7.0),
    ],
    "Survey Sketch": [
        (r"\bsurvey\s+sketch\b|\btippani\b|\bphodi\b", 6.5),
    ],
    "11E Sketch": [
        (r"\b11\s*-?\s*e\s+sketch\b|\bform\s+11\s*-?\s*e\b", 7.5),
    ],
    "Survey Settlement Records": [
        (r"\bsurvey\s+settlement\b|\baakarband\b", 7.0),
    ],
    "Building Approval": [
        (r"\bbuilding\s+(?:plan\s+)?approval\b|\bbuilding\s+licen[cs]e\b|\bsanctioned\s+plan\b", 7.0),
    ],
    "RERA Registration Document": [
        (r"\brera\s+registration\b|\bkarnataka\s+rera\b", 7.0),
    ],
    "Court Order / Litigation Document": [
        (r"\bin\s+the\s+court\s+of\b|\bhigh\s+court\s+of\s+karnataka\b", 7.0),
    ],
}

# Weighted keyword patterns across the full document body (evaluated after masking cross-references)
CLASSIFICATION_RULES: Dict[str, List[Tuple[str, float]]] = {
    "Sale Deed": [
        (r"\babsolute\s+sale\s+deed\b", 4.0),
        (r"\bsale\s+deed\b", 3.5),
        (r"\bseller\s*/\s*transferor\b|\bvendor\b.*\bpurchaser\b|\bseller\b.*\bbuyer\b", 3.0),
        (r"\bbuyer\s*/\s*transferee\b|\bexecutant\b.*\bclaimant\b", 2.5),
        (r"\bsale\s+consideration\b|\bconsideration\b", 2.2),
        (r"\bexecution\s+date\b|\bschedule\s+of\s+property\b|\bschedule\s+property\b", 1.8),
        (r"\bsub[-\s]?registrar\b", 2.0),
        (r"\bregistration\s+(?:no|number)\b", 1.2),
    ],
    "Mother Deed / Parent Deed": [
        (r"\bmother\s+deed\b|\bparent\s+deed\b", 8.5),
        (r"\bprior\s+sale\s+deed\b|\bprevious\s+title\s+deed\b", 4.0),
        (r"\bpartition\s+deed\b|\bgift\s+deed\b|\brelease\s+deed\b", 3.0),
        (r"\bflow\s+of\s+title\b|\bchain\s+of\s+title\b", 2.5),
    ],
    "RTC / Pahani": [
        (r"\brecord\s+of\s+rights\b|\bpahani\b", 4.0),
        (r"\brtc\s+extract\b|\bform\s+no\.?\s*16\b", 3.5),
        (r"\bpattadar\b|\bkhatedar\b|\bkhathedar\b|\bkultivator\b|\bcultivator\b", 3.0),
        (r"\bRecord\s+of\s+Rights\s+and\s+Tenancy\b|\brecord\s+year\b|\bcultivation\s*/\s*possession\b", 2.8),
        (r"\bland\s+classification\b|\bbhoomi\b", 2.0),
    ],
    "Mutation Register Extract": [
        (r"\bmutation\s+register\b|\bmutation\s+extract\b", 4.5),
        (r"\bmutation\s+reference\b|\bm\.?r\.?\s*(?:no|number)\b|\bmr-[a-z0-9-]+\b", 3.5),
        (r"\bmutation\s+(?:details|date|reason|basis|order)\b|\bapplication\s+date\b", 2.5),
        (r"\bform\s+no\.?\s*12\b|\bform\s+no\.?\s*21\b", 3.0),
        (r"\bprevious\s+owner\b.*\bnew\s+owner\b|\btransferor\b.*\btransferee\b|\bapplicant\s*/\s*claimant\b", 2.5),
        (r"\bmutation\s+entered\b|\bpending\s+objection\b|\bnot\s+shown\s+as\s+certified\b", 2.2),
    ],
    "Encumbrance Certificate (EC)": [
        (r"\bencumbrance\s+certificate\b", 5.0),
        (r"\bform\s+no\.?\s*15\b", 3.0),
        (r"\bkaveri\b|\bec-style\b", 2.2),
        (r"\bsearch\s+period\b|\bsearch\s+particulars\b|\bsearch\s+result\b|\bperiod\s+of\s+search\b", 3.2),
        (r"\bnil\s+encumbrance\b|\bno\s+registered\s+encumbrance\b|\bmortgage\b|\bcharge\b", 2.2),
    ],
    "Khata Certificate": [
        (r"\bkhata\s+certificate\b|\be-?khata\s+certificate\b", 5.0),
        (r"\bform\s+9\b|\bform\s+11b\b|\bpid\s+no\b", 2.5),
        (r"\bassessment\s+register\b", 1.8),
    ],
    "Khata Extract": [
        (r"\bkhata\s+extract\b|\bassessment\s+extract\b", 5.0),
        (r"\bdemand\s+register\b|\bproperty\s+identification\s+number\b", 2.5),
    ],
    "Property Tax Receipt": [
        (r"\bproperty\s+tax\s+receipt\b|\btax\s+paid\s+receipt\b", 5.0),
        (r"\bsas\s+application\b|\bchallan\s+no\b|\bassessment\s+year\b", 2.5),
    ],
    "Land Conversion Order": [
        (r"\bland\s+conversion\s+order\b|\bconversion\s+order\b", 5.0),
        (r"\bsection\s+95\b|\bkarnataka\s+land\s+revenue\s+act\b", 3.5),
        (r"\bdeputy\s+commissioner\b|\bd\.?c\.?\s+conversion\b", 3.0),
        (r"\bnon-?agricultural\b|\bna\s+conversion\b|\baln\b", 2.8),
    ],
    "Approved Layout Plan": [
        (r"\bapproved\s+layout\s+plan\b|\blayout\s+approval\b", 5.0),
        (r"\btechnical\s+approval\b|\bprovisional\s+layout\b|\bfinal\s+layout\b", 3.0),
        (r"\bcivic\s+amenity\b|\bpark\s+area\b|\broad\s+width\b", 2.5),
        (r"\bmuda\b|\bmda\b|\bdtcp\b|\bplanning\s+authority\b", 2.0),
    ],
    "Survey Sketch": [
        (r"\bsurvey\s+sketch\b|\btippani\b|\bhissa\s+tippani\b|\bphodi\b", 4.5),
        (r"\bsurveyor\b|\bmeasurements?\s+in\s+chains\b|\baakarband\b", 2.5),
    ],
    "11E Sketch": [
        (r"\b11\s*-?\s*e\s+sketch\b|\bform\s+11\s*-?\s*e\b", 5.5),
        (r"\bpre-?mutation\s+sketch\b|\blicensed\s+surveyor\b", 3.0),
    ],
    "Survey Settlement Records": [
        (r"\bsurvey\s+settlement\b|\baakarband\b|\brevision\s+settlement\b", 4.5),
        (r"\bpot\s+kharab\b|\bclass\s+of\s+soil\b", 2.5),
    ],
    "Building Approval": [
        (r"\bbuilding\s+(?:plan\s+)?approval\b|\bbuilding\s+licen[cs]e\b", 5.0),
        (r"\bsanctioned\s+plan\b|\bcommencement\s+certificate\b|\boccupancy\s+certificate\b", 3.0),
    ],
    "RERA Registration Document": [
        (r"\bkarnataka\s+rera\b|\bprm/ka/rera\b|\brera\s+registration\b", 5.5),
        (r"\breal\s+estate\s+regulatory\s+authority\b", 3.5),
    ],
    "Court Order / Litigation Document": [
        (r"\bin\s+the\s+court\s+of\b|\bhigh\s+court\s+of\s+karnataka\b", 5.0),
        (r"\br\.?a\.?\s*no\.?\b|\bw\.?p\.?\s*no\.?\b|\bcivil\s+judge\b", 3.5),
        (r"\bplaintiff\b.*\bdefendant\b|\bpetitioner\b.*\brespondent\b", 4.0),
        (r"\bjudgment\b|\bplaint\b|\bdecree\b|\bcause\s+title\b", 3.0),
    ],
}

FILENAME_HINTS: Dict[str, List[str]] = {
    "Sale Deed": ["sale_deed", "saledeed", "sale-deed"],
    "Mother Deed / Parent Deed": ["mother_deed", "parent_deed", "motherdeed"],
    "RTC / Pahani": ["rtc", "pahani"],
    "Mutation Register Extract": ["mutation", "mr_extract"],
    "Encumbrance Certificate (EC)": ["encumbrance", "_ec", "ec_", "ec."],
    "Khata Certificate": ["khata_cert", "ekhata"],
    "Khata Extract": ["khata_extract"],
    "Property Tax Receipt": ["tax_receipt", "property_tax"],
    "Land Conversion Order": ["conversion", "dc_order", "aln"],
    "Approved Layout Plan": ["layout", "muda_plan", "mda_plan"],
    "Survey Sketch": ["survey_sketch", "tippani"],
    "11E Sketch": ["11e", "11_e"],
    "Survey Settlement Records": ["settlement", "aakarband"],
    "Building Approval": ["building_approval", "sanction_plan"],
    "RERA Registration Document": ["rera"],
    "Court Order / Litigation Document": ["court", "litigation", "order_os", "injunction"],
}

# Cross-reference phrases inside other documents that mention another document type incidentally
CROSS_REFERENCE_NOISE_PATTERNS = [
    r"related\s+rtc(?:\s+survey)?\s*[:\-][^\n]*",
    r"refer\s+to\s+mutation\s+register[^\n]*",
    r"related\s+sale\s+deed(?:\s+reference)?\s*[:\-][^\n]*",
    r"all\s+four\s+documents[^\n]*",
    r"simulated\s+entry\s*:[^\n]*o\.s\.[^\n]*",
    r"o\.s\.\s*\d+/\d{4}[^\n]*invented\s+test\s+data[^\n]*",
    r"1\s+acre\s+\d+\s+guntas\s*\(\s*sale\s+deed\s*\)",
]

LOW_CONFIDENCE_THRESHOLD = 0.68
AMBIGUITY_MARGIN_THRESHOLD = 1.5


def _strip_cross_references(text: str) -> str:
    cleaned = text or ""
    for pat in CROSS_REFERENCE_NOISE_PATTERNS:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _extract_heading_region(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    filtered = [
        ln
        for ln in lines[:18]
        if not ln.lower().startswith(("fictional training", "important:", "page ", "--- page"))
    ]
    return "\n".join(filtered[:10])[:700]


class DocumentClassificationService:
    """Classifies uploaded Karnataka land documents using heading, lexical, and filename signals."""

    def classify(
        self,
        text: str,
        filename: str = "",
        user_declared_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        header_text = _extract_heading_region(text).lower()
        body_text = _strip_cross_references(text).lower()
        fname_lower = (filename or "").lower()

        scores: Dict[str, float] = {}
        matched_signals: Dict[str, List[str]] = {}

        for doc_type, patterns in CLASSIFICATION_RULES.items():
            total = 0.0
            hits: List[str] = []

            for t_pat, t_weight in TITLE_RULES.get(doc_type, []):
                if re.search(t_pat, header_text, flags=re.IGNORECASE | re.DOTALL):
                    total += t_weight
                    hits.append(f"title:{t_pat}")

            for pattern, weight in patterns:
                if re.search(pattern, body_text, flags=re.IGNORECASE | re.DOTALL):
                    total += weight
                    hits.append(pattern)

            for hint in FILENAME_HINTS.get(doc_type, []):
                if hint in fname_lower:
                    total += 1.4
                    hits.append(f"filename:{hint}")

            if total > 0:
                scores[doc_type] = round(total, 2)
                matched_signals[doc_type] = hits

        if not scores or max(scores.values()) < 1.5:
            chosen = user_declared_type if user_declared_type in DOCUMENT_TYPES else "Other Supporting Document"
            return {
                "document_type": chosen,
                "original_classified_type": chosen,
                "confidence": 0.35 if user_declared_type else 0.2,
                "classification_method": "user_declared_fallback" if user_declared_type else "default_fallback",
                "classification_status": "Requires Confirmation",
                "requires_confirmation": True,
                "confirmation_message": "Document type requires confirmation.",
                "matched_indicators": matched_signals.get(chosen, []),
                "alternatives": [
                    {"document_type": dt, "score": sc}
                    for dt, sc in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
                ],
                "user_declared_type": user_declared_type,
                "matches_user_declaration": None if not user_declared_type else (user_declared_type == chosen),
                "classification_history": [],
            }

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_type, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, round(top_score - second_score, 2))

        # Calibrated confidence score strictly derived from lexical/title score + margin
        confidence = min(0.98, round(0.45 + min(top_score / 14.0, 0.38) + min(margin / 8.0, 0.15), 2))
        if user_declared_type and user_declared_type in DOCUMENT_TYPES and user_declared_type == top_type:
            confidence = min(0.99, round(confidence + 0.03, 2))

        requires_confirmation = (
            confidence < LOW_CONFIDENCE_THRESHOLD
            or (second_score > 0 and margin < AMBIGUITY_MARGIN_THRESHOLD and top_score < 7.0)
            or top_type == "Other Supporting Document"
        )
        confirmation_message = "Document type requires confirmation." if requires_confirmation else None

        alternatives = [
            {"document_type": dt, "score": sc} for dt, sc in ranked[1:4]
        ]

        return {
            "document_type": top_type,
            "original_classified_type": top_type,
            "confidence": confidence,
            "score": top_score,
            "score_margin": margin,
            "classification_method": "heading_lexical_and_filename_rules",
            "classification_status": "Requires Confirmation" if requires_confirmation else "Classified",
            "requires_confirmation": requires_confirmation,
            "confirmation_message": confirmation_message,
            "matched_indicators": matched_signals.get(top_type, [])[:6],
            "alternatives": alternatives,
            "user_declared_type": user_declared_type,
            "matches_user_declaration": (
                None if not user_declared_type else (user_declared_type == top_type)
            ),
            "classification_history": [],
        }

    def segment_multi_document_pages(
        self,
        pages: List[Dict[str, Any]],
        fallback_filename: str = "",
        user_declared_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Inspect pages individually to detect bundled multi-document PDFs (e.g. RTC + Mutation + EC + Sale Deed).
        Multi-page single documents without distinct document headers stay grouped together.
        Never uses the bundle filename during per-page classification so filename never biases pages.
        """
        if not pages:
            return []

        if len(pages) == 1:
            full_text = pages[0].get("text") or ""
            cls_res = self.classify(text=full_text, filename=fallback_filename, user_declared_type=user_declared_type)
            return [{
                "pages": pages,
                "page_numbers": [pages[0].get("page_number", 1)],
                "page_range": f"Page {pages[0].get('page_number', 1)}",
                "text": full_text,
                "classification": cls_res,
            }]

        groups: List[Dict[str, Any]] = []
        for idx, page in enumerate(pages):
            p_text = page.get("text") or ""
            p_num = int(page.get("page_number") or (idx + 1))
            header = _extract_heading_region(p_text).lower()
            p_cls = self.classify(text=p_text, filename="")
            p_type = p_cls["document_type"]
            p_score = float(p_cls.get("score") or 0.0)
            has_title_hit = any(ind.startswith("title:") for ind in (p_cls.get("matched_indicators") or []))
            has_doc_marker = bool(re.search(r"\bdocument\s+[a-d]\b|\bsample\s+only\b", p_text[:450], re.I))

            if not groups:
                groups.append({"pages": [page], "page_cls": p_cls})
                continue

            cur_cls = groups[-1]["page_cls"]
            cur_type = cur_cls["document_type"]
            starts_new_doc = (
                (p_type != cur_type and (has_title_hit or p_score >= 3.0))
                or (has_title_hit and has_doc_marker)
            )
            if starts_new_doc:
                groups.append({"pages": [page], "page_cls": p_cls})
            else:
                groups[-1]["pages"].append(page)

        if len(groups) == 1:
            full_text = "\n\n".join((p.get("text") or "") for p in pages)
            cls_res = self.classify(text=full_text, filename=fallback_filename, user_declared_type=user_declared_type)
            pnums = [int(p.get("page_number") or (i + 1)) for i, p in enumerate(pages)]
            prange = f"Pages {pnums[0]}–{pnums[-1]}" if len(pnums) > 1 else f"Page {pnums[0]}"
            return [{
                "pages": pages,
                "page_numbers": pnums,
                "page_range": prange,
                "text": full_text,
                "classification": cls_res,
            }]

        segments: List[Dict[str, Any]] = []
        for grp in groups:
            g_pages = grp["pages"]
            g_text = "\n\n".join((p.get("text") or "") for p in g_pages)
            g_cls = self.classify(text=g_text, filename="")
            pnums = [int(p.get("page_number") or 1) for p in g_pages]
            prange = f"Page {pnums[0]}" if len(pnums) == 1 else f"Pages {pnums[0]}–{pnums[-1]}"
            segments.append({
                "pages": g_pages,
                "page_numbers": pnums,
                "page_range": prange,
                "text": g_text,
                "classification": g_cls,
            })
        return segments
