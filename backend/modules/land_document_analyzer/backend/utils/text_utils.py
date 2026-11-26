"""Domain text normalization utilities: Karnataka land area units, name matching, date parsing."""
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional, Tuple

# Karnataka standard land area conversions to Square Feet
UNIT_TO_SQFT = {
    "sq.ft": 1.0,
    "sqft": 1.0,
    "sq ft": 1.0,
    "sft": 1.0,
    "square feet": 1.0,
    "square foot": 1.0,
    "sq.m": 10.7639104,
    "sqm": 10.7639104,
    "sq m": 10.7639104,
    "square meter": 10.7639104,
    "square meters": 10.7639104,
    "square metre": 10.7639104,
    "square metres": 10.7639104,
    "gunta": 1089.0,
    "guntas": 1089.0,
    "guntha": 1089.0,
    "gunthas": 1089.0,
    "acre": 43560.0,
    "acres": 43560.0,
    "cent": 435.6,
    "cents": 435.6,
    "hectare": 107639.104,
    "hectares": 107639.104,
}


def parse_area_to_sqft(area_text: Optional[str], default_unit_sqft: bool = False) -> Optional[float]:
    """
    Parses Karnataka land extent strings such as:
    - '1,200 sq.ft.'
    - '1200' (when default_unit_sqft=True for numeric reference fields)
    - '2 Acres 10 Guntas'
    - '111.48 sq.m'
    - '40 x 30 ft'
    Returns normalized area in sq.ft., or None if unparseable.
    """
    if area_text is None:
        return None
    text = str(area_text).lower().strip()
    if not text or text == "unable to extract":
        return None

    # Compound Acre + Gunta pattern (common in Karnataka RTC / Pahani)
    acre_gunta = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:acres?|ac\.?)\s*(?:and\s*)?(\d+(?:\.\d+)?)\s*(?:guntas?|gunthas?|g\.?)",
        text,
    )
    if acre_gunta:
        acres = float(acre_gunta.group(1))
        guntas = float(acre_gunta.group(2))
        return round(acres * 43560.0 + guntas * 1089.0, 2)

    # Dimension pattern e.g., 30 x 40 ft or 30ft x 40ft
    dims = re.search(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|')?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:ft|feet|')?", text)
    if dims and ("sq" not in text):
        return round(float(dims.group(1)) * float(dims.group(2)), 2)

    # Single value + unit
    match = re.search(
        r"(\d[\d,]*(?:\.\d+)?)\s*(sq\.?\s*ft\.?|sqft|sft|square\s*f(?:ee|oo)t|sq\.?\s*m\.?|sqm|square\s*met(?:er|re)s?|guntas?|gunthas?|acres?|cents?|hectares?)",
        text,
    )
    if match:
        val = float(match.group(1).replace(",", ""))
        unit_raw = re.sub(r"\s+", " ", match.group(2).strip().rstrip("."))
        factor = UNIT_TO_SQFT.get(unit_raw)
        if factor is None:
            unit_compact = unit_raw.replace(" ", "").replace(".", "")
            factor = UNIT_TO_SQFT.get(unit_compact)
        if factor:
            return round(val * factor, 2)

    # Bare numeric reference area e.g. '1200' or '1,200'
    if default_unit_sqft:
        bare = re.fullmatch(r"\s*(\d[\d,]*(?:\.\d+)?)\s*", text)
        if bare:
            return round(float(bare.group(1).replace(",", "")), 2)

    return None


def normalize_name(name: Optional[str]) -> str:
    """Normalizes person names by removing honorifics, punctuation, and extra spaces."""
    if not name or not isinstance(name, str):
        return ""
    cleaned = re.sub(r"\b(sri|smt|mr|mrs|ms|dr|late|shri|kumari)\.?\b", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(s/o|d/o|w/o|c/o)\b.*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def compare_names(name_a: Optional[str], name_b: Optional[str]) -> Tuple[str, float]:
    """
    Compares two person names.
    Returns (status, similarity_ratio) where status is one of:
    'Consistent', 'Spelling Variation', 'Mismatch', 'Insufficient Data'.
    """
    norm_a = normalize_name(name_a)
    norm_b = normalize_name(name_b)
    if not norm_a or not norm_b:
        return "Insufficient Data", 0.0
    if norm_a == norm_b:
        return "Consistent", 1.0

    # Token-sorted similarity handles initials or reordered family names
    tokens_a = " ".join(sorted(norm_a.split()))
    tokens_b = " ".join(sorted(norm_b.split()))
    ratio = max(
        SequenceMatcher(None, norm_a, norm_b).ratio(),
        SequenceMatcher(None, tokens_a, tokens_b).ratio(),
    )
    if ratio >= 0.78:
        return "Spelling Variation", round(ratio, 3)
    return "Mismatch", round(ratio, 3)


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parses common Indian and ISO date formats."""
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned = date_str.strip()
    if not cleaned or cleaned.lower() == "unable to extract":
        return None

    formats = (
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%b-%Y",
        "%d/%b/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def normalize_survey_number(value: Optional[str]) -> str:
    """Normalizes survey/hissa strings like 'Sy. No. 45 / 2A' -> '45/2a'."""
    if not value:
        return ""
    s = re.sub(r"(?i)(sy\.?\s*no\.?|survey\s*no\.?|s\.?\s*no\.?)", "", str(value))
    s = re.sub(r"\s+", "", s).strip().lower()
    return s
