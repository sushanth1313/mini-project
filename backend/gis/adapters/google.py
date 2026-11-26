import os
import threading
import time
import requests
import logging
from datetime import datetime, timezone
from typing import Optional
from .base import BaseAdapter

log = logging.getLogger(__name__)

_GOOGLE_LOCK = threading.Lock()
_GOOGLE_RUNTIME_ENABLED: Optional[bool] = None
_GOOGLE_DAILY_QUOTA = int(os.environ.get("GOOGLE_MAPS_DAILY_QUOTA", "200") or "200")
_GOOGLE_USAGE_DAY = ""
_GOOGLE_USAGE_COUNT = 0
_GOOGLE_REV_CACHE: dict = {}
_GOOGLE_FWD_CACHE: dict = {}
_GOOGLE_PLACES_CACHE: dict = {}
_GOOGLE_FAC_CACHE: dict = {}

_FACILITY_NOISE_WORDS = (
    "bus stop", "bus stand", "bus depot", "railway station", "train station",
    "hospital", "clinic", "school", "college", "police station", "substation",
    "petrol", "fuel", "hotel", "restaurant", "temple", "mosque", "church",
    "atm", "bank", "pharmacy", "supermarket", "mall", "park",
)


def is_google_maps_enabled() -> bool:
    """Google Maps Platform is strictly OPTIONAL: active only when API key exists AND explicitly enabled."""
    key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if not key:
        return False
    if _GOOGLE_RUNTIME_ENABLED is not None:
        return bool(_GOOGLE_RUNTIME_ENABLED)
    flag = (os.environ.get("GOOGLE_MAPS_ENABLED") or "false").strip().lower()
    return flag in ("1", "true", "yes", "on", "enabled")


def set_google_maps_enabled(enabled: bool) -> None:
    global _GOOGLE_RUNTIME_ENABLED
    with _GOOGLE_LOCK:
        _GOOGLE_RUNTIME_ENABLED = bool(enabled)


def get_google_maps_status() -> dict:
    key_set = bool((os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip())
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _GOOGLE_LOCK:
        used_today = _GOOGLE_USAGE_COUNT if _GOOGLE_USAGE_DAY == today else 0
    return {
        "api_key_configured": key_set,
        "enabled": is_google_maps_enabled(),
        "daily_quota": _GOOGLE_DAILY_QUOTA,
        "requests_used_today": used_today,
    }


def _consume_google_quota(calls: int = 1) -> bool:
    """Enforce daily Google Maps Platform request cap so unexpected charges cannot occur."""
    global _GOOGLE_USAGE_DAY, _GOOGLE_USAGE_COUNT
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _GOOGLE_LOCK:
        if _GOOGLE_USAGE_DAY != today:
            _GOOGLE_USAGE_DAY = today
            _GOOGLE_USAGE_COUNT = 0
        if (_GOOGLE_USAGE_COUNT + calls) > _GOOGLE_DAILY_QUOTA:
            return False
        _GOOGLE_USAGE_COUNT += calls
        return True


def get_google_maps_api_key() -> Optional[str]:
    """Read Google Maps API key ONLY when key is set and Google provider is explicitly enabled."""
    if not is_google_maps_enabled():
        return None
    key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    return key or None


def _is_facility_or_generic_label(label: str) -> bool:
    s = (label or "").strip().lower()
    if not s:
        return True
    if "taluk" in s or s in ("mysuru", "mysore", "mysuru district", "mysore district", "karnataka", "india"):
        return True
    return any(w in s for w in _FACILITY_NOISE_WORDS)


def _extract_google_components(address_components: list) -> dict:
    """Parse structured Google Geocoding / Place address components safely."""
    comp_map = {}
    for comp in address_components or []:
        long_name = (comp.get("long_name") or "").strip()
        if not long_name:
            continue
        for ctype in comp.get("types") or []:
            if ctype not in comp_map:
                comp_map[ctype] = long_name

    # Supporting locality priority: sublocality_level_2 -> sublocality_level_1 -> sublocality -> neighborhood -> non-Mysuru locality
    supporting_locality = None
    for ctype in (
        "sublocality_level_3",
        "sublocality_level_2",
        "sublocality_level_1",
        "sublocality",
        "neighborhood",
        "locality",
        "administrative_area_level_4",
    ):
        cand = comp_map.get(ctype)
        if cand and not _is_facility_or_generic_label(cand):
            supporting_locality = cand
            break

    return {
        "supporting_locality": supporting_locality,
        "sublocality_level_2": comp_map.get("sublocality_level_2"),
        "sublocality_level_1": comp_map.get("sublocality_level_1"),
        "sublocality": comp_map.get("sublocality"),
        "neighborhood": comp_map.get("neighborhood"),
        "city_or_town": comp_map.get("locality"),
        "taluk_component": comp_map.get("administrative_area_level_3"),
        "district_component": comp_map.get("administrative_area_level_2"),
        "state_component": comp_map.get("administrative_area_level_1"),
        "postal_code": comp_map.get("postal_code"),
    }


def google_reverse_geocode(lat: float, lon: float) -> dict:
    """
    Reverse-geocode (lat, lon) via Google Maps Geocoding API (OPTIONAL provider).
    Used strictly as supporting evidence when explicitly enabled & within quota;
    results are cached by rounded coordinates so repeated calls are never billed.
    """
    api_key = get_google_maps_api_key()
    if not api_key:
        return {
            "status": "NOT_CONFIGURED",
            "provider": "Google Geocoding API (Optional / Disabled)",
            "supporting_locality": None,
            "error": "Google Maps Platform is optional and currently disabled or unconfigured.",
        }

    ck = (round(float(lat), 4), round(float(lon), 4))
    with _GOOGLE_LOCK:
        cached = _GOOGLE_REV_CACHE.get(ck)
        if cached and (time.monotonic() - cached.get("_ts", 0)) < 3600:
            return {k: v for k, v in cached.items() if k != "_ts"}

    if not _consume_google_quota(1):
        return {
            "status": "QUOTA_LIMIT",
            "provider": "Google Geocoding API",
            "supporting_locality": None,
            "error": "Daily Google Maps quota reached; using free GIS providers.",
        }

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"latlng": f"{lat},{lon}", "language": "en", "key": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
    except Exception as e:
        log.warning("Google Geocoding API request error: %s", type(e).__name__)
        return {
            "status": "UNAVAILABLE",
            "provider": "Google Geocoding API",
            "supporting_locality": None,
            "error": f"Google Geocoding request failed ({type(e).__name__}).",
        }

    gstatus = (payload.get("status") or "").upper()
    if gstatus not in ("OK", "ZERO_RESULTS"):
        log.warning("Google Geocoding API status=%s", gstatus)
        return {
            "status": "API_ERROR",
            "google_status": gstatus,
            "provider": "Google Geocoding API",
            "supporting_locality": None,
            "error": payload.get("error_message") or f"Google Geocoding API returned {gstatus}.",
        }

    results = payload.get("results") or []
    if not results:
        return {
            "status": "ZERO_RESULTS",
            "provider": "Google Geocoding API",
            "supporting_locality": None,
        }

    # Prefer results that are political / sublocality / locality / route rather than transit POI alone
    preferred = results[0]
    for r in results:
        rtypes = set(r.get("types") or [])
        if rtypes & {"sublocality_level_1", "sublocality_level_2", "sublocality", "neighborhood", "locality"}:
            preferred = r
            break

    parsed = _extract_google_components(preferred.get("address_components") or [])
    if not parsed.get("supporting_locality"):
        for r in results[1:4]:
            alt = _extract_google_components(r.get("address_components") or [])
            if alt.get("supporting_locality"):
                parsed["supporting_locality"] = alt["supporting_locality"]
                for k in ("sublocality_level_2", "sublocality_level_1", "sublocality", "neighborhood", "postal_code"):
                    if not parsed.get(k) and alt.get(k):
                        parsed[k] = alt[k]
                break

    out = {
        "status": "OK",
        "provider": "Google Geocoding API",
        "formatted_address": preferred.get("formatted_address"),
        "place_id": preferred.get("place_id"),
        "location_type": (preferred.get("geometry") or {}).get("location_type"),
        "result_types": preferred.get("types") or [],
        **parsed,
    }
    with _GOOGLE_LOCK:
        _GOOGLE_REV_CACHE[ck] = {**out, "_ts": time.monotonic()}
    return out


def google_geocode_locality(village: str, taluk: str, district: str = "Mysuru") -> Optional[dict]:
    """Forward-geocode a locality within Mysuru District via Google Geocoding API (OPTIONAL)."""
    api_key = get_google_maps_api_key()
    if not api_key:
        return None

    from ..geo_utils import is_in_mysuru_district

    address_q = f"{village}, {taluk} Taluk, {district} District, Karnataka, India"
    ck = address_q.strip().lower()
    with _GOOGLE_LOCK:
        cached = _GOOGLE_FWD_CACHE.get(ck)
        if cached and (time.monotonic() - cached.get("_ts", 0)) < 3600:
            return cached.get("data")

    if not _consume_google_quota(1):
        return None
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": address_q,
                "components": "country:IN|administrative_area:Karnataka",
                "bounds": "11.6,75.8|12.8,77.4",
                "language": "en",
                "key": api_key,
            },
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        if payload.get("status") != "OK":
            return None
        for item in payload.get("results") or []:
            loc = (item.get("geometry") or {}).get("location") or {}
            lat_v, lon_v = loc.get("lat"), loc.get("lng")
            if lat_v is None or lon_v is None:
                continue
            lat_f, lon_f = float(lat_v), float(lon_v)
            if is_in_mysuru_district(lat_f, lon_f):
                out = {
                    "lat": lat_f,
                    "lon": lon_f,
                    "display_name": item.get("formatted_address", address_q),
                    "matched_name": village,
                    "place_id": item.get("place_id"),
                    "coordinate_status": "LOCALITY_GEOCODE",
                    "coordinate_source": "Google Geocoding API",
                }
                with _GOOGLE_LOCK:
                    _GOOGLE_FWD_CACHE[ck] = {"data": out, "_ts": time.monotonic()}
                return out
    except Exception as e:
        log.warning("Google forward geocode error: %s", type(e).__name__)
    return None


def google_places_search(query: str, limit: int = 8) -> dict:
    """
    Search Mysuru District places/addresses/localities via Google Places API (OPTIONAL).
    Cached & quota-capped so repeated paid requests never occur.
    """
    api_key = get_google_maps_api_key()
    if not api_key:
        return {"status": "NOT_CONFIGURED", "results": [], "provider": "Google Places API (Optional / Disabled)"}

    from ..geo_utils import is_in_mysuru_district

    q_clean = " ".join((query or "").strip().split())
    ck = (q_clean.lower(), int(limit))
    with _GOOGLE_LOCK:
        cached = _GOOGLE_PLACES_CACHE.get(ck)
        if cached and (time.monotonic() - cached.get("_ts", 0)) < 1800:
            return {k: v for k, v in cached.items() if k != "_ts"}

    if not _consume_google_quota(1):
        return {"status": "QUOTA_LIMIT", "results": [], "provider": "Google Places API"}
    candidates = []
    try:
        ac_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/autocomplete/json",
            params={
                "input": q_clean,
                "location": "12.3052,76.6552",
                "radius": 60000,
                "components": "country:in",
                "language": "en",
                "key": api_key,
            },
            timeout=8,
        )
        ac_resp.raise_for_status()
        ac_data = ac_resp.json() or {}
        if ac_data.get("status") == "OK":
            for pred in (ac_data.get("predictions") or [])[: min(10, max(limit, 5))]:
                pid = pred.get("place_id")
                if not pid:
                    continue
                det_resp = requests.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": pid,
                        "fields": "place_id,name,formatted_address,geometry,types,address_component",
                        "language": "en",
                        "key": api_key,
                    },
                    timeout=8,
                )
                det_resp.raise_for_status()
                det = (det_resp.json() or {}).get("result") or {}
                loc = (det.get("geometry") or {}).get("location") or {}
                if loc.get("lat") is None or loc.get("lng") is None:
                    continue
                lat_f, lon_f = float(loc["lat"]), float(loc["lng"])
                if not is_in_mysuru_district(lat_f, lon_f):
                    continue
                parsed = _extract_google_components(det.get("address_components") or [])
                candidates.append({
                    "place_id": det.get("place_id") or pid,
                    "name": det.get("name") or (pred.get("structured_formatting") or {}).get("main_text") or q_clean,
                    "formatted_address": det.get("formatted_address") or pred.get("description") or "",
                    "latitude": round(lat_f, 6),
                    "longitude": round(lon_f, 6),
                    "types": det.get("types") or pred.get("types") or [],
                    "parsed_components": parsed,
                })
        elif ac_data.get("status") not in ("ZERO_RESULTS", "OK"):
            return {
                "status": "API_ERROR",
                "results": [],
                "provider": "Google Places API",
                "error": ac_data.get("error_message") or ac_data.get("status"),
            }

        if not candidates:
            ts_resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={
                    "query": f"{q_clean}, Mysuru District, Karnataka, India",
                    "location": "12.3052,76.6552",
                    "radius": 60000,
                    "language": "en",
                    "key": api_key,
                },
                timeout=8,
            )
            ts_resp.raise_for_status()
            ts_data = ts_resp.json() or {}
            if ts_data.get("status") == "OK":
                for item in (ts_data.get("results") or [])[:limit]:
                    loc = (item.get("geometry") or {}).get("location") or {}
                    if loc.get("lat") is None or loc.get("lng") is None:
                        continue
                    lat_f, lon_f = float(loc["lat"]), float(loc["lng"])
                    if not is_in_mysuru_district(lat_f, lon_f):
                        continue
                    candidates.append({
                        "place_id": item.get("place_id"),
                        "name": item.get("name") or q_clean,
                        "formatted_address": item.get("formatted_address") or "",
                        "latitude": round(lat_f, 6),
                        "longitude": round(lon_f, 6),
                        "types": item.get("types") or [],
                        "parsed_components": {},
                    })
    except Exception as e:
        log.warning("Google Places search failed: %s", type(e).__name__)
        return {
            "status": "UNAVAILABLE",
            "results": [],
            "provider": "Google Places API",
            "error": f"Google Places request failed ({type(e).__name__}).",
        }

    out = {
        "status": "OK" if candidates else "ZERO_RESULTS",
        "results": candidates,
        "provider": "Google Places API",
    }
    with _GOOGLE_LOCK:
        _GOOGLE_PLACES_CACHE[ck] = {**out, "_ts": time.monotonic()}
    return out

# Mapping from our categories to Google Places types
GOOGLE_TYPES = {
    "school": "school",
    "hospital": "hospital",
    "clinic": "doctor",
    "supermarket": "supermarket",
    "market": "supermarket",  # Google doesn't have a distinct 'marketplace'
    "pharmacy": "pharmacy",
    "bus_stop": "transit_station",
    "railway_station": "train_station",
    "bank": "bank",
    "police": "police",
    "atm": "atm",
    "park": "park",
}

class GooglePlacesAdapter(BaseAdapter):
    def __init__(self):
        super().__init__("Google Places")

    @property
    def api_key(self):
        return get_google_maps_api_key()

    def check_status(self) -> dict:
        if not self.api_key:
            return {"status": "DISABLED", "message": "Optional provider disabled or API key not configured"}
        return {"status": "CONNECTED", "message": "Enabled within daily quota"}

    def fetch_facilities(self, lat: float, lon: float, radius_m: int) -> dict:
        api_key = self.api_key
        if not api_key:
            return None

        ck = (round(float(lat), 3), round(float(lon), 3), int(radius_m))
        with _GOOGLE_LOCK:
            cached = _GOOGLE_FAC_CACHE.get(ck)
            if cached and (time.monotonic() - cached.get("_ts", 0)) < 1800:
                res_copy = {}
                for cat, items in cached["data"].items():
                    recomputed = []
                    for it in items:
                        c_it = dict(it)
                        c_it["distance_km"] = round(self.haversine(lat, lon, c_it["latitude"], c_it["longitude"]), 3)
                        recomputed.append(c_it)
                    recomputed.sort(key=lambda x: x["distance_km"])
                    res_copy[cat] = recomputed
                return res_copy

        if not _consume_google_quota(len(GOOGLE_TYPES)):
            log.warning("GooglePlacesAdapter skipped: daily quota limit reached.")
            return None
            
        results = {k: [] for k in GOOGLE_TYPES.keys()}
        
        # We can either make 1 call per type or try to make fewer calls.
        # Google Places nearby search allows only one type per request usually,
        # but we can do a keyword search. Let's just do a type-based nearby search for the most critical ones
        # to avoid blowing up quota, or we can just make 12 requests.
        # Let's make individual requests for the categories.
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

        def _fetch_cat(cat: str, gtype: str):
            cat_items = []
            params = {
                "location": f"{lat},{lon}",
                "radius": radius_m,
                "type": gtype,
                "key": self.api_key
            }
            try:
                resp = requests.get(url, params=params, timeout=6)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") not in ["OK", "ZERO_RESULTS"]:
                    log.warning(f"Google Places API error for {cat}: {data.get('status')}")
                    return cat, cat_items

                for place in data.get("results", []):
                    plat = place["geometry"]["location"]["lat"]
                    plon = place["geometry"]["location"]["lng"]
                    dist = self.haversine(lat, lon, plat, plon)

                    cat_items.append({
                        "id": f"google_{place.get('place_id')}",
                        "name": place.get("name"),
                        "category": cat,
                        "latitude": plat,
                        "longitude": plon,
                        "distance_km": round(dist, 3),
                        "distance_type": "calculated",
                        "source": "Google Places",
                        "source_type": "google_places",
                        "source_url": "https://maps.google.com/?q=place_id:" + place.get("place_id", ""),
                        "retrieved_at": self.now_iso(),
                        "confidence": "secondary_gis"
                    })
            except Exception as e:
                log.warning(f"GooglePlacesAdapter error for {cat}: {e}")
            return cat, cat_items

        import concurrent.futures as _cf
        pool = _cf.ThreadPoolExecutor(max_workers=6)
        try:
            futs = [pool.submit(_fetch_cat, cat, gtype) for cat, gtype in GOOGLE_TYPES.items()]
            done, _ = _cf.wait(futs, timeout=12)
            for fut in done:
                try:
                    cat, items = fut.result()
                    results[cat] = items
                except Exception:
                    pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        if any(results.values()):
            with _GOOGLE_LOCK:
                _GOOGLE_FAC_CACHE[ck] = {"data": results, "_ts": time.monotonic()}
        return results
