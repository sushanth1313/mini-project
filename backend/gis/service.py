"""
GIS service: Overpass API queries + Haversine distance calculations.
Falls back gracefully if Overpass is unavailable.
"""
import math
import logging
import requests
from typing import Optional

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 45


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in kilometres between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _overpass_query(lat: float, lon: float, radius_m: int, node_type: str, tags: dict) -> list:
    """
    Generic Overpass QL query for nodes/ways near a point.
    Returns list of {name, lat, lon, distance_km}.
    """
    tag_filters = "".join(f'["{k}"="{v}"]' for k, v in tags.items())
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  node{tag_filters}(around:{radius_m},{lat},{lon});
  way{tag_filters}(around:{radius_m},{lat},{lon});
);
out center;
"""
    try:
        headers = {"User-Agent": "SmartLandEvaluation/1.0 (college-project)"}
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=OVERPASS_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        log.warning("Overpass API timeout")
        return []
    except Exception as e:
        log.warning(f"Overpass API error: {e}")
        return []

    results = []
    for elem in data.get("elements", []):
        if elem["type"] == "node":
            elat, elon = elem.get("lat"), elem.get("lon")
        elif elem["type"] == "way" and "center" in elem:
            elat, elon = elem["center"]["lat"], elem["center"]["lon"]
        else:
            continue
        if elat is None or elon is None:
            continue
        dist = haversine(lat, lon, elat, elon)
        name = elem.get("tags", {}).get("name", "")
        results.append({"name": name, "lat": elat, "lon": elon, "distance_km": round(dist, 3)})

    results.sort(key=lambda x: x["distance_km"])
    return results


FACILITY_QUERIES = {
    "school": ({"amenity": "school"}, 5000),
    "hospital": ({"amenity": "hospital"}, 5000),
    "clinic": ({"amenity": "clinic"}, 3000),
    "supermarket": ({"shop": "supermarket"}, 3000),
    "market": ({"amenity": "marketplace"}, 3000),
    "pharmacy": ({"amenity": "pharmacy"}, 3000),
    "bus_stop": ({"highway": "bus_stop"}, 3000),
    "railway_station": ({"railway": "station"}, 10000),
    "bank": ({"amenity": "bank"}, 3000),
    "police": ({"amenity": "police"}, 5000),
    "atm": ({"amenity": "atm"}, 2000),
    "park": ({"leisure": "park"}, 3000),
}


def get_nearby_facilities(lat: float, lon: float, overpass_url: str = OVERPASS_URL, timeout: int = OVERPASS_TIMEOUT, locality: str = "", district: str = "") -> dict:
    """
    Query multi-source GIS for facilities.
    Per-category status:
      SUCCESS          — query completed, ≥1 features found.
      NO_DATA          — query completed, 0 features found (not an error).
      SOURCE_UNAVAILABLE — query failed/timed out.
    """
    from .enrichment import LocationEnrichment, _is_generic_name
    from datetime import datetime, timezone
    
    from .adapters.osm import OVERPASS_ENDPOINTS
    orchestrator = LocationEnrichment()
    if overpass_url and overpass_url != OVERPASS_URL:
        orchestrator.osm.endpoints = [overpass_url] + [ep for ep in OVERPASS_ENDPOINTS if ep != overpass_url]
    orchestrator.osm.timeout = timeout
    
    facilities_response = orchestrator.get_facilities(lat, lon, radius_m=5000, locality=locality, district=district)
    facilities_data = facilities_response["data"]
    overall_status = facilities_response["status"]
    cat_status_map = facilities_response.get("category_status", {})

    results = {}
    for ftype, items in facilities_data.items():
        # Never pick a generic unnamed fallback ('Clinic / Medical Practice', etc.) as nearest
        # when an actual named facility was mapped within the search radius.
        named_items = [i for i in items if not _is_generic_name(i)]
        nearest = named_items[0] if named_items else (items[0] if items else None)
        count_1km = sum(1 for i in items if i.get("distance_km") is not None and i["distance_km"] <= 1.0)
        count_3km = sum(1 for i in items if i.get("distance_km") is not None and i["distance_km"] <= 3.0)
        count_5km = sum(1 for i in items if i.get("distance_km") is not None and i["distance_km"] <= 5.0)

        # Merge all sources to describe provenance
        sources_used = list(set([i.get("source") for i in items if i.get("source")]))

        per_status = cat_status_map.get(ftype)
        if not per_status:
            if overall_status == "SOURCE_UNAVAILABLE":
                per_status = "SOURCE_UNAVAILABLE"
            elif nearest is None:
                per_status = "NO_DATA"
            else:
                per_status = "SUCCESS"

        # Never report zero counts when source failed or incomplete without any results
        counts_reliable = per_status == "SUCCESS" or per_status == "NO_DATA" or (per_status == "PARTIAL" and nearest is not None)

        from .adapters.osm import FACILITY_CONFIG
        _, cat_default_r = FACILITY_CONFIG.get(ftype, ([], 5000))
        radius_km_used = max(5.0, cat_default_r / 1000.0)

        coverage_label = (
            "partial_nominatim_fallback" if per_status == "PARTIAL"
            else ("multi_source_poi" if any("ArcGIS" in s for s in sources_used) else ("complete_overpass" if per_status in ("SUCCESS", "NO_DATA") else "unavailable"))
        )

        results[ftype] = {
            "nearest": nearest,
            "nearest_distance_km": nearest["distance_km"] if nearest else None,
            "count_within_1km": count_1km if counts_reliable else None,
            "count_within_3km": count_3km if counts_reliable else None,
            "count_within_5km": count_5km if counts_reliable else None,
            "radius_km_searched": radius_km_used,
            "distance_type": "straight_line_haversine",
            "all_within_5km": [i for i in items if i.get("distance_km") is not None and i["distance_km"] <= 5.0][:15],
            "all_within_radius": items[:15],
            "source": " + ".join(sources_used) if sources_used else "OpenStreetMap",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "status": per_status,
            "coverage": coverage_label,
        }

    return results


def check_gis_sources():
    from .enrichment import LocationEnrichment
    return LocationEnrichment().check_sources()

def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


import threading
import time as _time

FORWARD_GEOCODE_CACHE = {}
REVERSE_GEOCODE_CACHE = {}
LOCATION_SEARCH_CACHE = {}
_NOMINATIM_SEARCH_LOCK = threading.Lock()
_LAST_NOMINATIM_SEARCH_TS = 0.0


def _general_locality_variants(name: str) -> list[str]:
    """
    Generate general Karnataka/Indian transliteration fallback spellings for Nominatim
    when the exact query string fails (no hardcoded locality names):
      - Dataset close spelling match (cutoff >= 0.78)
      - Aspirated consonant normalization (th->t, dh->d, bh->b, gh->g, kh->k, ph->p)
      - Epenthetic vowel before -galli / -halli / -pura (e.g. Sathgalli -> Satagalli)
    """
    import difflib
    import re
    from .geo_utils import normalize_locality

    base = (name or "").strip()
    if not base:
        return []

    seen = set()
    variants = []

    def _add(cand: str):
        c = (cand or "").strip()
        cl = c.lower()
        if c and cl not in seen:
            seen.add(cl)
            variants.append(c)

    _add(base)

    # Check training dataset for closest known spelling (e.g. 'sathgall' -> 'Sathgalli')
    try:
        from ml.predict import _load_train_df
        df = _load_train_df()
        if not df.empty:
            norms = {}
            for orig in df["village_or_locality"].dropna().astype(str):
                n = normalize_locality(orig)
                if n and n not in norms:
                    norms[n] = orig.strip()
            matches = difflib.get_close_matches(normalize_locality(base), list(norms.keys()), n=1, cutoff=0.76)
            if matches:
                _add(norms[matches[0]])
    except Exception:
        pass

    # Generate general phonetic/epenthetic candidates from each candidate found so far
    for s in list(variants):
        de_asp = re.sub(r"([bcdgkpt])h", r"\1", s, flags=re.IGNORECASE)
        _add(de_asp)
        ep_a = re.sub(r"([bcdfgjklmnpqrstvwxyz])(galli|halli|pura)\b", r"\1a\2", s, flags=re.IGNORECASE)
        _add(ep_a)
        ep_de_asp = re.sub(r"([bcdfgjklmnpqrstvwxyz])(galli|halli|pura)\b", r"\1a\2", de_asp, flags=re.IGNORECASE)
        _add(ep_de_asp)

    return variants


def geocode_locality(village: str, taluk: str, district: str = "Mysuru") -> Optional[dict]:
    """
    Forward-geocode a locality within Mysuru District using:
      1. Google Geocoding API (when GOOGLE_MAPS_API_KEY is configured)
      2. Authoritative KGIS village boundary interior point
      3. Nominatim/OSM fallback
    Validates coordinates fall inside the actual Mysuru District boundary polygon.
    """
    from .geo_utils import normalize_taluk, normalize_locality, GEOCODE_TALUK_NAMES, is_in_mysuru_district
    from .adapters.google import google_geocode_locality, get_google_maps_api_key
    from .kgis_boundaries import search_kgis_villages

    t_canon = normalize_taluk(taluk)
    t_query = GEOCODE_TALUK_NAMES.get(t_canon, t_canon)
    v_canon = normalize_taluk(village)
    v_query = GEOCODE_TALUK_NAMES.get(v_canon, village)
    has_gkey = bool(get_google_maps_api_key())
    cache_key = (normalize_locality(v_query), t_canon, (district or "Mysuru").strip().lower(), has_gkey)
    if cache_key in FORWARD_GEOCODE_CACHE:
        return FORWARD_GEOCODE_CACHE[cache_key]

    # 1. Exact KGIS revenue village match (authoritative free local boundary — zero API cost)
    try:
        v_norm_target = normalize_locality(v_query)
        for kv in search_kgis_villages(v_query, limit=8):
            if normalize_locality(kv["locality"]) == v_norm_target and normalize_taluk(kv.get("taluk") or "") == t_canon:
                res = {
                    "lat": kv["latitude"],
                    "lon": kv["longitude"],
                    "display_name": f"{kv['locality']}, {t_canon} Taluk, {district} District, Karnataka",
                    "matched_name": kv["locality"],
                    "coordinate_status": "LOCALITY_GEOCODE",
                    "coordinate_source": "Karnataka GIS (KGIS)",
                }
                FORWARD_GEOCODE_CACHE[cache_key] = res
                return res
    except Exception:
        pass

    # 2. Free Photon (OSM-backed) forward geocode inside Mysuru District
    for var in _general_locality_variants(v_query)[:2]:
        try:
            ph_resp = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": f"{var}, {t_query}, Mysuru", "lat": 12.3052, "lon": 76.6552, "limit": 5},
                headers={"User-Agent": "SmartLandEvaluation/1.0"},
                timeout=4,
            )
            if ph_resp.status_code == 200:
                for feat in (ph_resp.json() or {}).get("features", []):
                    coords = (feat.get("geometry") or {}).get("coordinates") or []
                    if len(coords) >= 2:
                        lon_v, lat_v = float(coords[0]), float(coords[1])
                        if is_in_mysuru_district(lat_v, lon_v):
                            props = feat.get("properties") or {}
                            res = {
                                "lat": lat_v,
                                "lon": lon_v,
                                "display_name": ", ".join(p for p in [props.get("name"), props.get("city") or props.get("county"), "Mysuru, Karnataka"] if p),
                                "matched_name": var,
                                "coordinate_status": "LOCALITY_GEOCODE",
                                "coordinate_source": "Photon/OSM",
                            }
                            FORWARD_GEOCODE_CACHE[cache_key] = res
                            return res
        except Exception:
            pass

    # 3. Policy-compliant Nominatim/OSM fallback
    variants = _general_locality_variants(v_query)
    queries = []
    for var in variants:
        queries.append((var, f"{var}, {t_query}, {district}, Karnataka, India"))
    for var in variants[:2]:
        queries.append((var, f"{var}, {district} District, Karnataka, India"))

    url = "https://nominatim.openstreetmap.org/search"
    for matched_var, query in queries:
        try:
            resp = requests.get(
                url,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 5,
                    "viewbox": "75.8,12.8,77.4,11.6",
                },
                headers={"User-Agent": "SmartLandEvaluation/1.0 (college-project)"},
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data:
                lat_v, lon_v = float(item["lat"]), float(item["lon"])
                if is_in_mysuru_district(lat_v, lon_v):
                    res = {
                        "lat": lat_v,
                        "lon": lon_v,
                        "display_name": item.get("display_name", ""),
                        "matched_name": matched_var,
                        "coordinate_status": "LOCALITY_GEOCODE",
                        "coordinate_source": "Nominatim/OSM",
                    }
                    FORWARD_GEOCODE_CACHE[cache_key] = res
                    return res
        except Exception as e:
            log.warning(f"Nominatim geocode failed for '{query}': {e}")

    # 4. Optional Google Geocoding API ONLY when explicitly enabled & free providers had no hit
    if has_gkey:
        g_res = google_geocode_locality(v_query, t_query, district)
        if g_res:
            FORWARD_GEOCODE_CACHE[cache_key] = g_res
            return g_res
    return None


def _appropriate_zoom_for_osm_item(item: dict) -> int:
    otype = (item.get("type") or item.get("addresstype") or "").lower()
    oclass = (item.get("class") or "").lower()
    if otype in ("house", "building", "residential", "road", "street", "tertiary", "secondary", "primary") or oclass in ("amenity", "highway", "building", "shop"):
        return 17
    if otype in ("neighbourhood", "suburb", "quarter", "city_district"):
        return 15
    if otype in ("village", "hamlet"):
        return 14
    if otype in ("town", "city"):
        return 13
    if otype in ("county", "administrative", "state_district") or oclass == "boundary":
        return 12
    return 15


def _enrich_suggestion_with_kgis(lat_v: float, lon_v: float, fallback_loc: str, fallback_taluk: str) -> tuple:
    """
    Anchor every place/search result strictly to the smallest reliable official KGIS boundary
    polygon containing (lat_v, lon_v). Prevents bloated external polygons (e.g. OSM tagging
    Sathagalli coordinates as Kyathamaranahalli) or legacy broad villages from masking neighbourhoods.
    """
    from .geo_utils import normalize_taluk, TALUK_HQS
    from .kgis_boundaries import lookup_kgis_location

    kgis = lookup_kgis_location(lat_v, lon_v)
    kt_raw = kgis.get("kgis_taluk")
    kt_norm = normalize_taluk(kt_raw) if kt_raw else None
    canon_taluk = kt_norm if kt_norm in TALUK_HQS else fallback_taluk
    if kgis.get("overlap_detected"):
        canon_loc = kgis.get("ward_name") or fallback_loc or "Locality Requires Verification"
    else:
        canon_loc = kgis.get("smallest_locality") or kgis.get("revenue_village_display") or kgis.get("ward_name") or fallback_loc
    return canon_loc, canon_taluk, kgis


def search_locations(query: str, limit: int = 8) -> dict:
    """
    Search places, villages, wards, localities, streets, and taluks inside Mysuru District.
    Priority:
      1. Google Places API (when GOOGLE_MAPS_API_KEY is configured)
      2. Authoritative KGIS Revenue Villages & Municipal Wards
      3. Nominatim/OSM fallback
    Every suggestion's locality/taluk is anchored to the KGIS boundary polygon containing its coordinates.
    """
    from .geo_utils import is_in_mysuru_district, normalize_locality, normalize_taluk, TALUK_HQS
    from .adapters.google import google_places_search, get_google_maps_api_key
    from .kgis_boundaries import search_kgis_villages, search_kgis_wards

    q_clean = " ".join((query or "").strip().split())
    if len(q_clean) < 2:
        return {"status": "TOO_SHORT", "query": q_clean, "results": [], "provider": "Google Places / KGIS"}

    limit = max(1, min(int(limit or 8), 15))
    has_gkey = bool(get_google_maps_api_key())
    cache_key = (q_clean.lower(), limit, has_gkey)
    if cache_key in LOCATION_SEARCH_CACHE:
        cached = dict(LOCATION_SEARCH_CACHE[cache_key])
        cached["cached"] = True
        return cached

    suggestions = []
    seen_coords = set()
    q_low = q_clean.lower()
    active_providers = []

    def _push_suggestion(item_dict: dict):
        coord_key = (
            round(float(item_dict["latitude"]), 4),
            round(float(item_dict["longitude"]), 4),
            (item_dict.get("name") or "").lower(),
        )
        if coord_key in seen_coords:
            return
        seen_coords.add(coord_key)
        suggestions.append(item_dict)

    # 1. Authoritative KGIS Revenue Villages & Municipal Wards (free local polygons — instant, all 7 taluks)
    kgis_added = False
    try:
        for kv in search_kgis_villages(q_clean, limit=limit):
            kt = normalize_taluk(kv.get("taluk") or "Mysuru")
            ward_lbl = f" · Ward {kv['ward_number']}" if kv.get("ward_number") else ""
            _push_suggestion({
                "place_id": f"kgis_v_{kv['locality']}_{kt}",
                "osm_type": "kgis_polygon",
                "osm_id": None,
                "name": kv["name"],
                "locality": kv["locality"],
                "taluk": kt,
                "district": "Mysuru",
                "state": "Karnataka",
                "ward_number": kv.get("ward_number"),
                "ward_name": kv.get("ward_name"),
                "hobli": kv.get("hobli"),
                "latitude": kv["latitude"],
                "longitude": kv["longitude"],
                "category": "boundary",
                "place_type": "village",
                "place_type_label": f"KGIS Revenue Village ({kv.get('hobli') or kt} Hobli)",
                "is_non_settlement_landmark": False,
                "appropriate_zoom": 15 if kt == "Mysuru" else 14,
                "display_name": f"{kv['locality']}{ward_lbl}, {kt} Taluk, Mysuru (KGIS)",
                "full_display_name": f"{kv['locality']} Revenue Village, {kv.get('hobli') or kt} Hobli, {kt} Taluk, Mysuru District",
                "coordinate_status": "GEOCODED",
                "coordinate_source": "Karnataka GIS (KGIS)",
            })
            kgis_added = True
        for kw in search_kgis_wards(q_clean, limit=max(3, limit // 2)):
            kt = normalize_taluk(kw.get("taluk") or "Mysuru")
            _push_suggestion({
                "place_id": f"kgis_w_{kw.get('ward_number')}_{kw['locality']}_{kt}",
                "osm_type": "kgis_ward_polygon",
                "osm_id": None,
                "name": kw["name"],
                "locality": kw["locality"],
                "taluk": kt,
                "district": "Mysuru",
                "state": "Karnataka",
                "ward_number": kw.get("ward_number"),
                "ward_name": kw.get("ward_name"),
                "hobli": kw.get("hobli"),
                "latitude": kw["latitude"],
                "longitude": kw["longitude"],
                "category": "boundary",
                "place_type": "suburb",
                "place_type_label": f"KGIS Municipal Ward ({kw.get('municipal_body') or 'ULB'})",
                "is_non_settlement_landmark": False,
                "appropriate_zoom": 15,
                "display_name": f"{kw['name']} — {kw['locality']}, {kt} Taluk, Mysuru (KGIS)",
                "full_display_name": f"{kw['name']}, {kw['locality']}, {kt} Taluk, Mysuru District",
                "coordinate_status": "GEOCODED",
                "coordinate_source": "Karnataka GIS (KGIS)",
            })
            kgis_added = True
    except Exception:
        pass
    if kgis_added:
        active_providers.append("Karnataka GIS (KGIS)")

    # 2. Free Photon (OSM-backed) Search anchored to KGIS polygons
    if len(suggestions) < limit:
        try:
            ph_resp = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": f"{q_clean}, Mysuru", "lat": 12.3052, "lon": 76.6552, "limit": min(10, limit + 2)},
                headers={"User-Agent": "SmartLandEvaluation/1.0"},
                timeout=4,
            )
            if ph_resp.status_code == 200:
                ph_feats = (ph_resp.json() or {}).get("features", [])
                if ph_feats:
                    active_providers.append("Photon/OSM + KGIS")
                for feat in ph_feats:
                    coords = (feat.get("geometry") or {}).get("coordinates") or []
                    if len(coords) < 2:
                        continue
                    lon_v, lat_v = float(coords[0]), float(coords[1])
                    if not is_in_mysuru_district(lat_v, lon_v):
                        continue
                    props = feat.get("properties") or {}
                    p_name = (props.get("name") or "").strip()
                    fb_loc = (props.get("district") or props.get("locality") or props.get("city") or p_name or q_clean.title()).strip()
                    fb_taluk = min(
                        TALUK_HQS.keys(),
                        key=lambda t: ((lat_v - TALUK_HQS[t][0]) ** 2 + (lon_v - TALUK_HQS[t][1]) ** 2),
                    )
                    canon_loc, canon_taluk, kgis = _enrich_suggestion_with_kgis(lat_v, lon_v, fb_loc, fb_taluk)
                    primary_name = p_name or canon_loc
                    ward_lbl = f" · Ward {kgis['ward_number']}" if kgis.get("ward_number") else ""
                    short_lbl = f"{primary_name}" + (f" ({canon_loc})" if canon_loc and canon_loc.lower() != primary_name.lower() else "") + f"{ward_lbl}, {canon_taluk} Taluk, Mysuru"
                    okey = str(props.get("osm_key") or "place").lower()
                    oval = str(props.get("osm_value") or "locality").lower()
                    is_lm = okey in ("amenity", "shop", "railway", "power", "tourism") or oval in ("bus_stop", "bus_station", "station")
                    _push_suggestion({
                        "place_id": f"photon_{props.get('osm_type', 'N')}_{props.get('osm_id', 0)}",
                        "osm_type": props.get("osm_type"),
                        "osm_id": props.get("osm_id"),
                        "name": primary_name,
                        "locality": canon_loc,
                        "taluk": canon_taluk,
                        "district": "Mysuru",
                        "state": props.get("state") or "Karnataka",
                        "ward_number": kgis.get("ward_number"),
                        "ward_name": kgis.get("ward_name"),
                        "hobli": kgis.get("hobli"),
                        "latitude": round(lat_v, 6),
                        "longitude": round(lon_v, 6),
                        "category": okey,
                        "place_type": oval,
                        "place_type_label": f"{oval.replace('_', ' ').title()} (Photon/OSM)",
                        "is_non_settlement_landmark": is_lm,
                        "appropriate_zoom": 16 if is_lm else 15,
                        "display_name": short_lbl,
                        "full_display_name": f"{primary_name}, {canon_loc}, {canon_taluk} Taluk, Mysuru District",
                        "coordinate_status": "GEOCODED",
                        "coordinate_source": "Photon/OSM + KGIS" if kgis.get("matched") else "Photon/OSM",
                    })
        except Exception as _pe:
            log.debug("Photon location search skipped: %s", _pe)

    # 3. Optional Google Places API ONLY when explicitly enabled AND more hits needed
    if has_gkey and len(suggestions) < limit:
        gp = google_places_search(q_clean, limit=limit)
        if gp.get("status") == "OK" and gp.get("results"):
            active_providers.append("Google Places API")
            for gitem in gp["results"]:
                lat_v = float(gitem["latitude"])
                lon_v = float(gitem["longitude"])
                parsed = gitem.get("parsed_components") or {}
                fb_loc = parsed.get("supporting_locality") or gitem.get("name") or q_clean.title()
                fb_taluk = min(
                    TALUK_HQS.keys(),
                    key=lambda t: ((lat_v - TALUK_HQS[t][0]) ** 2 + (lon_v - TALUK_HQS[t][1]) ** 2),
                )
                canon_loc, canon_taluk, kgis = _enrich_suggestion_with_kgis(lat_v, lon_v, fb_loc, fb_taluk)
                gtypes = {t.lower() for t in (gitem.get("types") or [])}
                is_landmark = bool(
                    gtypes & {
                        "bus_station", "transit_station", "train_station", "subway_station",
                        "school", "university", "hospital", "doctor", "pharmacy", "police",
                        "bank", "atm", "shopping_mall", "supermarket", "gas_station", "place_of_worship",
                    }
                ) and not bool(gtypes & {"sublocality", "sublocality_level_1", "sublocality_level_2", "locality", "neighborhood"})
                zoom = 17 if is_landmark else (15 if gtypes & {"sublocality_level_1", "sublocality_level_2", "neighborhood"} else 14)
                ward_lbl = f" · Ward {kgis['ward_number']}" if kgis.get("ward_number") else ""
                _push_suggestion({
                    "place_id": gitem.get("place_id"),
                    "osm_type": "google_place",
                    "osm_id": None,
                    "name": gitem.get("name") or canon_loc,
                    "locality": canon_loc,
                    "taluk": canon_taluk,
                    "district": "Mysuru",
                    "state": "Karnataka",
                    "ward_number": kgis.get("ward_number"),
                    "ward_name": kgis.get("ward_name"),
                    "hobli": kgis.get("hobli"),
                    "latitude": round(lat_v, 6),
                    "longitude": round(lon_v, 6),
                    "category": "place",
                    "place_type": "landmark" if is_landmark else "locality",
                    "place_type_label": "Transit / Facility Landmark (Google Places)" if is_landmark else "Locality / Address (Google Places + KGIS)",
                    "is_non_settlement_landmark": is_landmark,
                    "appropriate_zoom": zoom,
                    "display_name": f"{gitem.get('name') or canon_loc} — {canon_loc}{ward_lbl}, {canon_taluk} Taluk, Mysuru",
                    "full_display_name": gitem.get("formatted_address") or f"{canon_loc}, {canon_taluk} Taluk, Mysuru",
                    "coordinate_status": "GEOCODED",
                    "coordinate_source": "Google Places API + KGIS",
                })

    # 3. Nominatim/OSM Fallback (when Google Places is unconfigured or extra street/layout hits needed)
    def _run_nominatim(search_q: str, bounded: int = 1) -> list:
        global _LAST_NOMINATIM_SEARCH_TS
        with _NOMINATIM_SEARCH_LOCK:
            now = _time.monotonic()
            wait_s = 1.05 - (now - _LAST_NOMINATIM_SEARCH_TS)
            if wait_s > 0:
                _time.sleep(wait_s)
            _LAST_NOMINATIM_SEARCH_TS = _time.monotonic()
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": search_q,
                    "format": "json",
                    "addressdetails": 1,
                    "namedetails": 1,
                    "limit": min(20, limit * 2 + 4),
                    "viewbox": "75.8,12.8,77.4,11.6",
                    "bounded": bounded,
                    "countrycodes": "in",
                },
                headers={"User-Agent": "SmartLandEvaluation/1.0", "Accept-Language": "en"},
                timeout=8,
            )
            resp.raise_for_status()
            return resp.json() or []

    nom_failed = False
    if len(suggestions) < limit:
        items = []
        try:
            items = _run_nominatim(q_clean, bounded=1)
            if len(items) < 3 and "mysur" not in q_low and "karnataka" not in q_low:
                items.extend(_run_nominatim(f"{q_clean}, Mysuru District, Karnataka, India", bounded=1))
        except Exception as e:
            nom_failed = True
            log.warning(f"Nominatim fallback search_locations failed for '{q_clean}': {e}")

        if items:
            active_providers.append("Nominatim/OSM + KGIS")

        for item in items:
            try:
                lat_v = float(item["lat"])
                lon_v = float(item["lon"])
            except Exception:
                continue
            if not is_in_mysuru_district(lat_v, lon_v):
                continue

            addr = item.get("address") or {}
            fb_loc = (
                addr.get("suburb")
                or addr.get("neighbourhood")
                or addr.get("village")
                or addr.get("hamlet")
                or addr.get("town")
                or addr.get("city_district")
                or addr.get("city")
                or item.get("name")
                or q_clean
            )
            fb_loc = str(fb_loc).split(",")[0].strip() if fb_loc else q_clean.title()
            raw_taluk = addr.get("county") or addr.get("state_district") or addr.get("town") or ""
            cand_taluk = normalize_taluk(raw_taluk) if raw_taluk else None
            fb_taluk = (
                cand_taluk
                if cand_taluk in TALUK_HQS
                else min(
                    TALUK_HQS.keys(),
                    key=lambda t: ((lat_v - TALUK_HQS[t][0]) ** 2 + (lon_v - TALUK_HQS[t][1]) ** 2),
                )
            )
            # CRITICAL: Anchor coordinates to KGIS polygon instead of trusting bloated OSM suburb labels!
            canon_loc, canon_taluk, kgis = _enrich_suggestion_with_kgis(lat_v, lon_v, fb_loc, fb_taluk)

            primary_name = (item.get("name") or "").strip() or canon_loc
            district_clean = _clean_district_name(addr.get("state_district") or addr.get("district") or "Mysuru") or "Mysuru"
            if district_clean.lower() not in ("mysuru", "mysore"):
                district_clean = "Mysuru"

            ward_lbl = f" · Ward {kgis['ward_number']}" if kgis.get("ward_number") else ""
            short_label = f"{primary_name}"
            if canon_loc and canon_loc.lower() != primary_name.lower():
                short_label += f" ({canon_loc})"
            short_label += f"{ward_lbl}, {canon_taluk} Taluk, {district_clean}"

            pt_raw = (item.get("type") or item.get("addresstype") or "locality").lower()
            oc_raw = (item.get("class") or "place").lower()
            is_landmark = (
                pt_raw in (
                    "station", "halt", "tram_stop", "bus_stop", "bus_station",
                    "substation", "school", "college", "hospital", "clinic",
                    "police", "bank", "atm", "place_of_worship", "fuel", "mall",
                )
                or oc_raw in ("railway", "power", "amenity", "shop", "tourism")
            )
            type_label_map = {
                "village": "Village / Rural Settlement",
                "hamlet": "Hamlet / Rural Settlement",
                "suburb": "Urban / Suburban Locality",
                "neighbourhood": "Urban Neighbourhood",
                "quarter": "Residential Layout / Sector",
                "town": "Town Municipal Centre",
                "city": "City Core",
                "station": "Railway Station (Transit Landmark)",
                "halt": "Railway Halt (Transit Landmark)",
                "bus_stop": "Bus Stop (Transit Landmark)",
                "bus_station": "Bus Stand (Transit Landmark)",
                "residential": "Residential Street / Area",
                "road": "Street / Road",
                "tertiary": "Local Road",
                "secondary": "Main Road Corridor",
                "primary": "Highway / Arterial Road",
                "administrative": "Taluk / Administrative Boundary",
                "county": "Taluk Administrative Region",
            }
            place_type_label = type_label_map.get(pt_raw, f"{pt_raw.replace('_', ' ').title()} ({oc_raw.title()})")

            _push_suggestion({
                "place_id": item.get("place_id"),
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "name": primary_name,
                "locality": canon_loc,
                "taluk": canon_taluk,
                "district": district_clean,
                "state": addr.get("state") or "Karnataka",
                "ward_number": kgis.get("ward_number"),
                "ward_name": kgis.get("ward_name"),
                "hobli": kgis.get("hobli"),
                "latitude": round(lat_v, 6),
                "longitude": round(lon_v, 6),
                "category": oc_raw,
                "place_type": pt_raw,
                "place_type_label": place_type_label,
                "is_non_settlement_landmark": is_landmark,
                "appropriate_zoom": _appropriate_zoom_for_osm_item(item),
                "display_name": short_label,
                "full_display_name": item.get("display_name", short_label),
                "coordinate_status": "GEOCODED",
                "coordinate_source": "Nominatim/OSM + KGIS" if kgis.get("matched") else "Nominatim/OSM",
            })

    if not suggestions and nom_failed and not has_gkey:
        return {
            "status": "SOURCE_UNAVAILABLE",
            "query": q_clean,
            "results": [],
            "provider": "Google Places / KGIS / Nominatim",
            "error": "Location search service is temporarily unavailable.",
        }

    # Rank non-landmark settlements & exact/prefix matches first, then Google/KGIS official polygons ahead of OSM POIs
    def _rank_key(s: dict):
        sname = (s.get("name") or "").lower()
        sloc = (s.get("locality") or "").lower()
        is_exact = 0 if (sname == q_low or sloc == q_low or sname.startswith(q_low) or sloc.startswith(q_low)) else 1
        src = (s.get("coordinate_source") or "").lower()
        src_rank = 0 if "google" in src else (1 if "kgis" in src and "nominatim" not in src else 2)
        landmark_rank = 1 if s.get("is_non_settlement_landmark") else 0
        taluk_rank = 0 if (s.get("taluk") or "").lower() == "mysuru" else 1
        return (landmark_rank, is_exact, src_rank, taluk_rank)

    suggestions.sort(key=_rank_key)
    suggestions = suggestions[:limit]

    name_counts = {}
    for s_item in suggestions:
        nk = (s_item.get("name") or "").strip().lower()
        if nk:
            name_counts[nk] = name_counts.get(nk, 0) + 1
    ambiguous = any(cnt > 1 for cnt in name_counts.values())

    res = {
        "status": "SUCCESS" if suggestions else "NO_DATA",
        "query": q_clean,
        "count": len(suggestions),
        "ambiguous_matches": ambiguous,
        "results": suggestions,
        "provider": " + ".join(active_providers) if active_providers else "Karnataka GIS (KGIS)",
        "google_places_enabled": has_gkey,
        "cached": False,
    }
    if len(LOCATION_SEARCH_CACHE) > 250:
        LOCATION_SEARCH_CACHE.pop(next(iter(LOCATION_SEARCH_CACHE)))
    LOCATION_SEARCH_CACHE[cache_key] = res
    return res


def _clean_district_name(val: str) -> str:
    s = (val or "").strip()
    if s.lower().endswith(" district"):
        s = s[:-9].strip()
    return "Mysuru" if s.lower() in ("mysore", "mysuru") else s


def _norm_compare_locality(name: Optional[str]) -> str:
    """Normalize urban/rural locality strings for independent-source comparison."""
    import re as _re
    s = str(name or "").strip().lower()
    if not s:
        return ""
    s = _re.sub(r"\([^)]*\)", " ", s)
    s = _re.sub(r"\b(ward|stage|block|phase|extension|extn|layout|badavane|mohalla|road|street)\b", " ", s)
    s = _re.sub(r"\bnagara?\b", "nagar", s)
    s = s.replace("thilak", "tilak").replace("sathya", "satya").replace("ajiz", "azeez")
    s = _re.sub(r"[^a-z0-9]", "", s)
    # Handle common initial contractions e.g. 'nrmohalla' / 'narasimharaja'
    s = s.replace("narasimharaja", "nr").replace("krishnaraja", "kr").replace("jayachamaraja", "jc")
    return s


def _assess_source_agreement(
    kgis_locality: Optional[str],
    kgis_village: Optional[str],
    kgis_ward_name: Optional[str],
    kgis_ward_no: Optional[str],
    kgis_boundary_type: Optional[str],
    geocoder_locality: Optional[str],
    geocoder_source_name: Optional[str],
    geocoder_address: Optional[str],
) -> dict:
    """
    Compare authoritative KGIS point-in-polygon locality against an independent geocoder
    (Google Geocoding API or Nominatim/OSM). Flags disagreements transparently instead of
    silently masking neighbourhood/mohalla vs electoral-ward differences.
    """
    import difflib

    kgis_cands = [c for c in (kgis_locality, kgis_ward_name) if c] if kgis_ward_no else [c for c in (kgis_locality, kgis_village) if c]
    geo_loc = (geocoder_locality or "").strip() or None

    # Build deduplicated candidate list for confirmation UI
    candidates = []
    seen_c = set()

    def _add_cand(loc_val: Optional[str], src_val: str, detail_val: str):
        if not loc_val:
            return
        k = loc_val.strip().lower()
        if k in seen_c:
            return
        seen_c.add(k)
        candidates.append({
            "locality": loc_val.strip(),
            "source": src_val,
            "detail": detail_val,
        })

    if kgis_locality:
        ward_det = f"Ward {kgis_ward_no}" if kgis_ward_no else "Revenue Village Boundary"
        _add_cand(
            kgis_locality,
            "Karnataka GIS (KGIS Boundary Polygon)",
            f"{kgis_boundary_type or 'KGIS Boundary'} ({ward_det})",
        )
    if kgis_village and kgis_village.lower() != (kgis_locality or "").lower():
        _add_cand(kgis_village, "Karnataka GIS (Revenue Village)", f"Revenue Village: {kgis_village}")
    if geo_loc:
        _add_cand(
            geo_loc,
            geocoder_source_name or "Geocoder Suburb / Neighbourhood",
            geocoder_address or f"Reported by {geocoder_source_name or 'Geocoder'}",
        )

    if not kgis_locality and not geo_loc:
        return {
            "verification_status": "REQUIRES_VERIFICATION",
            "source_disagreement": False,
            "disagreement_reason": "Neither KGIS boundary polygons nor geocoder resolved a locality.",
            "candidate_localities": candidates,
        }

    if kgis_locality and not geo_loc:
        return {
            "verification_status": "KGIS_BOUNDARY_ONLY",
            "source_disagreement": False,
            "disagreement_reason": None,
            "candidate_localities": candidates,
        }

    if not kgis_locality and geo_loc:
        return {
            "verification_status": "GEOCODER_ONLY_BOUNDARY_GAP",
            "source_disagreement": False,
            "disagreement_reason": (
                f"KGIS locality polygon coverage gap at this coordinate; '{geo_loc}' comes from "
                f"{geocoder_source_name or 'external geocoder'} and requires manual verification."
            ),
            "candidate_localities": candidates,
        }

    # Both KGIS and external geocoder returned names — compare normalized forms
    gn = _norm_compare_locality(geo_loc)
    matched = False
    for kc in kgis_cands:
        kn = _norm_compare_locality(kc)
        if not kn or not gn:
            continue
        if kn == gn or kn in gn or gn in kn:
            matched = True
            break
        if difflib.SequenceMatcher(None, kn, gn).ratio() >= 0.78:
            matched = True
            break

    if matched:
        return {
            "verification_status": "VERIFIED",
            "source_disagreement": False,
            "disagreement_reason": None,
            "candidate_localities": candidates,
        }

    src_lbl = geocoder_source_name or "OSM/Nominatim"
    if kgis_ward_no:
        reason = (
            f"KGIS Municipal Ward {kgis_ward_no} ('{kgis_locality}'"
            f"{f', Rev. Village: {kgis_village}' if kgis_village else ''}) differs from "
            f"{src_lbl} neighbourhood ('{geo_loc}'). MCC electoral wards often cover multiple "
            f"adjacent neighbourhoods/mohallas — please review and confirm the applicable locality."
        )
    else:
        reason = (
            f"KGIS Revenue Village ('{kgis_locality}') differs from {src_lbl} locality ('{geo_loc}'). "
            f"Please review both before confirming."
        )
    return {
        "verification_status": "SOURCE_DISAGREEMENT",
        "source_disagreement": True,
        "disagreement_reason": reason,
        "candidate_localities": candidates,
    }


def reverse_geocode_coords(lat: float, lon: float) -> dict:
    """
    Reverse-geocode selected property coordinates strictly by priority:
      1. Authoritative Karnataka GIS (KGIS / KSRSAC) point-in-polygon boundary containment
         (Revenue Village, Municipal Ward, Hobli, Taluk, ULB, Planning Authority)
      2. Google Maps Geocoding API reverse-geocoded address components (supporting evidence;
         fallback ONLY when KGIS village & ward polygons both have a gap)
      3. Secondary Nominatim/OSM cross-check (strictly non-facility fallback when needed)
    Never uses radius expansion, bus stops, railway stations, landmarks, or centroids to assign locality.
    Returns 'Locality Requires Verification' if boundaries overlap or cannot be resolved.
    """
    from .geo_utils import is_in_mysuru_district, normalize_taluk, TALUK_HQS
    from .kgis_boundaries import lookup_kgis_location
    from .adapters.google import google_reverse_geocode, get_google_maps_api_key

    if not is_in_mysuru_district(lat, lon):
        return {
            "status": "OUTSIDE_DISTRICT",
            "confidence": "none",
            "locality": None,
            "taluk": None,
            "district": None,
            "state": None,
            "provider": "Karnataka GIS (KGIS) Polygons",
            "error": "Coordinates fall outside the Mysuru District boundary polygon.",
        }

    has_gkey = bool(get_google_maps_api_key())
    cache_key = (round(float(lat), 5), round(float(lon), 5), has_gkey)
    if cache_key in REVERSE_GEOCODE_CACHE:
        return dict(REVERSE_GEOCODE_CACHE[cache_key])

    # 1. Primary Authoritative Point-in-Polygon Resolution (KGIS / KSRSAC)
    kgis = lookup_kgis_location(float(lat), float(lon))

    # 2. Supporting Google Maps Geocoding API Cross-Check (when API key configured)
    google_rev = google_reverse_geocode(float(lat), float(lon)) if has_gkey else {
        "status": "NOT_CONFIGURED",
        "provider": "Google Geocoding API",
        "supporting_locality": None,
    }
    g_ok = google_rev.get("status") == "OK"
    google_loc = google_rev.get("supporting_locality") if g_ok else None

    kgis_smallest = kgis.get("smallest_locality")
    kgis_village = kgis.get("revenue_village_display") or kgis.get("revenue_village")
    kgis_ward_name = kgis.get("ward_name")

    # 3. Secondary Nominatim Cross-Check (run ONLY when KGIS/Google lack coverage or postcode needed)
    data = None
    nom_locality = None
    addr = {}
    if not (kgis_smallest and g_ok):
        url = "https://nominatim.openstreetmap.org/reverse"
        headers = {
            "User-Agent": "SmartLandEvaluation/1.0",
            "Accept-Language": "en",
        }
        for zoom in (16, 14):
            try:
                resp = requests.get(
                    url,
                    params={
                        "format": "jsonv2",
                        "lat": lat,
                        "lon": lon,
                        "addressdetails": 1,
                        "zoom": zoom,
                        "accept-language": "en",
                    },
                    headers=headers,
                    timeout=4,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    if payload and not payload.get("error"):
                        data = payload
                        break
            except Exception:
                pass
        addr = (data or {}).get("address", {}) or {}
        _facility_noise = (
            "bus stop", "bus stand", "bus depot", "railway station", "hospital",
            "school", "police station", "substation", "petrol", "hotel",
        )
        for key in ("suburb", "village", "hamlet", "town", "quarter", "city_district", "neighbourhood", "residential", "local_authority", "subdistrict"):
            cand = (addr.get(key) or "").strip()
            if not cand:
                continue
            c_low = cand.lower()
            if "taluk" in c_low or c_low in ("mysuru", "mysore", "mysuru district", "karnataka", "india"):
                continue
            if any(fw in c_low for fw in _facility_noise):
                continue
            nom_locality = cand
            break

    g_taluk_raw = google_rev.get("taluk_component") if g_ok else None
    g_taluk = normalize_taluk(g_taluk_raw) if g_taluk_raw else None
    nom_taluk_raw = addr.get("county") or addr.get("subdistrict") or addr.get("state_district") or ""
    nom_taluk = normalize_taluk(nom_taluk_raw) if nom_taluk_raw else None

    kgis_taluk_raw = kgis.get("kgis_taluk")
    kgis_taluk_norm = normalize_taluk(kgis_taluk_raw) if kgis_taluk_raw else None
    valid_taluk = (
        kgis_taluk_norm if kgis_taluk_norm in TALUK_HQS
        else (g_taluk if g_taluk in TALUK_HQS else (nom_taluk if nom_taluk in TALUK_HQS else None))
    )

    district_clean = (
        kgis.get("district")
        or _clean_district_name(google_rev.get("district_component") if g_ok else "")
        or _clean_district_name(addr.get("state_district") or addr.get("district") or "Mysuru")
        or "Mysuru"
    )
    state_clean = (google_rev.get("state_component") if g_ok else None) or (addr.get("state") or "").strip() or "Karnataka"

    google_comp_summary = {
        k: google_rev.get(k)
        for k in ("sublocality_level_2", "sublocality_level_1", "sublocality", "neighborhood", "city_or_town", "taluk_component", "postal_code")
        if g_ok and google_rev.get(k)
    }

    # Ambiguity / Overlap guard
    if kgis.get("overlap_detected"):
        res = {
            "status": "AMBIGUOUS",
            "confidence": "ambiguous",
            "locality": None,
            "locality_display": "Locality Requires Verification",
            "uncertain": True,
            "taluk": valid_taluk,
            "district": district_clean,
            "state": state_clean,
            "revenue_village": None,
            "urban_locality": kgis.get("urban_locality"),
            "ward_number": kgis.get("ward_number"),
            "ward_name": kgis.get("ward_name"),
            "hobli": kgis.get("hobli"),
            "municipal_body": kgis.get("local_body"),
            "likely_planning_authority": kgis.get("likely_planning_authority"),
            "boundary_source": kgis.get("source"),
            "point_in_polygon": True,
            "kgis_boundaries": kgis,
            "google_geocoder_status": google_rev.get("status"),
            "google_supporting_locality": google_loc,
            "google_formatted_address": google_rev.get("formatted_address") if g_ok else None,
            "google_address_components": google_comp_summary,
            "secondary_nominatim_locality": nom_locality,
            "raw_nominatim": data,
            "display_name": google_rev.get("formatted_address") if g_ok else (data or {}).get("display_name", ""),
            "provider": "Karnataka GIS (KGIS) Polygons",
            "retrieved_at": _now_iso(),
            "error": f"Overlapping boundary polygons ({', '.join(kgis.get('overlapping_villages', []))}) — Locality Requires Verification.",
        }
        REVERSE_GEOCODE_CACHE[cache_key] = res
        return dict(res)

    # Compare authoritative KGIS boundary against supporting geocoder (Google or Nominatim)
    sup_loc = google_loc if g_ok else nom_locality
    sup_src = "Google Geocoding API" if g_ok else ("Nominatim / OpenStreetMap" if nom_locality else None)
    sup_addr = (google_rev.get("formatted_address") if g_ok else None) or (data or {}).get("display_name")
    agreement = _assess_source_agreement(
        kgis_locality=kgis_smallest or kgis_ward_name,
        kgis_village=kgis_village,
        kgis_ward_name=kgis_ward_name,
        kgis_ward_no=kgis.get("ward_number"),
        kgis_boundary_type=kgis.get("smallest_boundary_type"),
        geocoder_locality=sup_loc,
        geocoder_source_name=sup_src,
        geocoder_address=sup_addr,
    )

    # Strict Resolution Priority Chain:
    #   1. Smallest reliable KGIS containing polygon (MCC Urban Ward inside Mysuru CC, else KGIS Revenue Village)
    #   2. KGIS Urban Ward fallback
    #   3. Google Geocoding supporting locality (only on KGIS boundary gap)
    #   4. Nominatim fallback (only on KGIS & Google gap)
    #   5. Locality Requires Verification
    if kgis_smallest and not kgis.get("overlap_detected"):
        final_locality = kgis_smallest
        confidence = "medium" if agreement["source_disagreement"] else "high"
        cross = "Google Geocoding Supporting Check" if g_ok else "Nominatim Cross-Check"
        btype = kgis.get("smallest_boundary_type") or "KGIS Boundary Polygon"
        provider_lbl = f"{btype} + {cross}"
    elif kgis_ward_name:
        final_locality = kgis_ward_name
        confidence = "medium" if agreement["source_disagreement"] else "high"
        cross = "Google Geocoding Supporting Check" if g_ok else "KGIS Boundaries"
        provider_lbl = f"KGIS Urban Ward Polygon + {cross}"
    elif google_loc:
        final_locality = google_loc
        confidence = "medium"
        provider_lbl = "Google Geocoding API (KGIS Locality Polygon Gap)"
    elif nom_locality:
        final_locality = nom_locality
        confidence = "low"
        provider_lbl = "Nominatim/OSM (KGIS Locality Polygon Gap)"
    else:
        res = {
            "status": "AMBIGUOUS",
            "confidence": "low",
            "locality": None,
            "locality_display": "Locality Requires Verification",
            "uncertain": True,
            "verification_status": "REQUIRES_VERIFICATION",
            "source_disagreement": False,
            "disagreement_reason": agreement.get("disagreement_reason"),
            "candidate_localities": agreement.get("candidate_localities", []),
            "taluk": valid_taluk,
            "district": district_clean,
            "state": state_clean,
            "revenue_village": kgis_village,
            "urban_locality": kgis.get("urban_locality"),
            "ward_number": kgis.get("ward_number"),
            "ward_name": kgis.get("ward_name"),
            "hobli": kgis.get("hobli"),
            "gram_panchayat_lgd_code": kgis.get("lgd_gp_code"),
            "assembly_constituency": None,
            "assembly_constituency_status": "UNAVAILABLE_NO_DATASET",
            "municipal_body": kgis.get("local_body"),
            "likely_planning_authority": kgis.get("likely_planning_authority"),
            "boundary_source": kgis.get("source"),
            "smallest_boundary_type": kgis.get("smallest_boundary_type"),
            "point_in_polygon": bool(kgis.get("point_in_polygon")),
            "kgis_boundaries": kgis,
            "google_geocoder_status": google_rev.get("status"),
            "google_supporting_locality": google_loc,
            "google_formatted_address": google_rev.get("formatted_address") if g_ok else None,
            "google_address_components": google_comp_summary,
            "secondary_nominatim_locality": nom_locality,
            "geocoder_reported_locality": sup_loc,
            "geocoder_reported_address": sup_addr,
            "raw_nominatim": data,
            "display_name": sup_addr or "",
            "provider": kgis.get("source") if kgis.get("matched") else google_rev.get("provider"),
            "retrieved_at": _now_iso(),
            "error": f"Locality Requires Verification (coordinates fall within {valid_taluk or 'Mysuru'} taluk; exact locality polygon missing).",
        }
        REVERSE_GEOCODE_CACHE[cache_key] = res
        return dict(res)

    disp_parts = [final_locality]
    if kgis.get("ward_number"):
        wn = kgis.get("ward_name")
        disp_parts.append(f"Ward {kgis['ward_number']}{f' ({wn})' if wn else ''}")
    if kgis.get("hobli"):
        disp_parts.append(f"{kgis['hobli']} Hobli")
    disp_parts.extend([f"{valid_taluk or 'Mysuru'} Taluk", f"{district_clean} District"])

    res = {
        "status": "SUCCESS",
        "confidence": confidence,
        "verification_status": agreement["verification_status"],
        "source_disagreement": agreement["source_disagreement"],
        "disagreement_reason": agreement["disagreement_reason"],
        "candidate_localities": agreement["candidate_localities"],
        "locality": final_locality,
        "taluk": valid_taluk or kgis_taluk_norm or "Mysuru",
        "kgis_taluk_exact": kgis_taluk_raw,
        "district": district_clean,
        "state": state_clean,
        "revenue_village": kgis_village or final_locality,
        "urban_locality": kgis.get("urban_locality"),
        "ward_number": kgis.get("ward_number"),
        "ward_name": kgis.get("ward_name"),
        "hobli": kgis.get("hobli"),
        "gram_panchayat_lgd_code": kgis.get("lgd_gp_code"),
        "assembly_constituency": None,
        "assembly_constituency_status": "UNAVAILABLE_NO_DATASET",
        "municipal_body": kgis.get("local_body"),
        "municipal_type": kgis.get("municipal_type"),
        "likely_planning_authority": kgis.get("likely_planning_authority"),
        "boundary_source": kgis.get("source"),
        "smallest_boundary_type": kgis.get("smallest_boundary_type"),
        "smallest_area_sqm": kgis.get("smallest_area_sqm"),
        "point_in_polygon": bool(kgis.get("point_in_polygon")),
        "kgis_boundaries": kgis,
        "google_geocoder_status": google_rev.get("status"),
        "google_supporting_locality": google_loc,
        "google_formatted_address": google_rev.get("formatted_address") if g_ok else None,
        "google_address_components": google_comp_summary,
        "secondary_nominatim_locality": nom_locality,
        "geocoder_reported_locality": sup_loc,
        "geocoder_reported_address": sup_addr,
        "raw_nominatim": data,
        "postcode": (google_rev.get("postal_code") if g_ok else None) or addr.get("postcode"),
        "display_name": ", ".join(disp_parts),
        "provider": provider_lbl,
        "retrieved_at": _now_iso(),
    }
    REVERSE_GEOCODE_CACHE[cache_key] = res
    return dict(res)


def resolve_entered_vs_coordinates(
    lat: float,
    lon: float,
    entered_locality: Optional[str],
    entered_taluk: Optional[str],
) -> dict:
    """
    Reconcile user-entered (locality, taluk) with reverse-geocoded (lat, lon).
    If coordinates confidently identify a different locality/taluk, use the resolved
    values as canonical while preserving original entered values for auditability.
    Never invents a locality on failure or ambiguity.
    """
    import difflib
    from .geo_utils import normalize_locality, normalize_taluk

    ent_loc = (entered_locality or "").strip()
    ent_taluk = normalize_taluk(entered_taluk)
    rev = reverse_geocode_coords(lat, lon)

    audit = {
        "entered_locality": ent_loc or None,
        "entered_taluk": ent_taluk,
        "resolved_locality": rev.get("locality"),
        "resolved_taluk": rev.get("taluk"),
        "resolved_district": rev.get("district"),
        "resolved_state": rev.get("state"),
        "revenue_village": rev.get("revenue_village"),
        "urban_locality": rev.get("urban_locality"),
        "ward_number": rev.get("ward_number"),
        "ward_name": rev.get("ward_name"),
        "hobli": rev.get("hobli"),
        "municipal_body": rev.get("municipal_body"),
        "likely_planning_authority": rev.get("likely_planning_authority"),
        "boundary_source": rev.get("boundary_source"),
        "point_in_polygon": rev.get("point_in_polygon"),
        "google_geocoder_status": rev.get("google_geocoder_status"),
        "google_supporting_locality": rev.get("google_supporting_locality"),
        "google_formatted_address": rev.get("google_formatted_address"),
        "secondary_nominatim_locality": rev.get("secondary_nominatim_locality"),
        "geocoder_reported_locality": rev.get("geocoder_reported_locality"),
        "geocoder_reported_address": rev.get("geocoder_reported_address"),
        "verification_status": rev.get("verification_status"),
        "source_disagreement": rev.get("source_disagreement"),
        "disagreement_reason": rev.get("disagreement_reason"),
        "gram_panchayat_lgd_code": rev.get("gram_panchayat_lgd_code"),
        "assembly_constituency": rev.get("assembly_constituency"),
        "reverse_display_name": rev.get("display_name"),
        "reverse_provider": rev.get("provider"),
        "reverse_status": rev.get("status"),
        "reverse_confidence": rev.get("confidence"),
        "canonical_locality": ent_loc,
        "canonical_taluk": ent_taluk,
        "resolution_status": "UNVERIFIED",
        "mismatch_detected": False,
        "mismatch_distance_km": None,
        "warning": None,
    }

    if rev["status"] == "UNAVAILABLE":
        audit["resolution_status"] = "REVERSE_GEOCODE_UNAVAILABLE"
        if not ent_loc:
            audit["canonical_locality"] = "Locality Requires Verification"
            audit["uncertain"] = True
        else:
            audit["user_reported_locality"] = True
        audit["warning"] = (
            "Reverse-geocoding service was unavailable; coordinates could not be verified "
            f"against locality boundaries. {'Using user-reported locality.' if ent_loc else 'Locality Requires Verification.'}"
        )
        return audit

    if rev["status"] == "AMBIGUOUS":
        audit["resolution_status"] = "AMBIGUOUS_REVERSE_GEOCODE"
        if rev.get("taluk"):
            audit["canonical_taluk"] = rev["taluk"]
        if not ent_loc:
            audit["canonical_locality"] = "Locality Requires Verification"
            audit["uncertain"] = True
        else:
            audit["user_reported_locality"] = True
        extra_taluk = f" Coordinates appear within {rev['taluk']} taluk." if rev.get("taluk") else ""
        audit["warning"] = (
            f"Locality Requires Verification ({rev.get('error')}).{extra_taluk}"
        )
        return audit

    if rev["status"] != "SUCCESS" or not rev.get("locality"):
        audit["resolution_status"] = rev["status"]
        if not ent_loc:
            audit["canonical_locality"] = "Locality Requires Verification"
            audit["uncertain"] = True
        else:
            audit["user_reported_locality"] = True
        audit["warning"] = rev.get("error")
        return audit

    res_loc = rev["locality"]
    res_taluk = normalize_taluk(rev.get("taluk") or ent_taluk)

    if not ent_loc:
        audit["canonical_locality"] = res_loc
        audit["canonical_taluk"] = res_taluk
        audit["resolution_status"] = "AUTO_RESOLVED_FROM_COORDS"
        return audit

    import re as _re
    norm_ent = normalize_locality(ent_loc)
    norm_res = normalize_locality(res_loc)
    sim = difflib.SequenceMatcher(None, norm_ent, norm_res).ratio()
    de_ent = _re.sub(r"([bcdgkpt])h", r"\1", norm_ent)
    de_res = _re.sub(r"([bcdgkpt])h", r"\1", norm_res)
    sim_de = difflib.SequenceMatcher(None, de_ent, de_res).ratio()
    same_locality = (
        (norm_ent == norm_res)
        or (norm_ent in norm_res)
        or (norm_res in norm_ent)
        or (sim >= 0.78)
        or (sim_de >= 0.80)
    )
    same_taluk = (ent_taluk == res_taluk)

    if same_locality and same_taluk:
        audit["canonical_locality"] = res_loc if (norm_ent != norm_res) else ent_loc
        audit["canonical_taluk"] = res_taluk
        audit["resolution_status"] = "MATCHED" if norm_ent == norm_res else "MINOR_SPELLING_NORMALIZED"
        return audit

    # If user explicitly confirmed the independent geocoder neighbourhood (e.g. NR Mohalla / Udayagiri)
    # or KGIS revenue village at this coordinate when KGIS Ward & Geocoder differed, honor their confirmed pick.
    sup_cand = rev.get("geocoder_reported_locality")
    rev_vill = rev.get("revenue_village")
    if same_taluk:
        for alt_src, alt_status in ((sup_cand, "CONFIRMED_SUPPORTING_GEOCODER"), (rev_vill, "CONFIRMED_REVENUE_VILLAGE")):
            if alt_src:
                norm_alt = _norm_compare_locality(alt_src)
                if norm_alt and (_norm_compare_locality(ent_loc) == norm_alt or difflib.SequenceMatcher(None, _norm_compare_locality(ent_loc), norm_alt).ratio() >= 0.80):
                    audit["canonical_locality"] = alt_src
                    audit["canonical_taluk"] = res_taluk
                    audit["resolution_status"] = alt_status
                    return audit

    # Measure distance only for diagnostic audit — NEVER override coordinate-resolved locality
    # with an adjacent locality or nearby facility name (e.g. Sathagalli vs Kyathamaranahalli).
    fwd = None
    dist_mismatch = None
    try:
        fwd = geocode_locality(ent_loc, ent_taluk, "Mysuru")
        if fwd:
            dist_mismatch = round(haversine(lat, lon, fwd["lat"], fwd["lon"]), 2)
    except Exception:
        fwd = None

    audit["mismatch_detected"] = True
    audit["mismatch_distance_km"] = dist_mismatch

    if rev.get("confidence") in ("high", "medium"):
        audit["canonical_locality"] = res_loc
        audit["canonical_taluk"] = res_taluk
        audit["resolution_status"] = "CORRECTED_FROM_COORDS"
        dist_clause = f" (~{dist_mismatch:.1f} km from geocoded '{ent_loc}')" if dist_mismatch else ""
        rev_prov = rev.get("provider") or "Authoritative GIS Boundaries"
        audit["warning"] = (
            f"Coordinates ({lat:.5f}, {lon:.5f}) are the primary reference and resolved via "
            f"{rev_prov} to '{res_loc}' ({res_taluk} taluk, {rev.get('district', 'Mysuru')} District){dist_clause}. "
            f"Canonical evaluation locality set to '{res_loc}'; entered input '{ent_loc}' preserved for audit only."
        )
    else:
        audit["canonical_locality"] = "Locality Requires Verification"
        audit["canonical_taluk"] = res_taluk
        audit["uncertain"] = True
        audit["resolution_status"] = "MISMATCH_LOW_CONFIDENCE"
        audit["warning"] = (
            f"Locality Requires Verification from ({lat:.5f}, {lon:.5f}) "
            f"[suggested '{res_loc}', confidence={rev.get('confidence')} vs entered '{ent_loc}']. Please verify manually."
        )

    return audit
