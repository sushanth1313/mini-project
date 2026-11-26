"""
Document extraction service.
Extracts text from PDFs using pdfplumber/PyMuPDF and images via Tesseract OCR.
"""
import os
import re
import json
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    """
    Extract text from PDF. Returns (text, method_used).
    Tries pdfplumber first, falls back to PyMuPDF.
    """
    text = ""
    method = "none"

    # Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
            text = "\n".join(pages)
            method = "pdfplumber"
    except Exception as e:
        log.warning(f"pdfplumber failed: {e}")

    # If pdfplumber got no text, try PyMuPDF
    if not text.strip():
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            pages = []
            for page in doc:
                pages.append(page.get_text())
            doc.close()
            text = "\n".join(pages)
            method = "pymupdf"
        except Exception as e:
            log.warning(f"PyMuPDF failed: {e}")

    return text.strip(), method


def extract_text_from_image(file_path: str) -> tuple[str, str]:
    """
    Extract text from image using Tesseract OCR via pytesseract.
    Returns (text, method_used).
    """
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        # Try to set Tesseract path for Windows
        if os.name == "nt":
            common_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for p in common_paths:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break
        text = pytesseract.image_to_string(img, lang="eng+kan")
        return text.strip(), "tesseract"
    except ImportError:
        log.warning("pytesseract not installed. OCR unavailable for images.")
        return "", "tesseract_unavailable"
    except Exception as e:
        log.warning(f"Tesseract OCR failed: {e}")
        return "", f"tesseract_error: {e}"


def extract_document_fields(text: str) -> dict:
    """
    Parse extracted text to find common land document fields.
    Uses regex patterns for Karnataka land documents (RTC, EC, Sale Deed, etc.)
    Returns dict of found fields (may have None values for not-found).
    """
    fields = {
        "owner_name": None,
        "survey_number": None,
        "document_type": None,
        "village": None,
        "taluk": None,
        "district": None,
        "area_mentioned": None,
        "dates_mentioned": [],
        "registration_ref": None,
        "is_property_document": True,
        "relevance_note": "Appears to be a property document."
    }

    if not text:
        return fields

    text_lower = text.lower()

    # Document type detection
    doc_types = {
        "sale deed": "Sale Deed",
        "sale certificate": "Sale Certificate",
        "rtc": "RTC / Pahani",
        "pahani": "RTC / Pahani",
        "encumbrance": "Encumbrance Certificate",
        "mutation": "Mutation Record",
        "gift deed": "Gift Deed",
        "partition": "Partition Deed",
        "agreement": "Agreement of Sale",
        "power of attorney": "Power of Attorney",
        "patta": "Patta",
        "khata": "Khata Certificate",
        "title deed": "Title Deed",
    }
    for key, val in doc_types.items():
        if key in text_lower:
            fields["document_type"] = val
            break

    # Survey number patterns (Karnataka land docs)
    survey_patterns = [
        r"survey\s+no[.:]?\s*(\d+[\w/\-]*)",
        r"s\.no[.:]?\s*(\d+[\w/\-]*)",
        r"sno[.:]?\s*(\d+[\w/\-]*)",
        r"plot\s+no[.:]?\s*(\d+[\w/\-]*)",
        r"khasra\s+no[.:]?\s*(\d+[\w/\-]*)",
    ]
    for pat in survey_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["survey_number"] = m.group(1).strip()
            break

    # Area patterns
    area_patterns = [
        r"(\d+[\d.,]*)\s*(sq\.?\s*ft|sqft|square\s+feet)",
        r"(\d+[\d.,]*)\s*(acres?|guntas?|cents?)",
        r"(\d+[\d.,]*)\s*(sq\.?\s*m|sqm|square\s+met)",
    ]
    for pat in area_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["area_mentioned"] = f"{m.group(1)} {m.group(2)}"
            break

    # Date patterns
    date_patterns = [
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}",
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
    ]
    dates = []
    for pat in date_patterns:
        dates.extend(re.findall(pat, text, re.IGNORECASE))
    fields["dates_mentioned"] = list(set(dates))[:10]  # limit to 10

    # Owner name patterns
    owner_patterns = [
        r"(?:seller|vendor|owner|grantor|executant)[:\s]+([A-Z][A-Za-z\s]{3,50}?)(?:\n|,|\.|son|d/o|w/o|s/o)",
        r"(?:Sri|Mr\.|Mrs\.|Smt\.|Dr\.)\s+([A-Z][A-Za-z\s]{3,50}?)(?:\n|,|\.)",
    ]
    for pat in owner_patterns:
        m = re.search(pat, text)
        if m:
            fields["owner_name"] = m.group(1).strip()
            break

    # Village / Taluk / District
    village_m = re.search(r"(?:village|hobli)[:\s]+([A-Za-z\s]{3,50})(?:\n|,|\.)", text, re.IGNORECASE)
    if village_m:
        fields["village"] = village_m.group(1).strip()

    taluk_m = re.search(r"taluk[:\s]+([A-Za-z\s]{3,30})(?:\n|,|\.)", text, re.IGNORECASE)
    if taluk_m:
        fields["taluk"] = taluk_m.group(1).strip()

    district_m = re.search(r"district[:\s]+([A-Za-z\s]{3,30})(?:\n|,|\.)", text, re.IGNORECASE)
    if district_m:
        fields["district"] = district_m.group(1).strip()

    # Registration number
    reg_patterns = [
        r"(?:registration|reg\.?\s*no)[.:\s]+([A-Z0-9/\-]{3,30})",
        r"document\s+no[.:\s]+([A-Z0-9/\-]{3,30})",
    ]
    for pat in reg_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields["registration_ref"] = m.group(1).strip()
            break

    # Determine if this is actually a property document vs a CV/resume
    cv_keywords = [r"\bresume\b", r"\bcurriculum vitae\b", r"\bwork experience\b", r"\beducation\b", r"\bskills\b", r"\bbachelor'?s degree\b", r"\bmaster'?s degree\b", r"\bphd\b", r"\bacademic\b", r"\blinkedin\b", r"\bgithub\b"]
    prop_keywords = [r"\bsurvey no\b", r"\bsale deed\b", r"\bkhata\b", r"\bencumbrance\b", r"\bschedule property\b", r"\bsub-registrar\b", r"\bpurchaser\b", r"\bvendor\b", r"\bstamp paper\b", r"\bmaster plan\b", r"\bmuda\b", r"\bpahani\b"]
    
    cv_count = sum(1 for w in cv_keywords if re.search(w, text_lower))
    prop_count = sum(1 for w in prop_keywords if re.search(w, text_lower))
    
    # If it strongly looks like a CV or has no real property keywords
    if cv_count >= 2 and prop_count == 0:
        fields["is_property_document"] = False
        fields["relevance_note"] = "Not a property document (appears to be a CV/Resume)."
    elif cv_count >= 3 and prop_count < 2:
        fields["is_property_document"] = False
        fields["relevance_note"] = "Not a property document (appears to be a CV/Resume)."
    elif prop_count == 0 and cv_count > 0:
        fields["is_property_document"] = False
        fields["relevance_note"] = "Not a property document."
        
    return fields


def extract_text_from_pdf_ocr(file_path: str) -> tuple[str, str]:
    """
    Extract text from a scanned PDF by converting pages to images and using OCR.
    Limits to first 3 pages.
    """
    text = ""
    try:
        import fitz
        import tempfile
        doc = fitz.open(file_path)
        pages = []
        for i in range(min(3, len(doc))):
            page = doc[i]
            pix = page.get_pixmap(dpi=150)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                pix.save(tmp_path)
                page_text, _ = extract_text_from_image(tmp_path)
                if page_text:
                    pages.append(page_text)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        doc.close()
        text = "\n".join(pages)
        return text.strip(), "pdf_ocr"
    except Exception as e:
        log.warning(f"PDF OCR failed: {e}")
        return "", f"pdf_ocr_error: {e}"


def extract_from_document(file_path: str, file_ext: str) -> dict:
    """
    Main extraction function. Routes to PDF or image extraction.
    Returns {text, fields, method, success, warnings}.
    """
    file_ext = file_ext.lower().lstrip(".")
    warnings = []

    if file_ext == "pdf":
        text, method = extract_text_from_pdf(file_path)
        if not text:
            warnings.append("No embedded text found. OCR required.")
            text, method = extract_text_from_pdf_ocr(file_path)
            if not text:
                warnings.append("OCR also returned no text. Document may be unreadable.")
    elif file_ext in ("jpg", "jpeg", "png"):
        text, method = extract_text_from_image(file_path)
        if not text:
            warnings.append(
                "OCR extraction returned no text. Tesseract may not be installed, "
                "or the image quality may be too low."
            )
    else:
        return {
            "success": False,
            "error": f"Unsupported file type: {file_ext}",
            "text": "",
            "fields": {},
            "method": "none",
            "warnings": [],
        }

    if not text:
        warnings.append("No text could be extracted from this document.")

    fields = extract_document_fields(text)

    return {
        "success": True,
        "text": text,
        "text_length": len(text),
        "fields": fields,
        "method": method,
        "warnings": warnings,
        "disclaimer": (
            "IMPORTANT: Extracted information is for reference only. "
            "This does NOT constitute legal verification of ownership, title, "
            "or authenticity. All legal documents must be independently verified "
            "through official government portals and/or a qualified legal professional."
        ),
    }


DEFAULT_VERIFICATION_ITEMS = [
    {"key": "seller_identity", "label": "Seller identity verified (with government ID)"},
    {"key": "survey_number", "label": "Survey number verified (Revenue Dept / Bhoomi)"},
    {"key": "rtc_pahani", "label": "RTC / Pahani records checked"},
    {"key": "encumbrance_cert", "label": "Encumbrance certificate (EC) obtained and verified"},
    {"key": "mutation_records", "label": "Mutation records (Khata) checked"},
    {"key": "land_conversion", "label": "Land conversion order verified (if applicable)"},
    {"key": "survey_boundaries", "label": "Survey boundaries / sketch verified"},
    {"key": "registration_details", "label": "Registration details verified at Sub-Registrar office"},
    {"key": "no_objection", "label": "No objection / litigation status verified"},
    {"key": "tax_receipts", "label": "Property tax receipts reviewed"},
]
