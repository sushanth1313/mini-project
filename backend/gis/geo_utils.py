"""
Centralized geographic consistency, boundary polygon validation,
taluk/locality normalization, and rule-based region classification
for Mysuru District, Karnataka.
"""
import json
import math
import os
import re
from typing import Optional, Tuple

_BOUNDARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mysuru_boundary.json")
_POLYGON_RING = None

# Canonical Mysuru District Taluk HQ coordinates (WGS-84)
TALUK_HQS = {
    "Mysuru":        (12.3052, 76.6552),
    "Nanjangud":     (12.1197, 76.6805),
    "Hunsur":        (12.3035, 76.2928),
    "HD Kote":       (12.0877, 76.3311),
    "T. Narasipura": (12.2135, 76.9028),
    "Periyapatna":   (12.3372, 76.0988),
    "K. R. Nagar":   (12.4385, 76.3827),
}

# Mapping from all common spellings/abbreviations to canonical ML & DB taluk name
TALUK_ALIASES = {
    "hd kote": "HD Kote",
    "h.d. kote": "HD Kote",
    "h d kote": "HD Kote",
    "h.d kote": "HD Kote",
    "heggadadevanakote": "HD Kote",
    "hunsur": "Hunsur",
    "hunasuru": "Hunsur",
    "kr nagar": "K. R. Nagar",
    "k.r. nagar": "K. R. Nagar",
    "k. r. nagar": "K. R. Nagar",
    "k r nagar": "K. R. Nagar",
    "krishnarajanagara": "K. R. Nagar",
    "krishnaraja nagar": "K. R. Nagar",
    "mysuru": "Mysuru",
    "mysore": "Mysuru",
    "mysuru rural": "Mysuru",
    "nanjangud": "Nanjangud",
    "nanjanagudu": "Nanjangud",
    "periyapatna": "Periyapatna",
    "piriyapattana": "Periyapatna",
    "saragur": "HD Kote",
    "saraguru": "HD Kote",
    "saligrama": "K. R. Nagar",
    "t narsipura": "T. Narasipura",
    "t narasipura": "T. Narasipura",
    "t. narsipura": "T. Narasipura",
    "t. narasipura": "T. Narasipura",
    "t.narasipura": "T. Narasipura",
    "tirumakudalu narasipura": "T. Narasipura",
    "tirumakudal narasipura": "T. Narasipura",
}

# Unambiguous names sent to Nominatim geocoder for abbreviated taluks
GEOCODE_TALUK_NAMES = {
    "HD Kote": "Heggadadevanakote",
    "K. R. Nagar": "Krishnarajanagara",
    "T. Narasipura": "Tirumakudalu Narasipura",
    "Mysuru": "Mysuru",
    "Nanjangud": "Nanjangud",
    "Hunsur": "Hunsur",
    "Periyapatna": "Periyapatna",
}


def _load_polygon() -> list:
    global _POLYGON_RING
    if _POLYGON_RING is None:
        if os.path.exists(_BOUNDARY_PATH):
            with open(_BOUNDARY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _POLYGON_RING = data["coordinates"][0]
        else:
            _POLYGON_RING = []
    return _POLYGON_RING


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line Haversine distance in km (not road travel distance)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def is_in_mysuru_district(lat: float, lon: float) -> bool:
    """
    Validate coordinates against the simplified OSM Mysuru District boundary polygon.
    Falls back to strict Mysuru lat/lon bounds only if boundary file is absent.
    Never silently modifies negative coordinates.
    """
    if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if lat <= 0 or not (11.6 <= lat <= 12.8 and 75.8 <= lon <= 77.4):
        return False

    ring = _load_polygon()
    if not ring:
        return True

    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def normalize_taluk(val: Optional[str]) -> str:
    """Return canonical Mysuru district taluk name (strips OSM 'taluk'/'taluku' suffixes)."""
    if not val:
        return "Mysuru"
    s = re.sub(r"\s+", " ", str(val).strip())
    s_clean = re.sub(r"\s+taluk[au]?$", "", s, flags=re.IGNORECASE).strip()
    return TALUK_ALIASES.get(s_clean.lower(), TALUK_ALIASES.get(s.lower(), s_clean))


def normalize_locality(val: Optional[str]) -> str:
    """Normalize locality text for matching without mutating user-visible display."""
    s = str(val or "").strip().lower()
    s = re.sub(r",\s*(mysuru|mysore|karnataka|india).*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_coordinate_status(status: Optional[str], default: str = "LOCALITY_CENTROID") -> str:
    """
    Distinguish coordinate origins without mislabeling approximate inputs as surveyed GPS:
      - SURVEY_GPS / SURVEYED / EXACT: user-certified surveyed/DGPS parcel coordinates
      - USER_ENTERED: raw coordinates manually entered by user (not independently verified)
      - MAP_SELECTED: user-pinned/dragged coordinates on interactive map
      - DEVICE_GPS / BROWSER_GPS: device/browser geolocation API coordinates
      - GEOCODED / LOCALITY_GEOCODE: auto-geocoded via search/Nominatim
      - LOCALITY_CENTROID: approximate village/locality centre
    """
    raw = str(status or "").strip().upper()
    if raw in ("SURVEY_GPS", "SURVEYED", "EXACT_PARCEL", "EXACT", "DGPS"):
        return raw if raw == "SURVEY_GPS" else "SURVEY_GPS"
    if raw == "USER_ENTERED":
        return "USER_ENTERED"
    if raw in ("MAP_SELECTED", "USER_MAP", "PIN_SELECTED"):
        return "MAP_SELECTED"
    if raw in ("DEVICE_GPS", "BROWSER_GPS", "GEOLOCATION"):
        return raw if raw == "BROWSER_GPS" else "DEVICE_GPS"
    if raw in ("GEOCODED", "LOCALITY_GEOCODE"):
        return "GEOCODED"
    if raw == "LOCALITY_CENTROID":
        return "LOCALITY_CENTROID"
    return default


def format_coordinate_precision_label(status: Optional[str]) -> str:
    """Human-readable display string exposing exact coordinate precision tier."""
    st = str(status or "LOCALITY_CENTROID").strip().upper()
    mapping = {
        "SURVEY_GPS": "SURVEY_GPS (Certified Surveyed / DGPS Coordinates)",
        "SURVEYED": "SURVEY_GPS (Certified Surveyed / DGPS Coordinates)",
        "EXACT": "SURVEY_GPS (Certified Surveyed / DGPS Coordinates)",
        "EXACT_PARCEL": "SURVEY_GPS (Certified Surveyed / DGPS Coordinates)",
        "MAP_SELECTED": "MAP_SELECTED (User-Pinned / Dragged Map Marker)",
        "DEVICE_GPS": "DEVICE_GPS (Explicit Browser/Device Geolocation)",
        "BROWSER_GPS": "DEVICE_GPS (Explicit Browser/Device Geolocation)",
        "GEOCODED": "GEOCODED (Address / Place Search Geocoded)",
        "LOCALITY_GEOCODE": "GEOCODED (Locality Geocoded)",
        "USER_ENTERED": "USER_ENTERED (Manually Typed Coordinates — Unverified)",
        "LOCALITY_CENTROID": "LOCALITY_CENTROID (Approximate Locality Centre)",
    }
    return mapping.get(st, st)


def classify_region_type(
    taluk: Optional[str] = None,
    village_or_locality: Optional[str] = None,
    land_type: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    explicit_region_type: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Consistently classify region into ('Urban' | 'Peri-urban' | 'Rural', explanation).
    Does NOT classify based solely on taluk name and does NOT hardcode individual localities.

    Rules when explicit_region_type is absent / 'Auto' / 'Unknown':
      1. Agricultural/Farm land type -> 'Rural'
      2. Explicit administrative 'village' designation in locality -> 'Rural'
      3. Within 8.0 km of Mysuru City Corporation centre (12.3052, 76.6552) -> 'Urban'
      4. Within 8.0–16.0 km of Mysuru centre OR within 3.0 km of any Taluk HQ municipal town -> 'Peri-urban'
      5. Otherwise -> 'Rural'
    """
    exp = str(explicit_region_type or "").strip()
    exp_low = exp.lower()
    if exp_low in ("urban",):
        return "Urban", "User-specified Urban region classification."
    if exp_low in ("peri-urban", "periurban", "suburban", "semi-urban", "town", "urban/peri-urban"):
        return "Peri-urban", "User-specified Peri-urban / Town region classification."
    if exp_low in ("rural", "rural/agricultural", "agricultural"):
        return "Rural", "User-specified Rural region classification."

    lt_low = str(land_type or "").strip().lower()
    loc_low = normalize_locality(village_or_locality)

    if "agri" in lt_low or "farm" in lt_low:
        return "Rural", "Classified as Rural based on Agricultural/Farm land type."

    if "village" in loc_low or "grama" in loc_low:
        return "Rural", "Classified as Rural based on administrative Village designation."

    if lat is not None and lon is not None and math.isfinite(lat) and math.isfinite(lon):
        dist_mysuru = haversine_km(lat, lon, *TALUK_HQS["Mysuru"])
        min_taluk_dist = min(haversine_km(lat, lon, hlat, hlon) for hlat, hlon in TALUK_HQS.values())

        if dist_mysuru <= 8.0:
            return "Urban", f"Classified as Urban ({dist_mysuru:.1f} km from Mysuru urban core)."
        if dist_mysuru <= 16.0 or min_taluk_dist <= 3.0:
            return (
                "Peri-urban",
                f"Classified as Peri-urban ({dist_mysuru:.1f} km from Mysuru core; "
                f"{min_taluk_dist:.1f} km from nearest taluk municipal centre)."
            )
        return (
            "Rural",
            f"Classified as Rural ({dist_mysuru:.1f} km from Mysuru core; "
            f"{min_taluk_dist:.1f} km from nearest taluk municipal centre)."
        )

    # Coordinate-free fallback: never assume all of Mysuru taluk is Urban
    if any(k in loc_low for k in ("stage", "block", "layout", "nagar", "mohalla", "puram")):
        return "Urban", "Classified as Urban based on urban layout/extension nomenclature."
    if "town" in loc_low:
        return "Peri-urban", "Classified as Peri-urban based on municipal town designation."
    return "Rural", "Classified as Rural (no urban/town indicators or coordinates provided)."


def to_ml_region_label(region_type: Optional[str]) -> str:
    """Map UI/canonical region ('Urban', 'Peri-urban', 'Rural') cleanly for the 3-tier ML schema."""
    low = str(region_type or "").strip().lower()
    if low == "urban":
        return "Urban"
    if low in ("peri-urban", "periurban", "suburban", "semi-urban", "town"):
        return "Peri-urban"
    if low in ("rural", "rural/agricultural", "agricultural"):
        return "Rural"
    if low == "urban/peri-urban":
        return "Urban/Peri-urban"
    return str(region_type or "Unknown").strip() or "Unknown"
