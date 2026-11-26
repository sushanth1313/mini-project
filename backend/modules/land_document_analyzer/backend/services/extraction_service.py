"""Structured document field extraction with tabular line-pair parsing, page provenance, and separated confidence."""
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.models.schemas import UNABLE_TO_EXTRACT
from modules.land_document_analyzer.backend.utils.security import check_external_ai_consent, get_safe_logger

logger = get_safe_logger(__name__)

# Field schemas per Karnataka document type
DOCUMENT_FIELD_SCHEMAS: Dict[str, List[str]] = {
    "Sale Deed": [
        "document_number", "registration_number", "registration_date", "sub_registrar_office",
        "seller_names", "buyer_names", "property_description", "survey_number", "hissa_number",
        "plot_number", "village", "hobli", "taluk", "district", "property_extent",
        "property_boundaries", "sale_consideration", "registration_details", "witness_information",
    ],
    "Mother Deed / Parent Deed": [
        "document_number", "registration_number", "registration_date", "sub_registrar_office",
        "seller_names", "buyer_names", "survey_number", "hissa_number", "village",
        "hobli", "taluk", "district", "property_extent", "property_boundaries", "sale_consideration",
    ],
    "RTC / Pahani": [
        "owner_names", "father_or_spouse_name", "survey_number", "hissa_number", "village",
        "hobli", "taluk", "district", "total_land_extent", "recorded_land_classification",
        "cultivation_details", "mutation_references", "record_date",
    ],
    "Encumbrance Certificate (EC)": [
        "search_period", "property_identification", "applicant_name", "document_numbers",
        "registration_dates", "transaction_parties", "registered_transactions",
        "mortgages_or_charges", "release_or_cancellation_entries",
        "survey_number", "village", "taluk", "district", "property_extent",
    ],
    "Mutation Register Extract": [
        "mutation_number", "previous_owner", "new_owner", "survey_number", "hissa_number",
        "village", "taluk", "district", "mutation_date", "mutation_reason",
        "linked_document_reference", "order_details", "recorded_status", "property_extent",
    ],
    "Khata Certificate": [
        "document_number", "owner_names", "survey_number", "plot_number",
        "village", "taluk", "district", "property_extent", "record_date",
    ],
    "Khata Extract": [
        "document_number", "owner_names", "survey_number", "plot_number",
        "village", "taluk", "district", "property_extent", "record_date",
    ],
    "Property Tax Receipt": [
        "document_number", "owner_names", "plot_number", "survey_number",
        "village", "taluk", "district", "sale_consideration", "record_date",
    ],
    "Land Conversion Order": [
        "conversion_order_number", "order_date", "applicant", "survey_number", "hissa_number",
        "village", "taluk", "district", "converted_extent", "approved_land_use",
        "issuing_authority", "conditions",
    ],
    "Approved Layout Plan": [
        "layout_name", "approval_number", "approval_date", "issuing_authority",
        "survey_number", "village", "taluk", "district", "total_layout_extent",
        "plot_number", "plot_dimensions", "property_extent", "road_widths",
        "parks_and_civic_amenity_areas", "approval_conditions",
    ],
    "Survey Sketch": [
        "survey_number", "hissa_number", "village", "hobli", "taluk", "district",
        "property_extent", "property_boundaries", "record_date",
    ],
    "11E Sketch": [
        "document_number", "survey_number", "hissa_number", "village", "hobli",
        "taluk", "district", "property_extent", "applicant", "record_date",
    ],
    "Court Order / Litigation Document": [
        "court_name", "case_number", "case_type", "parties", "filing_date",
        "current_status", "order_date", "property_references", "survey_number",
        "village", "nature_of_dispute", "interim_orders", "stay_orders", "final_orders",
    ],
}

# Section headers & stop markers for multi-line table parsing
STOP_HEADERS = {
    "field", "value", "recorded value", "property identification",
    "record of rights and tenancy (illustrative rtc extract)",
    "mutation details", "search particulars", "parties and transaction",
    "cross-reference", "cross reference", "schedule of property",
    "testing note", "interpretation boundary", "clean sample",
    "litigation / mismatch sample",
}

# Canonical field aliases used inside tabular/newline-separated Karnataka PDFs (lowercase)
LABEL_ALIASES: Dict[str, List[str]] = {
    "document_number": [
        "illustrative document number", "illustrative record reference", "mock search reference",
        "mock instrument number", "document number", "doc. no", "doc no", "document no",
        "khata no", "khata number", "pid no", "receipt no", "receipt number",
    ],
    "registration_number": ["mock instrument number", "registration number", "registration no", "reg. no", "reg no"],
    "registration_date": [
        "registration date", "date of registration", "registered on",
        "execution date", "date of execution",
    ],
    "sub_registrar_office": ["search jurisdiction", "sub-registrar office", "sub registrar office", "sro"],
    "seller_names": ["seller / transferor", "seller/transferor", "seller name", "sellers", "seller", "vendor", "executant"],
    "buyer_names": ["buyer / transferee", "buyer/transferee", "buyer name", "buyers", "buyer", "purchaser", "claimant"],
    "owner_names": [
        "recorded holder name", "pattadar / recorded holder", "pattadar/recorded holder", "pattadar",
        "owner name", "owner names", "owner(s) name", "khatedar", "khathedar", "recorded owner",
    ],
    "father_or_spouse_name": ["father / relation", "father / spouse name", "father/spouse name", "father's name", "spouse name"],
    "applicant_name": ["applicant / claimed owner", "applicant name", "applicant(s)"],
    "applicant": ["applicant / claimant", "applicant/claimant", "applicant name", "applicant"],
    "property_description": ["schedule of property", "property description", "schedule property"],
    "property_identification": ["property", "property identification", "property description", "property identification details", "schedule description"],
    "survey_number": ["related survey", "survey number", "survey numbers", "survey no", "sy. no", "sy no"],
    "hissa_number": ["hissa / subdivision", "hissa number", "hissa no", "hissa"],
    "plot_number": ["plot number", "plot no", "site number", "site no"],
    "village": ["property locality", "village / locality", "village/locality", "village", "locality"],
    "hobli": ["hobli"],
    "taluk": ["taluk", "taluka"],
    "district": ["district / state", "district/state", "district"],
    "property_extent": ["extent", "extent shown", "extent carried forward", "property extent", "site area", "plot extent", "plot area", "land area"],
    "total_land_extent": ["extent", "extent shown", "total land extent", "total extent", "land extent"],
    "converted_extent": ["converted extent", "extent converted", "extent"],
    "total_layout_extent": ["total layout extent", "layout extent"],
    "property_boundaries": ["boundaries", "property boundaries"],
    "sale_consideration": ["consideration (fictional)", "sale consideration", "consideration amount", "consideration", "tax paid", "amount paid"],
    "registration_details": ["registration details", "book no"],
    "witness_information": ["witness information", "witnesses", "witness"],
    "recorded_land_classification": ["land classification", "classification", "land type"],
    "cultivation_details": ["record notes", "cultivation / possession note", "cultivation details", "crop details", "remarks"],
    "mutation_references": ["mutation reference", "mutation references", "m.r. no", "mr no"],
    "record_date": ["illustrative entry date", "record year", "record date", "rtc date", "valid as on", "date of issue", "assessment year"],
    "search_period": ["search period", "period of search"],
    "document_numbers": ["document numbers", "registered doc nos", "document references"],
    "registration_dates": ["registration dates", "dates of registration"],
    "transaction_parties": ["transaction parties", "executant / claimant"],
    "registered_transactions": ["transaction schedule", "search result", "registered transactions", "nature of transaction"],
    "mortgages_or_charges": ["mortgages or charges", "mortgages / charges", "encumbrance entries", "charges"],
    "release_or_cancellation_entries": ["release or cancellation entries", "discharge details"],
    "mutation_number": ["illustrative mutation reference", "mutation reference", "mutation number", "mutation no", "m.r. no", "mr no"],
    "previous_owner": ["previous recorded holder", "previous owner", "transferor"],
    "new_owner": ["claimant / transferee", "new owner", "mutated in favour of", "transferee", "applicant / claimant", "applicant/claimant"],
    "mutation_date": ["mutation entry date", "application date", "mutation date", "date of mutation"],
    "mutation_reason": ["mutation basis", "mutation reason", "acquisition mode", "basis"],
    "linked_document_reference": ["underlying transaction reference"],
    "order_details": ["mutation remarks", "order details", "revenue inspector order", "remarks"],
    "recorded_status": ["entry status (fictional)", "entry status", "status", "recorded status", "mutation status"],
    "conversion_order_number": ["conversion order number", "conversion order no", "order no"],
    "order_date": ["order date", "date of order"],
    "approved_land_use": ["approved land use", "converted purpose", "land use"],
    "issuing_authority": ["issuing authority", "authority"],
    "conditions": ["conditions", "conversion conditions"],
    "layout_name": ["layout name", "project name"],
    "approval_number": ["approval number", "approval no", "sanction no"],
    "approval_date": ["approval date", "date of approval"],
    "plot_dimensions": ["plot dimensions", "site dimensions"],
    "road_widths": ["road widths", "approach road"],
    "parks_and_civic_amenity_areas": ["parks and civic amenity areas", "ca site"],
    "approval_conditions": ["approval conditions", "conditions"],
    "court_name": ["court name"],
    "case_number": ["case number", "case no", "o.s. no", "w.p. no", "r.a. no"],
    "case_type": ["case type", "suit type"],
    "parties": ["parties", "plaintiff / defendant"],
    "filing_date": ["filing date", "date of filing"],
    "current_status": ["current status", "case status"],
    "property_references": ["property references", "suit schedule property"],
    "nature_of_dispute": ["nature of dispute", "dispute type"],
    "interim_orders": ["interim orders", "interim order"],
    "stay_orders": ["stay orders", "stay order"],
    "final_orders": ["final orders", "judgment"],
}

# Flattened sorted lookup from label text -> list of matching canonical fields
_ALL_KNOWN_LABELS: List[Tuple[str, str]] = []
for _fname, _aliases in LABEL_ALIASES.items():
    for _al in _aliases:
        _ALL_KNOWN_LABELS.append((_al, _fname))
# Extra metadata labels that mark cell boundaries even if not schema fields
_NON_SCHEMA_LABELS = {
    "test property id", "remarks", "cross-reference", "cross reference",
    "interpretation boundary", "testing note", "schedule of property",
}
_ALL_KNOWN_LABEL_SET = {al for al, _ in _ALL_KNOWN_LABELS} | _NON_SCHEMA_LABELS | STOP_HEADERS

# Legacy/same-line fallback patterns
FIELD_PATTERNS: Dict[str, List[str]] = {
    "document_number": [r"(?:illustrative\s+document\s+number|document\s*(?:no|number)|doc\.?\s*no\.?)\s*[:\-]\s*([^\n]+)"],
    "registration_number": [r"(?:registration\s*(?:no|number)|reg\.?\s*no\.?)\s*[:\-]\s*([^\n]+)"],
    "registration_date": [r"(?:registration\s*date|execution\s*date|date\s*of\s*(?:registration|execution)|registered\s*on)\s*[:\-]\s*([^\n]+)"],
    "sub_registrar_office": [r"(?:sub[-\s]?registrar\s*office|sro)\s*[:\-]\s*([^\n]+)"],
    "seller_names": [r"(?:seller\s*/\s*transferor|seller(?:\(s\)|s)?|vendor(?:\(s\)|s)?|executant)\s*[:\-]\s*([^\n]+)"],
    "buyer_names": [r"(?:buyer\s*/\s*transferee|buyer(?:\(s\)|s)?|purchaser(?:\(s\)|s)?|claimant)\s*[:\-]\s*([^\n]+)"],
    "owner_names": [r"(?:pattadar\s*/\s*recorded\s*holder|owner(?:\(s\)|s)?\s*name(?:s)?|khatedar(?:\(s\)|s)?|khathedar)\s*[:\-]\s*([^\n]+)"],
    "survey_number": [r"(?:related\s*survey|survey\s*(?:no|number|numbers)|sy\.?\s*no\.?)\s*[:\-]\s*([A-Za-z0-9/\-,\s]+?)(?=\s*(?:hissa|village|hobli|taluk|extent|\n|$))"],
    "hissa_number": [r"(?:hissa\s*(?:no|number)?)\s*[:\-]\s*([A-Za-z0-9/\-]+)"],
    "plot_number": [r"(?:plot\s*(?:no|number)|site\s*(?:no|number))\s*[:\-]\s*([A-Za-z0-9/\-]+)"],
    "village": [r"(?:village\s*/\s*locality|village)\s*[:\-]\s*([^\n]+)"],
    "hobli": [r"(?:hobli)\s*[:\-]\s*([^\n]+)"],
    "taluk": [r"(?:taluk|taluka)\s*[:\-]\s*([^\n]+)"],
    "district": [r"(?:district\s*/\s*state|district)\s*[:\-]\s*([^\n]+)"],
    "property_extent": [r"(?:property\s*extent|site\s*area|plot\s*extent|plot\s*area|extent|land\s*area)\s*[:\-]\s*([^\n]+)"],
    "total_land_extent": [r"(?:total\s*land\s*extent|total\s*extent|extent)\s*[:\-]\s*([^\n]+)"],
    "sale_consideration": [r"(?:sale\s*consideration|consideration\s*amount|consideration)\s*[:\-]\s*([^\n]+)"],
    "mutation_number": [r"(?:mutation\s*ref(?:erence)?|mutation\s*(?:no|number)|m\.?r\.?\s*no\.?)\s*[:\-]\s*([^\n]+)"],
    "mutation_references": [r"(?:mutation\s*ref(?:erence|erences)?|m\.?r\.?\s*no\.?)\s*[:\-]\s*([^\n]+)"],
    "mutation_date": [r"(?:application\s*date|mutation\s*date|date\s*of\s*mutation)\s*[:\-]\s*([^\n]+)"],
    "court_name": [r"(?:court\s*name|in\s+the\s+court\s+of)\s*[:\-]?\s*([^\n]+)"],
    "case_number": [r"(?:case\s*(?:no|number)|o\.?s\.?\s*no\.?|w\.?p\.?\s*no\.?|r\.?a\.?\s*no\.?)\s*[:\-]\s*([^\n]+)"],
}


class AIProviderInterface(ABC):
    """Configurable provider interface for AI-assisted extraction."""

    @abstractmethod
    def enhance_extraction(
        self, document_type: str, pages: List[Dict[str, Any]], baseline_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Refines baseline extracted fields without inventing unreadable values."""


class LocalHeuristicProvider(AIProviderInterface):
    """Default on-premise extractor requiring zero external data transmission."""

    def enhance_extraction(
        self, document_type: str, pages: List[Dict[str, Any]], baseline_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        return baseline_fields


def _clean_label(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().rstrip(":-")).lower()


def _normalize_rupee_glyph(val: str) -> str:
    # Some generated PDFs map U+20B9 / rupee symbol glyph to leading capital 'I' before Indian digits
    return re.sub(r"^I(?=\d[\d,]*(?:\.\d+)?(?:\s*\(|$))", "₹", val.strip())


def _extract_tabular_kv_from_page(text: str) -> Dict[str, str]:
    """
    Extracts Key -> Value pairs from both same-line (`Label: Value`) and
    multi-line tabular PyMuPDF output (`Label\nValue line 1\nValue line 2`).
    """
    raw_lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    kv_by_label: Dict[str, str] = {}
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        lower_line = _clean_label(line)

        # Case 1: Inline 'Label: Value' or 'Label - Value' on the same line
        colon_split = re.match(r"^([^:\-]{2,45}?)\s*[:\-]\s*(.+)$", line)
        if colon_split:
            cand_label = _clean_label(colon_split.group(1))
            if cand_label in _ALL_KNOWN_LABEL_SET:
                kv_by_label.setdefault(cand_label, colon_split.group(2).strip())
                i += 1
                continue

        # Case 2: Standalone label on its own line followed by 1+ value lines until next label/header
        if lower_line in _ALL_KNOWN_LABEL_SET and lower_line not in STOP_HEADERS:
            val_parts: List[str] = []
            j = i + 1
            while j < len(raw_lines):
                nxt = raw_lines[j]
                nxt_lower = _clean_label(nxt)
                nxt_prefix = None
                cs = re.match(r"^([^:\-]{2,45}?)\s*[:\-]\s*(.+)$", nxt)
                if cs and _clean_label(cs.group(1)) in _ALL_KNOWN_LABEL_SET:
                    nxt_prefix = _clean_label(cs.group(1))
                if nxt_lower in _ALL_KNOWN_LABEL_SET or nxt_prefix is not None:
                    break
                if nxt.lower().startswith(("no government seal", "fictional training", "important:", "--- page", "page ")):
                    break
                val_parts.append(nxt)
                # Single-row fields usually wrap at most 4 lines
                if len(val_parts) >= 5:
                    break
                j += 1
            if val_parts:
                kv_by_label.setdefault(lower_line, re.sub(r"\s+", " ", " ".join(val_parts)).strip())
            i = j
            continue

        i += 1
    return kv_by_label


class ExtractionService:
    """Extracts structured fields with page numbers, separated confidence, and original-vs-corrected auditability."""

    def __init__(self, provider: Optional[AIProviderInterface] = None):
        self.provider = provider or LocalHeuristicProvider()

    def extract_fields(
        self,
        document_type: str,
        ocr_result: Dict[str, Any],
        ai_provider_name: Optional[str] = None,
        external_ai_consent: bool = False,
    ) -> Dict[str, Any]:
        provider_name = ai_provider_name or Settings.AI_PROVIDER
        consent_ok, consent_note = check_external_ai_consent(external_ai_consent, provider_name)
        if not consent_ok:
            logger.warning("External AI blocked due to missing consent; falling back to local extraction.")
            provider_name = "local_heuristic"

        pages = ocr_result.get("pages", [])
        schema_fields = DOCUMENT_FIELD_SCHEMAS.get(
            document_type,
            ["document_number", "registration_date", "owner_names", "survey_number", "village", "taluk", "district", "property_extent"],
        )

        all_unreadable = (not pages) or all(p.get("readability") == "unreadable" for p in pages)
        page_kv_cache: List[Tuple[Dict[str, Any], Dict[str, str], Dict[str, Tuple[str, int, float, str]]]] = []

        for page in pages:
            text = page.get("text", "")
            page_conf = float(page.get("confidence", 0.0))
            if not text or page.get("readability") == "unreadable":
                page_kv_cache.append((page, {}, {}))
                continue
            kv = _extract_tabular_kv_from_page(text)
            derived = self._derive_compound_fields(document_type, page, kv, page_conf)
            page_kv_cache.append((page, kv, derived))

        extracted: Dict[str, Dict[str, Any]] = {}
        for field_name in schema_fields:
            value, page_num, conf, status, snippet = self._resolve_field(
                field_name, page_kv_cache, all_unreadable
            )
            extracted[field_name] = {
                "original_value": value,
                "corrected_value": None,
                "effective_value": value,
                "is_corrected": False,
                "page_number": page_num,
                "confidence": conf,
                "extraction_status": status,  # extracted | missing_in_document | unreadable_text
                "raw_snippet": snippet,
                "provenance": "Information extracted from uploaded documents",
            }

        if provider_name == "local_heuristic":
            extracted = self.provider.enhance_extraction(document_type, pages, extracted)

        extracted_count = sum(1 for f in extracted.values() if f["extraction_status"] == "extracted")
        total_fields = len(extracted)
        unable_count = total_fields - extracted_count
        field_rate = round(extracted_count / total_fields, 3) if total_fields else 0.0
        # Honest field-level extraction confidence (0.0 when no fields extracted!)
        avg_field_conf = (
            round(sum(float(f.get("confidence", 0.0)) for f in extracted.values()) / total_fields, 3)
            if total_fields
            else 0.0
        )

        return {
            "document_type": document_type,
            "ai_provider_used": provider_name,
            "consent_note": consent_note,
            "fields": extracted,
            "total_fields": total_fields,
            "extracted_count": extracted_count,
            "unable_to_extract_count": unable_count,
            "field_extraction_rate": field_rate,
            "field_extraction_confidence": avg_field_conf,
        }

    def _derive_compound_fields(
        self,
        document_type: str,
        page: Dict[str, Any],
        kv: Dict[str, str],
        page_conf: float,
    ) -> Dict[str, Tuple[str, int, float, str]]:
        """Extracts structured sub-fields cleanly from multi-part administrative cells and cross-references."""
        pg = int(page["page_number"])
        text = page.get("text", "") or ""
        out: Dict[str, Tuple[str, int, float, str]] = {}

        # 1. District / State or Taluk / District or Village / Taluk slash pairs
        if "district / state" in kv:
            raw_ds = kv["district / state"]
            dist_part = raw_ds.split(",")[0].strip()
            if dist_part:
                out["district"] = (dist_part, pg, round(min(0.95, page_conf * 0.94), 2), raw_ds)
        if "taluk / district" in kv:
            raw_td = kv["taluk / district"]
            pts_td = [p.strip() for p in raw_td.split("/") if p.strip()]
            if len(pts_td) >= 2:
                out.setdefault("taluk", (pts_td[0], pg, round(min(0.94, page_conf * 0.94), 2), raw_td))
                out.setdefault("district", (pts_td[1], pg, round(min(0.94, page_conf * 0.94), 2), raw_td))
        if "village / taluk" in kv:
            raw_vt = kv["village / taluk"]
            pts_vt = [p.strip() for p in raw_vt.split("/") if p.strip()]
            if len(pts_vt) >= 2:
                out.setdefault("village", (pts_vt[0], pg, round(min(0.94, page_conf * 0.94), 2), raw_vt))
                out.setdefault("taluk", (pts_vt[1], pg, round(min(0.94, page_conf * 0.94), 2), raw_vt))
        if "survey / hissa" in kv:
            raw_sh = kv["survey / hissa"]
            # e.g. '42/3A / 3A'
            pts_sh = [p.strip() for p in raw_sh.split(" / ") if p.strip()]
            if len(pts_sh) >= 2:
                out.setdefault("survey_number", (pts_sh[0], pg, round(min(0.94, page_conf * 0.94), 2), raw_sh))
                out.setdefault("hissa_number", (pts_sh[1], pg, round(min(0.94, page_conf * 0.94), 2), raw_sh))

        # 2. Compound 'Property' cell: 'Kyathamaranahalli, Survey 42/3A, Hissa 3A' or 'Hulikere, Jayapura, Mysuru'
        prop_raw = kv.get("property") or kv.get("property identification") or kv.get("property description") or ""
        if prop_raw:
            sy_inline = re.search(r"survey\s*(?:no\.?)?\s*([A-Za-z0-9/\-]+)", prop_raw, re.I)
            if sy_inline:
                out.setdefault("survey_number", (sy_inline.group(1), pg, round(min(0.90, page_conf * 0.90), 2), prop_raw))
            hs_inline = re.search(r"hissa\s*(?:no\.?)?\s*([A-Za-z0-9/\-]+)", prop_raw, re.I)
            if hs_inline:
                out.setdefault("hissa_number", (hs_inline.group(1), pg, round(min(0.90, page_conf * 0.90), 2), prop_raw))
            parts = [p.strip() for p in prop_raw.split(",") if p.strip()]
            # Drop trailing 'Karnataka' state token when parsing hierarchical locations
            if parts and parts[-1].lower() == "karnataka":
                parts = parts[:-1]
            if len(parts) >= 4:
                out.setdefault("village", (parts[0], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
                out.setdefault("hobli", (parts[1], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
                out.setdefault("taluk", (parts[2], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
                out.setdefault("district", (parts[3], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
            elif len(parts) == 3 and not sy_inline:
                out.setdefault("village", (parts[0], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
                out.setdefault("taluk", (parts[1], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
                out.setdefault("district", (parts[2], pg, round(min(0.9, page_conf * 0.9), 2), prop_raw))
            elif len(parts) >= 1 and not sy_inline:
                out.setdefault("village", (parts[0], pg, round(min(0.85, page_conf * 0.85), 2), prop_raw))
            elif parts and sy_inline:
                out.setdefault("village", (parts[0], pg, round(min(0.88, page_conf * 0.88), 2), prop_raw))

        # 3. Schedule narrative parsing if survey/taluk/district missed in tables
        sched = kv.get("schedule of property", "")
        if sched:
            sy_m = re.search(r"(?:survey\s*no\.?|sy\.?\s*no\.?)\s*([A-Za-z0-9/\-]+)", sched, re.I)
            if sy_m:
                out.setdefault("survey_number", (f"Survey No. {sy_m.group(1)}", pg, round(min(0.88, page_conf * 0.88), 2), sched))
            tal_m = re.search(r"([A-Za-z\s]+?)\s+Taluk\b", sched, re.I)
            if tal_m:
                out.setdefault("taluk", (tal_m.group(1).split(",")[-1].strip(), pg, round(min(0.88, page_conf * 0.88), 2), sched))
            dist_m = re.search(r"([A-Za-z\s]+?)\s+District\b", sched, re.I)
            if dist_m:
                out.setdefault("district", (dist_m.group(1).split(",")[-1].strip(), pg, round(min(0.88, page_conf * 0.88), 2), sched))

        # 4. Survey / Hissa split safeguard (preserve full survey token like 'Survey No. 42/3A' AND derive hissa '3A' if formatted N/H)
        sy_val = kv.get("survey number") or kv.get("related survey") or (out.get("survey_number")[0] if "survey_number" in out else "")
        if sy_val:
            hissa_m = re.search(r"\b\d+\s*/\s*([0-9]+[A-Za-z]*)\b", sy_val)
            if hissa_m and "hissa number" not in kv and "hissa no" not in kv:
                out.setdefault("hissa_number", (hissa_m.group(1), pg, round(min(0.82, page_conf * 0.84), 2), sy_val))

        # 5. Linked sale deed reference / mutation references in RTC, Mutation, EC
        xref = kv.get("cross-reference") or kv.get("cross reference") or ""
        mut_basis = kv.get("mutation basis") or kv.get("mutation reason") or ""
        cult_note = kv.get("cultivation / possession note") or ""
        search_res = kv.get("search result") or ""

        if document_type == "Mutation Register Extract":
            doc_ref_m = re.search(r"\b([A-Z]+-SD-\d{4}-\d+|\d{3,6}/\d{4}-\d{2,4}|document\s+[A-Z0-9\-/]+)\b", f"{mut_basis} {xref}", re.I)
            if doc_ref_m:
                ref_val = re.sub(r"^document\s+", "", doc_ref_m.group(1), flags=re.I).strip()
                out.setdefault("linked_document_reference", (ref_val, pg, round(min(0.92, page_conf * 0.92), 2), f"{mut_basis} | {xref}".strip(" |")))

        if document_type == "RTC / Pahani":
            mr_m = re.search(r"\b(MR[-\s]?[A-Z0-9\-/]+\d)\b", f"{cult_note} {text}", re.I)
            if mr_m:
                out.setdefault("mutation_references", (mr_m.group(1), pg, round(min(0.88, page_conf * 0.88), 2), cult_note or mr_m.group(1)))

        if document_type == "Encumbrance Certificate (EC)":
            # Extract document references & mortgage/court charge signals from Search Result / Transaction schedule
            tx_sched = kv.get("transaction schedule") or ""
            sr_text = f"{search_res} {tx_sched}".strip() or text
            doc_refs = re.findall(r"\b(?:[A-Z]+-(?:SD|MORT)-\d{4}-\d+|O\.?S\.?\s*(?:No\.?\s*)?\d+/\d{4})\b", sr_text, re.I)
            if doc_refs:
                out.setdefault("document_numbers", (", ".join(dict.fromkeys(doc_refs)), pg, round(min(0.92, page_conf * 0.92), 2), sr_text))
            low_sr = sr_text.lower()
            if re.search(r"\bno\s+registered\s+encumbrance\b|\bnil\b", low_sr) and not re.search(r"mortgage|charge|dispute|objection", low_sr):
                out.setdefault("mortgages_or_charges", ("No registered encumbrance entry shown in supplied search period", pg, round(min(0.92, page_conf * 0.92), 2), search_res))
                out.setdefault("release_or_cancellation_entries", ("Not applicable (no entry shown in period)", pg, round(min(0.85, page_conf * 0.85), 2), search_res))
            elif re.search(r"\bmortgage\b|\bcharge\b|\bhypothecation\b|\battachment\b|\bo\.?s\.?\b|\bcivil\s+suit\b|\binterim\s+order\b|\bdisputed\b", low_sr):
                # Capture full transaction block from page if schedule wraps lines
                sched_blk = text[text.lower().find("transaction schedule"):] if "transaction schedule" in text.lower() else sr_text
                sched_snippet = re.sub(r"\s+", " ", sched_blk[:650]).strip()
                out.setdefault("mortgages_or_charges", (sched_snippet, pg, round(min(0.92, page_conf * 0.92), 2), sched_snippet))
                out.setdefault("registered_transactions", (sched_snippet, pg, round(min(0.90, page_conf * 0.90), 2), sched_snippet))
                if "release not shown" in text.lower() or "not released" in text.lower():
                    out.setdefault("release_or_cancellation_entries", ("Release not shown in supplied EC", pg, round(min(0.9, page_conf * 0.9), 2), sched_snippet))

        # Sale consideration rupee normalization
        if "consideration" in kv:
            out.setdefault("sale_consideration", (_normalize_rupee_glyph(kv["consideration"]), pg, round(min(0.94, page_conf * 0.94), 2), kv["consideration"]))

        return out

    def _resolve_field(
        self,
        field_name: str,
        page_kv_cache: List[Tuple[Dict[str, Any], Dict[str, str], Dict[str, Tuple[str, int, float, str]]]],
        all_unreadable: bool,
    ) -> Tuple[str, Optional[int], float, str, str]:
        aliases = LABEL_ALIASES.get(field_name, [])
        patterns = FIELD_PATTERNS.get(field_name, [])

        for page, kv, derived in page_kv_cache:
            text = page.get("text", "")
            page_conf = float(page.get("confidence", 0.0))
            if not text or page.get("readability") == "unreadable":
                continue

            # 1. Explicit tabular/KV match by alias priority
            for al in aliases:
                if al in kv:
                    raw_val = _normalize_rupee_glyph(kv[al]) if field_name == "sale_consideration" else kv[al]
                    if field_name == "district" and "," in raw_val:
                        raw_val = raw_val.split(",")[0].strip()
                    if raw_val and not self._looks_garbled(raw_val):
                        return raw_val, page["page_number"], round(min(0.96, page_conf * 0.95), 2), "extracted", kv[al]

            # 2. Compound/derived parser output
            if field_name in derived:
                val, pg, d_conf, snip = derived[field_name]
                if val and not self._looks_garbled(val):
                    return val, pg, d_conf, "extracted", snip

            # 3. Same-line regex fallback
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    raw_val = re.sub(r"\s+", " ", match.group(1)).strip(" :;,-")
                    if raw_val:
                        if self._looks_garbled(raw_val):
                            return UNABLE_TO_EXTRACT, page["page_number"], round(page_conf * 0.35, 2), "unreadable_text", raw_val
                        return raw_val, page["page_number"], round(min(0.92, page_conf * 0.92), 2), "extracted", raw_val

        if all_unreadable:
            return UNABLE_TO_EXTRACT, None, 0.0, "unreadable_text", ""
        return UNABLE_TO_EXTRACT, None, 0.0, "missing_in_document", ""

    @staticmethod
    def _looks_garbled(value: str) -> bool:
        if len(value) > 4:
            non_alnum = sum(1 for ch in value if not (ch.isalnum() or ch in " .,/-()&'#:₹%"))
            if non_alnum / len(value) > 0.4:
                return True
        return False

    @staticmethod
    def apply_manual_correction(
        extraction_record: Dict[str, Any], field_name: str, corrected_value: str, corrected_by: str = "user"
    ) -> Dict[str, Any]:
        """Records a user's manual correction while strictly preserving the original OCR value."""
        fields = extraction_record.get("fields", {})
        if field_name not in fields:
            fields[field_name] = {
                "original_value": UNABLE_TO_EXTRACT,
                "corrected_value": corrected_value,
                "effective_value": corrected_value,
                "is_corrected": True,
                "corrected_by": corrected_by,
                "page_number": None,
                "confidence": 1.0,
                "extraction_status": "manually_corrected",
                "raw_snippet": "",
                "provenance": "Information provided manually by the user",
            }
        else:
            fields[field_name]["corrected_value"] = corrected_value
            fields[field_name]["effective_value"] = corrected_value
            fields[field_name]["is_corrected"] = True
            fields[field_name]["corrected_by"] = corrected_by
            fields[field_name]["extraction_status"] = "manually_corrected"
            fields[field_name]["confidence"] = 1.0
            fields[field_name]["provenance"] = "Information provided manually by the user"

        total_fields = len(fields)
        extracted_count = sum(
            1 for f in fields.values() if f.get("effective_value") and f.get("effective_value") != UNABLE_TO_EXTRACT
        )
        extraction_record["total_fields"] = total_fields
        extraction_record["extracted_count"] = extracted_count
        extraction_record["unable_to_extract_count"] = total_fields - extracted_count
        extraction_record["field_extraction_rate"] = round(extracted_count / total_fields, 3) if total_fields else 0.0
        extraction_record["field_extraction_confidence"] = (
            round(sum(float(f.get("confidence", 0.0)) for f in fields.values()) / total_fields, 3)
            if total_fields
            else 0.0
        )
        return extraction_record
