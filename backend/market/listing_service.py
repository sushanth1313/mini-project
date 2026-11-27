"""
Market Listing Service — Smart Land Valuation System.

Retrieves live comparable property listings using ONLY permitted public endpoints
(respecting robots.txt; never bypassing HTTP 403/406 or anti-bot protections),
alongside clearly separated historical dataset comparables for reference.

Permitted Live Source:
  - MagicBricks public location listing pages (`/*-mysore-pppfs`), allowed by
    https://www.magicbricks.com/robots.txt (structured SSR state JSON).
Non-scraped / Policy-Respected Portals:
  - 99acres (returns HTTP 403) and Housing.com (returns HTTP 406) are NOT scraped
    and are recorded honestly as restricted for automated server queries.

IMPORTANT CONSTRAINTS:
- Zero fabricated prices, listings, or URLs.
- All online portal prices are labelled as:
  "Advertised asking prices only, not verified registered sale transactions."
- Market benchmark is computed only if >= MIN_COMPARABLES (3) valid comparables
  remain after IQR outlier filtering.
"""

import difflib
import json
import logging
import math
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

MIN_COMPARABLES = 3
_LISTING_CACHE: dict = {}
_LISTING_CACHE_MAX = 24
_CACHE_TTL_SECONDS = 3600  # 1 hour

_UA = "SmartLandEvaluation/1.0 (VTU Academic Research Project)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _cache_key(
    locality: str, taluk: str, land_type: str, listing_type: str, area: Optional[float],
    lat: Optional[float] = None, lon: Optional[float] = None,
) -> str:
    bucket = int(round((area or 0) / 500.0))
    coord_part = f"{round(float(lat), 3)},{round(float(lon), 3)}" if (lat is not None and lon is not None) else "nocoord"
    return f"{locality.lower()}|{taluk.lower()}|{land_type.lower()}|{listing_type.lower()}|{bucket}|{coord_part}"


def _is_cache_valid(entry: dict) -> bool:
    try:
        ts = entry.get("retrieved_at", "")
        dt = datetime.fromisoformat(ts)
        return (datetime.now(timezone.utc) - dt).total_seconds() < _CACHE_TTL_SECONDS
    except Exception:
        return False


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9\s-]", " ", str(text or "").lower()).strip()
    s = re.sub(r"\s+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def _mb_category_prefix(land_type: str) -> str:
    lt = str(land_type or "").lower()
    if "agri" in lt or "farm" in lt:
        return "agricultural-land-for-sale-in"
    if "comm" in lt:
        return "commercial-land-for-sale-in"
    return "residential-plots-land-for-sale-in"


def _build_mb_slug_candidates(locality: str, taluk: str, land_type: str) -> list[str]:
    """Generate clean, non-hardcoded MagicBricks URL slug candidates for Mysuru localities/taluks."""
    from gis.geo_utils import normalize_taluk, GEOCODE_TALUK_NAMES

    prefix = _mb_category_prefix(land_type)
    canon_t = normalize_taluk(taluk)
    t_full = GEOCODE_TALUK_NAMES.get(canon_t, canon_t)

    loc_raw = (locality or "").strip()
    variants = []
    if loc_raw:
        variants.append(loc_raw)
        # Phonetic Karnataka variants (e.g. Sathagalli / Satagalli, Nanjanagudu / Nanjangud)
        de_asp = re.sub(r"([bcdgkpt])h", r"\1", loc_raw, flags=re.IGNORECASE)
        if de_asp.lower() != loc_raw.lower():
            variants.append(de_asp)
        ep_a = re.sub(r"([bcdfgjklmnpqrstvwxyz])(galli|halli|pura)\b", r"\1a\2", loc_raw, flags=re.IGNORECASE)
        if ep_a.lower() != loc_raw.lower():
            variants.append(ep_a)

    slug_list = []
    seen = set()

    def _add(slug: str):
        if slug and slug not in seen:
            seen.add(slug)
            slug_list.append(slug)

    for v in variants:
        sl = _slugify(v)
        if sl and sl not in ("mysuru", "mysore"):
            _add(f"{prefix}-{sl}-mysore-pppfs")
            if "stage" not in sl:
                _add(f"{prefix}-{sl}-1st-stage-mysore-pppfs")
                _add(f"{prefix}-{sl}-4th-stage-mysore-pppfs")

    # Taluk HQ / corridor slugs when locality != taluk
    for tv in (canon_t, t_full):
        tsl = _slugify(tv)
        if tsl and tsl not in ("mysuru", "mysore"):
            _add(f"{prefix}-{tsl}-mysore-pppfs")
            _add(f"{prefix}-{tsl}-road-mysore-pppfs")
            if "narasipura" in tsl:
                _add(f"{prefix}-{tsl.replace('narasipura', 'narsipura')}-road-mysore-pppfs")
            if tsl == "hd-kote":
                _add(f"{prefix}-hd-kote-road-mysore-pppfs")

    # District fallback slug
    _add(f"{prefix}-mysore-pppfs")
    return slug_list


def _fetch_mb_page(slug: str) -> tuple[str, list[dict], str]:
    """Fetch and parse window.SERVER_PRELOADED_STATE_.searchResult from MagicBricks."""
    url = f"https://www.magicbricks.com/{slug}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "text/html,application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status != 200:
                return "HTTP_ERROR", [], url
            html = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as he:
        return f"HTTP_{he.code}", [], url
    except Exception as e:
        log.debug(f"MagicBricks fetch failed for {url}: {e}")
        return "UNAVAILABLE", [], url

    low = html.lower()
    if any(w in low for w in ("captcha", "verify you are human", "attention required", "just a moment")):
        return "BLOCKED_BY_CHALLENGE", [], url

    m = re.search(r"window\.SERVER_PRELOADED_STATE_\s*=\s*(\{.*?\})\s*;\s*</script>", html, re.S)
    if not m:
        return "PARSE_EMPTY", [], url

    try:
        raw_json = m.group(1).replace("\\u002F", "/")
        state = json.loads(raw_json)
        items = state.get("searchResult", []) or []
        return "OK", items, url
    except Exception as e:
        log.debug(f"MagicBricks JSON parse error for {slug}: {e}")
        return "PARSE_ERROR", [], url


def _normalize_mb_listing(
    item: dict,
    fallback_loc: str,
    land_type: str,
    target_lat: Optional[float],
    target_lon: Optional[float],
    search_url: str,
) -> Optional[dict]:
    """Convert one MagicBricks searchResult dict into a standardized comparable dict."""
    try:
        price = float(item.get("price") or 0)
        if price <= 0:
            return None

        unit = str(item.get("landAreaUnitD") or "Sq-ft").strip()
        raw_area = item.get("caSqFt") or item.get("coveredArea") or item.get("plotArea") or item.get("la")
        sqFtPrice_raw = float(item.get("sqFtPrice") or 0)

        desc = str(item.get("seoDesc") or item.get("scdpropdescmbl") or "")
        url_slug = str(item.get("url") or "")
        area_sqft = float(raw_area) if raw_area else None

        # Override unit when MagicBricks URL/desc indicates Sq-yrd / Acre / Guntha despite Sq-ft tag
        url_desc_low = f"{url_slug} {desc}".lower()
        if "sq-yrd" in url_desc_low or "sq.yrd" in url_desc_low or "sq yd" in url_desc_low:
            unit = "Sq-yrd"
        elif "-acre" in url_slug.lower() or " acre" in desc.lower():
            unit = "Acre"
        elif "-guntha" in url_slug.lower() or " guntha" in desc.lower():
            unit = "Guntha"

        if area_sqft is None:
            m_desc = re.search(r"spans\s+(\d+(?:\.\d+)?)", desc, re.I)
            if m_desc and unit.lower() in ("sq-ft", "sqft", "sq ft"):
                area_sqft = float(m_desc.group(1))
        if area_sqft is None:
            m_url_sq = re.search(r"^(\d+(?:\.\d+)?)-Sq-ft", url_slug, re.I)
            m_url_yd = re.search(r"^(\d+(?:\.\d+)?)-Sq-yrd", url_slug, re.I)
            m_url_ac = re.search(r"^(\d+(?:\.\d+)?)-Acre", url_slug, re.I)
            m_url_gu = re.search(r"^(\d+(?:\.\d+)?)-Guntha", url_slug, re.I)
            if m_url_sq:
                area_sqft = float(m_url_sq.group(1))
            elif m_url_yd:
                area_sqft = float(m_url_yd.group(1)) * 9.0
            elif m_url_ac:
                area_sqft = float(m_url_ac.group(1)) * 43560.0
            elif m_url_gu:
                area_sqft = float(m_url_gu.group(1)) * 1089.0
        if area_sqft is None and sqFtPrice_raw > 0:
            area_sqft = round(price / sqFtPrice_raw, 0)

        psf = round(price / area_sqft, 0) if (area_sqft and area_sqft > 0) else (round(sqFtPrice_raw, 0) if sqFtPrice_raw > 0 else None)
        if not psf or psf <= 0:
            return None

        loc_name = str(item.get("lmtDName") or item.get("urlLocName") or fallback_loc or "Mysuru").strip()
        trans_raw = str(item.get("transactionTypeD") or item.get("transType") or "Unknown").strip()
        if "new" in trans_raw.lower():
            listing_cat = "New Sale / Builder"
        elif "resale" in trans_raw.lower():
            listing_cat = "Resale"
        else:
            listing_cat = trans_raw

        p_lat = item.get("pmtLat")
        p_lon = item.get("pmtLong")
        dist_km = None
        if target_lat and target_lon and p_lat and p_lon and float(p_lat) > 0 and float(p_lon) > 0:
            dist_km = round(_haversine_km(target_lat, target_lon, float(p_lat), float(p_lon)), 2)

        detail_url = f"https://www.magicbricks.com/propertyDetails/{url_slug}" if url_slug else search_url
        posted_dt = str(item.get("postDateT") or item.get("lastAccessDate") or "")[:10]

        unit_note = f"Area unit: {unit}." if unit.lower() not in ("sq-ft", "sqft", "sq ft") else ""
        return {
            "source": "MagicBricks",
            "source_type": "live_portal",
            "source_url": detail_url,
            "search_url": search_url,
            "price_per_sqft": float(psf),
            "total_price_inr": float(price),
            "land_area_sqft": float(round(area_sqft, 1)) if area_sqft else None,
            "area_unit": unit,
            "listing_type": listing_cat,
            "locality": loc_name,
            "land_type": str(item.get("propTypeD") or land_type),
            "distance_from_target_km": dist_km,
            "posted_date": posted_dt or None,
            "retrieval_date": _now_iso(),
            "is_verified_transaction": False,
            "note": f"Advertised asking price only (not verified transaction). {unit_note}".strip(),
        }
    except Exception:
        return None


def _fetch_live_magicbricks(
    locality: str,
    taluk: str,
    land_type: str,
    land_area_sqft: Optional[float],
    lat: Optional[float],
    lon: Optional[float],
) -> tuple[list[dict], list[str], str]:
    """
    Query permitted MagicBricks locality/taluk/district search pages.
    Returns (listings, search_urls_checked, scope_note).
    """
    slugs = _build_mb_slug_candidates(locality, taluk, land_type)
    loc_low = str(locality or "").strip().lower()
    taluk_low = str(taluk or "").strip().lower()

    matched_listings = []
    urls_used = []
    seen_urls = set()
    scope = "NO_LIVE_MATCH"

    import concurrent.futures as _cf
    candidate_slugs = slugs[:4]
    fetched_pages = {}
    pool = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="mb_fetch")
    try:
        fut_map = {pool.submit(_fetch_mb_page, sl): sl for sl in candidate_slugs}
        done, _ = _cf.wait(fut_map.keys(), timeout=6)
        for fut in done:
            sl = fut_map[fut]
            try:
                fetched_pages[sl] = fut.result()
            except Exception:
                pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    for slug in candidate_slugs:
        status, items, url = fetched_pages.get(slug, ("TIMEOUT", [], ""))
        if status != "OK" or not items:
            continue

        urls_used.append(url)
        is_district_wide = slug.endswith("-in-mysore-pppfs")

        for item in items:
            parsed = _normalize_mb_listing(item, locality, land_type, lat, lon, url)
            if not parsed:
                continue
            if parsed["source_url"] in seen_urls:
                continue
            # Reject gross plot-size mismatches (e.g. 10,800 sq.ft vs 1,200 sq.ft plot)
            if not _is_area_compatible(parsed.get("land_area_sqft"), land_area_sqft, land_type):
                continue

            item_loc_low = parsed["locality"].lower()
            dist_km = parsed.get("distance_from_target_km")

            # On district-wide page, ONLY accept items matching locality/taluk name OR within 12 km radius
            if is_district_wide:
                loc_match = bool(
                    loc_low and (
                        loc_low in item_loc_low
                        or item_loc_low in loc_low
                        or difflib.SequenceMatcher(None, loc_low, item_loc_low).ratio() >= 0.78
                    )
                )
                taluk_match = bool(taluk_low and taluk_low != "mysuru" and taluk_low in item_loc_low)
                near_geo = (dist_km is not None and dist_km <= 12.0)
                if not (loc_match or taluk_match or near_geo):
                    continue

            seen_urls.add(parsed["source_url"])
            matched_listings.append(parsed)

        if len(matched_listings) >= 4 and not is_district_wide:
            scope = "EXACT_LOCALITY_OR_CORRIDOR"
            break
        elif matched_listings and scope == "NO_LIVE_MATCH":
            scope = "DISTRICT_GEO_FILTERED" if is_district_wide else "EXACT_LOCALITY_OR_CORRIDOR"

    return matched_listings, urls_used, scope


def _is_area_compatible(cand_area: Optional[float], target_area: Optional[float], land_type: str = "") -> bool:
    """Rejects gross plot-size mismatches (e.g., 1,200 sq.ft plot vs 10,500+ sq.ft / acre parcel)."""
    if not target_area or target_area <= 0:
        return True
    if not cand_area or float(cand_area) <= 0:
        return False
    ratio = float(cand_area) / float(target_area)
    if target_area <= 10000:
        return 0.35 <= ratio <= 3.0 and float(cand_area) <= 15000
    return 0.25 <= ratio <= 4.0


def _deduplicate_listings(listings: list[dict]) -> list[dict]:
    """Deduplicate identical portal/dataset listings cleanly across sources."""
    seen = set()
    unique = []
    for l in listings:
        loc_k = str(l.get("locality") or "").strip().lower()
        psf_k = round(float(l.get("price_per_sqft") or 0), -1)
        area_k = round(float(l.get("land_area_sqft") or 0), -1)
        lt_k = str(l.get("land_type") or "").strip().lower()[:6]
        sig = (l.get("source_type"), loc_k, psf_k, area_k, lt_k)
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(l)
    return unique


def _row_to_comparable(row, land_type: str, fallback_loc: str, tier_label: str, dist_km: Optional[float] = None) -> Optional[dict]:
    psf = row.get("price_per_sqft")
    area = row.get("land_area_sqft")
    if not psf or float(psf) <= 0:
        return None
    note = f"Historical dataset comparable ({tier_label}; indicative reference only — not a live transaction)."
    return {
        "source": "Historical Dataset",
        "source_type": "historical_dataset",
        "source_url": None,
        "price_per_sqft": round(float(psf), 0),
        "total_price_inr": round(float(psf) * float(area), 0) if _pd_valid(area) else None,
        "land_area_sqft": float(area) if _pd_valid(area) else None,
        "area_unit": "Sq-ft",
        "listing_type": str(row.get("listing_type", "Unknown")),
        "locality": str(row.get("village_or_locality", fallback_loc)),
        "land_type": str(row.get("land_type", land_type)),
        "distance_from_target_km": round(float(dist_km), 2) if dist_km is not None else None,
        "comparison_tier": tier_label,
        "retrieval_date": _now_iso(),
        "is_verified_transaction": False,
        "note": note,
    }


def _fetch_locality_dataset_comparables(
    locality: str,
    taluk: str,
    land_type: str,
    target_area_sqft: Optional[float] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> tuple[list[dict], str]:
    """
    Hierarchical historical dataset comparables (strictly same land_type — NEVER cross-contaminates):
      1. Exact normalized / fuzzy locality match
      2. Nearby localities within <= 8 km Haversine (when exact < 3)
      3. Same taluk fallback (only when nearby < 3; explicitly labelled)
    """
    try:
        from gis.geo_utils import normalize_locality
        from ml.lightweight import canonicalize_basic, load_dataset_comparables_rows

        rows = load_dataset_comparables_rows()
        if not rows:
            return [], "NONE"

        canon_taluk = canonicalize_basic("taluk", taluk)
        canon_lt = canonicalize_basic("land_type", land_type)
        loc_norm = normalize_locality(locality)

        same_lt_rows = [
            r for r in rows
            if canonicalize_basic("land_type", r.get("land_type")) == canon_lt
            or str(r.get("land_type") or "").strip() == canon_lt
        ]
        if not same_lt_rows:
            return [], "NO_SAME_TYPE_DATA"

        if target_area_sqft and target_area_sqft > 0:
            compat_rows = [
                r for r in same_lt_rows
                if _is_area_compatible(
                    float(r.get("land_area_sqft")) if _pd_valid(r.get("land_area_sqft")) else None,
                    target_area_sqft,
                    canon_lt,
                )
            ]
            if compat_rows:
                same_lt_rows = compat_rows

        exact_rows = [
            r for r in same_lt_rows
            if loc_norm and normalize_locality(str(r.get("village_or_locality") or "")) == loc_norm
        ]

        if not exact_rows and loc_norm:
            taluk_rows = [r for r in same_lt_rows if str(r.get("taluk") or "").strip() == canon_taluk]
            pool = taluk_rows if taluk_rows else same_lt_rows
            pool_norms = {
                n: str(r.get("village_or_locality") or "")
                for r in pool
                for n in (normalize_locality(str(r.get("village_or_locality") or "")),)
                if n
            }
            matches = difflib.get_close_matches(loc_norm, list(pool_norms.keys()), n=1, cutoff=0.78)
            if matches:
                exact_rows = [
                    r for r in pool
                    if normalize_locality(str(r.get("village_or_locality") or "")) == matches[0]
                ]

        collected = []
        for row in exact_rows:
            c = _row_to_comparable(row, canon_lt, locality, "EXACT_LOCALITY", dist_km=0.0)
            if c:
                collected.append(c)

        collected = _deduplicate_listings(collected)
        tier_used = "EXACT_LOCALITY" if collected else "NONE"

        # Tier 2: Nearby localities within 8 km Haversine of confirmed coordinates
        if len(collected) < MIN_COMPARABLES and lat is not None and lon is not None:
            nearby_rows = []
            for row in same_lt_rows:
                r_lat, r_lon = row.get("latitude"), row.get("longitude")
                if not (_pd_valid(r_lat) and _pd_valid(r_lon)):
                    continue
                dkm = _haversine_km(float(lat), float(lon), float(r_lat), float(r_lon))
                if 0.0 < dkm <= 8.0:
                    nearby_rows.append((dkm, row))
            nearby_rows.sort(key=lambda x: x[0])
            for dkm, row in nearby_rows[:10]:
                c = _row_to_comparable(row, canon_lt, locality, f"NEARBY_WITHIN_8KM ({dkm:.1f} km)", dist_km=dkm)
                if c:
                    collected.append(c)
            collected = _deduplicate_listings(collected)
            if collected and tier_used == "NONE":
                tier_used = "NEARBY_LOCALITIES_8KM"
            elif nearby_rows and tier_used == "EXACT_LOCALITY":
                tier_used = "EXACT_PLUS_NEARBY_8KM"

        # Tier 3: Same taluk fallback ONLY if exact + nearby < 3 (never district-wide mix)
        if len(collected) < MIN_COMPARABLES:
            taluk_only = [r for r in same_lt_rows if str(r.get("taluk") or "").strip() == canon_taluk][:8]
            for row in taluk_only:
                c = _row_to_comparable(row, canon_lt, locality, f"SAME_TALUK ({canon_taluk})")
                if c:
                    collected.append(c)
            collected = _deduplicate_listings(collected)
            if collected and tier_used == "NONE":
                tier_used = "SAME_TALUK_FALLBACK"

        return collected, tier_used
    except Exception as e:
        log.warning(f"Dataset comparable lookup failed: {e}")
        return [], "NONE"


def _pd_valid(v) -> bool:
    try:
        return v is not None and not math.isnan(float(v)) and float(v) > 0
    except Exception:
        return False


def compute_market_benchmark(
    listings: list[dict],
    target_area_sqft: Optional[float] = None,
    min_comparables: int = MIN_COMPARABLES,
) -> dict:
    """
    Compute market statistics and benchmark (only when >= min_comparables valid comparables exist).
    Separates Sq-ft / size-comparable plots and uses IQR outlier filtering when N >= 4.
    """
    valid = [l for l in listings if l.get("price_per_sqft") and l["price_per_sqft"] > 0]
    live_valid = [l for l in valid if l.get("source_type") == "live_portal"]
    hist_valid = [l for l in valid if l.get("source_type") == "historical_dataset"]

    # Prefer live portal listings when >= min_comparables exist; else combine with historical comparables
    pool = live_valid if len(live_valid) >= min_comparables else valid

    # Filter out unit-mismatch / oversized-acre outliers when evaluating standard plots (<= 10,000 sq.ft)
    if target_area_sqft and target_area_sqft <= 10000:
        sqft_like = [
            l for l in pool
            if str(l.get("area_unit", "Sq-ft")).lower() in ("sq-ft", "sqft", "sq ft")
            or (l.get("land_area_sqft") and l["land_area_sqft"] <= 15000)
        ]
        # Exclude Sq-yrd rows where raw Sq-ft unit mismatch skewed psf
        sqft_only = [
            l for l in pool
            if str(l.get("area_unit", "Sq-ft")).lower() in ("sq-ft", "sqft", "sq ft")
        ]
        if len(sqft_only) >= min_comparables:
            pool = sqft_only
        elif len(sqft_like) >= min_comparables:
            pool = sqft_like

    psf_vals = sorted([float(l["price_per_sqft"]) for l in pool])
    areas = sorted([float(l["land_area_sqft"]) for l in valid if l.get("land_area_sqft") and float(l["land_area_sqft"]) > 0])

    new_cnt = sum(1 for l in valid if "new" in str(l.get("listing_type", "")).lower())
    resale_cnt = sum(1 for l in valid if "resale" in str(l.get("listing_type", "")).lower())
    other_cnt = len(valid) - new_cnt - resale_cnt

    base_meta = {
        "total_listings": len(valid),
        "live_count": len(live_valid),
        "historical_count": len(hist_valid),
        "size_min_sqft": round(min(areas), 0) if areas else None,
        "size_max_sqft": round(max(areas), 0) if areas else None,
        "new_sale_count": new_cnt,
        "resale_count": resale_cnt,
        "other_listing_count": other_cnt,
        "min_required": min_comparables,
    }

    if len(psf_vals) < min_comparables:
        return {
            **base_meta,
            "status": "INSUFFICIENT_DATA",
            "count": len(psf_vals),
            "filtered_count": len(psf_vals),
            "market_benchmark_psf": None,
            "market_p25_psf": None,
            "market_p75_psf": None,
            "market_min_psf": round(min(psf_vals), 0) if psf_vals else None,
            "market_max_psf": round(max(psf_vals), 0) if psf_vals else None,
            "note": (
                f"Only {len(psf_vals)} comparable price point(s) found — minimum {min_comparables} "
                "required to compute a reliable market benchmark."
            ),
        }

    filtered = list(psf_vals)
    if len(psf_vals) >= 4:
        q1 = psf_vals[len(psf_vals) // 4]
        q3 = psf_vals[(3 * len(psf_vals)) // 4]
        iqr = q3 - q1
        iqr_filtered = [v for v in psf_vals if (q1 - 1.5 * iqr) <= v <= (q3 + 1.5 * iqr)]
        if len(iqr_filtered) >= min_comparables:
            filtered = sorted(iqr_filtered)

    med_psf = round(float(statistics.median(filtered)), 0)
    mean_psf = round(float(statistics.mean(filtered)), 0)

    src_desc = (
        f"{len(live_valid)} live portal listing(s)"
        if len(live_valid) >= min_comparables
        else f"{len(live_valid)} live listing(s) + {len(hist_valid)} historical dataset record(s)"
    )

    return {
        **base_meta,
        "status": "COMPUTED",
        "count": len(psf_vals),
        "filtered_count": len(filtered),
        "market_benchmark_psf": med_psf,
        "market_mean_psf": mean_psf,
        "market_p25_psf": round(filtered[len(filtered) // 4], 0),
        "market_p75_psf": round(filtered[(3 * len(filtered)) // 4], 0),
        "market_min_psf": round(min(filtered), 0),
        "market_max_psf": round(max(filtered), 0),
        "note": (
            f"Median benchmark ₹{med_psf:,.0f}/sq.ft from {len(filtered)} filtered comparables ({src_desc}). "
            "Online listings represent advertised asking prices only, not verified sale transactions."
        ),
    }


def fetch_market_listings(
    locality: str,
    taluk: str,
    land_type: str = "Residential",
    listing_type: str = "Resale",
    land_area_sqft: Optional[float] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> dict:
    """Fetch permitted live comparable listings + historical dataset references."""
    ck = _cache_key(locality, taluk, land_type, listing_type, land_area_sqft, lat=lat, lon=lon)
    if ck in _LISTING_CACHE and _is_cache_valid(_LISTING_CACHE[ck]):
        log.info(f"MarketListings cache hit for {locality}, {taluk}")
        return _LISTING_CACHE[ck]

    live_listings, mb_urls, mb_scope = _fetch_live_magicbricks(locality, taluk, land_type, land_area_sqft, lat, lon)
    live_listings = [
        l for l in _deduplicate_listings(live_listings)
        if _is_area_compatible(l.get("land_area_sqft"), land_area_sqft, land_type)
    ]
    dataset_listings, dataset_tier = _fetch_locality_dataset_comparables(
        locality, taluk, land_type, target_area_sqft=land_area_sqft, lat=lat, lon=lon
    )

    all_listings = _deduplicate_listings(live_listings + dataset_listings)
    sources_used = []
    if live_listings:
        sources_used.append("MagicBricks (Public Live Listings — Advertised Asking)")
    if dataset_listings:
        sources_used.append(f"Historical Dataset ({dataset_tier})")

    benchmark = compute_market_benchmark(all_listings, target_area_sqft=land_area_sqft, min_comparables=MIN_COMPARABLES)

    if not all_listings:
        status = "NO_LISTINGS"
    elif benchmark.get("status") != "COMPUTED":
        status = "PARTIAL"
    else:
        status = "SUCCESS"

    result = {
        "status": status,
        "scope": mb_scope,
        "dataset_comparison_tier": dataset_tier,
        "listings": all_listings[:20],
        "market_benchmark": benchmark,
        "total_count": len(all_listings),
        "live_count": len(live_listings),
        "historical_count": len(dataset_listings),
        "sources": sources_used,
        "source_urls": mb_urls,
        "restricted_sources": [
            "99acres (HTTP 403 automated access restricted)",
            "Housing.com (HTTP 406 automated access restricted)",
        ],
        "locality": locality,
        "taluk": taluk,
        "land_type": land_type,
        "listing_type": listing_type,
        "retrieved_at": _now_iso(),
        "disclaimer": (
            "All online portal prices are advertised asking prices only, not verified registered "
            "sale transactions. Historical dataset records are indicative references only. "
            "Consult a registered valuer for certified legal or financial valuation."
        ),
    }

    while len(_LISTING_CACHE) >= _LISTING_CACHE_MAX and ck not in _LISTING_CACHE:
        _LISTING_CACHE.pop(next(iter(_LISTING_CACHE)))
    _LISTING_CACHE[ck] = result
    return result
