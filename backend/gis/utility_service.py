"""
District-Wide GIS Utility & Infrastructure Assessment Service (Mysuru District, Karnataka).

Simplified 4 Essential Infrastructure Categories ONLY:
  1. Road Connectivity
  2. Water Availability
  3. Electricity Availability
  4. Public Transport

Strict separation & honesty rules:
- User-Confirmed Availability is tracked strictly separately from GIS-Mapped Infrastructure:
    * "User Reported — Available"
    * "User Reported — Not Available"
    * "Not Confirmed" (when unanswered / Unknown — NEVER converted to "Not Available")
- GIS-Mapped Infrastructure uses canonical statuses:
    * "Available / Mapped" (displayed compactly as Mapped)
    * "Not Found in GIS Mapping" (with explicit "Mapping Data Not Found" note — NEVER "Absent" or "Unavailable")
    * "Unknown / Insufficient Data" (on external API failure/timeout)
    * "Officially Verified" (reserved only for genuine authoritative records)
- Nearby lake/waterbody/river NEVER equates to piped/potable water supply.
- Nearby power line/substation/transformer NEVER confirms an active property electricity connection.
- Nearby mapped roads establish road proximity/class only, NOT guaranteed direct legal access.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from gis.adapters.osm import (
    OSMAdapter,
    OVERPASS_ENDPOINTS,
    is_overpass_circuit_open,
    trip_overpass_circuit,
    reset_overpass_circuit,
)
from gis.geo_utils import haversine_km as haversine

log = logging.getLogger(__name__)

# Canonical GIS & User-Confirmed classifications
STATUS_AVAILABLE = "Available / Mapped"
STATUS_NOT_FOUND = "Not Found in GIS Mapping"
STATUS_MAPPING_NOT_FOUND = "Mapping Data Not Found"
STATUS_UNKNOWN = "Unknown / Insufficient Data"
STATUS_VERIFIED = "Officially Verified"

USER_CONF_YES = "User Reported — Available"
USER_CONF_NO = "User Reported — Not Available"
USER_CONF_UNANSWERED = "Not Confirmed"

_UTILITY_CACHE: Dict[Tuple[float, float], Dict[str, Any]] = {}
_UTILITY_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 3600  # 1 hour

_SOURCE_LABEL = "OpenStreetMap (Overpass API) + GIS Facility Layer"


def _format_user_confirmation(val: Any) -> str:
    """Strictly convert optional Yes/No/Unknown into canonical User-Confirmed labels."""
    if val is None:
        return USER_CONF_UNANSWERED
    s = str(val).strip().upper()
    if s in ("YES", "TRUE", "1", "AVAILABLE"):
        return USER_CONF_YES
    if s in ("NO", "FALSE", "0", "NOT AVAILABLE", "UNAVAILABLE"):
        return USER_CONF_NO
    return USER_CONF_UNANSWERED


def _clean_user_val(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.upper() in ("UNKNOWN", "NONE", "N/A", "NULL", "AUTO", "NOT CONFIRMED", "NOT SURE"):
        return None
    return s


def _extract_elem_coords(el: dict) -> Tuple[Optional[float], Optional[float]]:
    if el.get("lat") is not None and el.get("lon") is not None:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center") or {}
    if center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    return None, None


def _elem_label(el: dict, fallback: str) -> str:
    tags = el.get("tags") or {}
    name = tags.get("name") or tags.get("name:en") or tags.get("ref") or tags.get("operator")
    sub = (
        tags.get("highway")
        or tags.get("power")
        or tags.get("man_made")
        or tags.get("amenity")
        or tags.get("pump")
    )
    if name and sub:
        return f"{str(name).strip()} ({sub})"
    if name:
        return str(name).strip()
    return f"{fallback} ({sub})" if sub else fallback


def _fetch_utility_overpass(lat: float, lon: float, timeout: int = 10) -> Dict[str, Any]:
    """Spatial bbox Overpass query strictly covering Road Connectivity, Water Availability, and Electricity Availability."""
    cache_key = (round(float(lat), 3), round(float(lon), 3))
    with _UTILITY_CACHE_LOCK:
        cached = _UTILITY_CACHE.get(cache_key)
        if cached and (time.time() - cached.get("_ts", 0)) < _CACHE_TTL_SECONDS:
            return cached

    if is_overpass_circuit_open():
        log.info("Utility Overpass skipped (Overpass circuit breaker OPEN).")
        return {
            "ok": False,
            "elements": [],
            "error": "Overpass circuit breaker open",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "_ts": time.time(),
        }

    d15 = 0.014  # ~1.5 km for mapped roads
    d28 = 0.026  # ~3.0 km for water & electricity infrastructure
    rs, rw, rn, re_ = round(lat - d15, 5), round(lon - d15, 5), round(lat + d15, 5), round(lon + d15, 5)
    s, w, n, e = round(lat - d28, 5), round(lon - d28, 5), round(lat + d28, 5), round(lon + d28, 5)

    query_timeout = max(6, min(int(timeout or 10), 10))
    query = f"""
    [out:json][timeout:{query_timeout}];
    (
      // Road Connectivity (~1.5 km local + ~3.0 km arterial)
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street)$"]({rs},{rw},{rn},{re_});
      way["highway"~"^(trunk|primary|secondary|tertiary)$"]({s},{w},{n},{e});

      // Water Availability: piped water works, pipelines, reservoirs/tanks, taps & wells (NEVER lakes/canals)
      node["man_made"~"^(water_works|pumping_station|water_tower|storage_tank|reservoir_covered|water_tap|water_well)$"]({s},{w},{n},{e});
      way["man_made"~"^(water_works|pumping_station|water_tower|storage_tank|reservoir_covered|water_well)$"]({s},{w},{n},{e});
      way["man_made"="pipeline"]["substance"="water"]({s},{w},{n},{e});
      way["landuse"="reservoir"]({s},{w},{n},{e});
      node["amenity"~"^(drinking_water|water_point)$"]({s},{w},{n},{e});
      node["drinking_water"="yes"]({s},{w},{n},{e});
      node["pump"~"^(manual|powered|yes)$"]({s},{w},{n},{e});

      // Electricity Availability: substations, transformers & power distribution lines
      node["power"~"^(substation|transformer|plant|pole|tower)$"]({s},{w},{n},{e});
      way["power"~"^(substation|transformer|line|minor_line|cable|plant)$"]({s},{w},{n},{e});
    );
    out center 300;
    """

    import concurrent.futures as _cf
    adapter = OSMAdapter(timeout=query_timeout)
    last_err = None
    pool = _cf.ThreadPoolExecutor(max_workers=len(OVERPASS_ENDPOINTS))
    try:
        futs = {pool.submit(adapter._post_overpass, ep, query, query_timeout + 1): ep for ep in OVERPASS_ENDPOINTS}
        pending = set(futs.keys())
        deadline = time.monotonic() + (query_timeout + 2)
        while pending:
            rem = max(0.1, deadline - time.monotonic())
            done, pending = _cf.wait(pending, timeout=rem, return_when=_cf.FIRST_COMPLETED)
            if not done:
                last_err = "Overpass utility endpoints timed out"
                break
            for fut in done:
                ep = futs[fut]
                try:
                    data = fut.result()
                    if not isinstance(data, dict):
                        last_err = f"No JSON response returned from {ep}"
                        continue
                    elems = data.get("elements", []) or []
                    if data.get("remark") and not elems:
                        last_err = f"Overpass remark error at {ep}: {data.get('remark')}"
                        continue
                    reset_overpass_circuit()
                    result = {
                        "ok": True,
                        "elements": elems,
                        "endpoint": ep,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "_ts": time.time(),
                    }
                    with _UTILITY_CACHE_LOCK:
                        _UTILITY_CACHE[cache_key] = result
                    return result
                except Exception as exc:
                    last_err = str(exc)
                    log.warning("Utility Overpass endpoint %s failed: %s", ep, exc)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    trip_overpass_circuit(90)
    return {
        "ok": False,
        "elements": [],
        "error": last_err or "Overpass unavailable",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "_ts": time.time(),
    }


def _fetch_utility_nominatim_fallback(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fast bounded Nominatim fallback when Overpass is unavailable:
    - Road Connectivity: /reverse?zoom=17 + [highway=tertiary]/[highway=secondary] inside 3 km
    - Water Infrastructure: [man_made=water_tower] / 'water tank' inside 3 km (NEVER lakes/canals)
    - Electricity Infrastructure: [power=substation] / 'substation' inside 3 km
    Returns discovered elements only; empty categories stay UNKNOWN (never NOT_FOUND).
    """
    import concurrent.futures as _cf
    import json as _json
    import urllib.parse as _up
    import urllib.request as _ur

    cache_key = (round(float(lat), 4), round(float(lon), 4), "nom_util")
    with _UTILITY_CACHE_LOCK:
        cached = _UTILITY_CACHE.get(cache_key)
        if cached and (time.time() - cached.get("_ts", 0)) < _CACHE_TTL_SECONDS:
            return cached

    headers = {"User-Agent": "SmartLandEvaluation/1.0", "Accept-Language": "en"}
    d = 0.027  # ~3 km
    vb = f"{lon - d},{lat + d},{lon + d},{lat - d}"
    road_els: List[dict] = []
    water_els: List[dict] = []
    elec_els: List[dict] = []

    def _rev_road():
        url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=17&addressdetails=1"
        try:
            with _ur.urlopen(_ur.Request(url, headers=headers), timeout=4) as r:
                rv = _json.loads(r.read().decode("utf-8"))
                if rv.get("category") == "highway" and rv.get("lat") and rv.get("lon"):
                    addr = rv.get("address") or {}
                    nm = rv.get("name") or addr.get("road") or "Local Approach Road"
                    return {
                        "type": rv.get("osm_type") or "way",
                        "id": rv.get("osm_id") or 0,
                        "lat": float(rv["lat"]),
                        "lon": float(rv["lon"]),
                        "tags": {"highway": rv.get("type") or "residential", "name": nm},
                    }
        except Exception:
            pass
        return None

    def _nom_search(term: str):
        url = "https://nominatim.openstreetmap.org/search?" + _up.urlencode({
            "format": "json", "q": term, "viewbox": vb, "bounded": 1, "limit": 5,
        })
        try:
            with _ur.urlopen(_ur.Request(url, headers=headers), timeout=5) as r:
                return _json.loads(r.read().decode("utf-8")) or []
        except Exception:
            return []

    pool = _cf.ThreadPoolExecutor(max_workers=3)
    try:
        f_rev = pool.submit(_rev_road)
        f_wat = pool.submit(_nom_search, "water tank")
        f_pow = pool.submit(_nom_search, "[power=substation]")
        _cf.wait((f_rev, f_wat, f_pow), timeout=6)
        if f_rev.done() and f_rev.result():
            road_els.append(f_rev.result())
        if f_wat.done():
            for it in f_wat.result() or []:
                ic, itype = str(it.get("class") or "").lower(), str(it.get("type") or "").lower()
                if ic == "man_made" and itype in ("water_tower", "water_works", "storage_tank", "pumping_station", "water_well"):
                    water_els.append({
                        "type": it.get("osm_type") or "node",
                        "id": it.get("osm_id") or 0,
                        "lat": float(it["lat"]),
                        "lon": float(it["lon"]),
                        "tags": {"man_made": itype, "name": it.get("name") or "Water Tank"},
                    })
        if f_pow.done():
            for it in f_pow.result() or []:
                ic, itype = str(it.get("class") or "").lower(), str(it.get("type") or "").lower()
                if ic == "power" and itype in ("substation", "transformer", "plant"):
                    elec_els.append({
                        "type": it.get("osm_type") or "node",
                        "id": it.get("osm_id") or 0,
                        "lat": float(it["lat"]),
                        "lon": float(it["lon"]),
                        "tags": {"power": itype, "name": it.get("name") or "Substation"},
                    })
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    out = {
        "road_els": road_els,
        "water_els": water_els,
        "elec_els": elec_els,
        "_ts": time.time(),
    }
    with _UTILITY_CACHE_LOCK:
        _UTILITY_CACHE[cache_key] = out
    return out


def _nearest_from_bucket(
    lat: float,
    lon: float,
    items: List[dict],
    label_fallback: str,
    max_distance_km: Optional[float] = None,
) -> dict:
    if not items:
        return {"count": 0, "nearest_name": None, "nearest_class": None, "nearest_distance_km": None}
    best_dist = None
    best_name = None
    best_class = None
    seen = set()
    unique_count = 0
    for el in items:
        elat, elon = _extract_elem_coords(el)
        if elat is None or elon is None:
            continue
        key = (round(elat, 5), round(elon, 5), el.get("type"), el.get("id"))
        if key in seen:
            continue
        d = round(haversine(lat, lon, elat, elon), 3)
        if max_distance_km is not None and d > max_distance_km:
            continue
        seen.add(key)
        unique_count += 1
        if best_dist is None or d < best_dist:
            best_dist = d
            best_name = _elem_label(el, label_fallback)
            tags = el.get("tags") or {}
            best_class = (
                tags.get("highway")
                or tags.get("power")
                or tags.get("man_made")
                or tags.get("amenity")
            )
    return {
        "count": unique_count,
        "nearest_name": best_name,
        "nearest_class": best_class,
        "nearest_distance_km": best_dist,
    }


def _facility_entry(facilities_raw: Optional[dict], key: str) -> dict:
    raw = (facilities_raw or {}).get(key) or {}
    if hasattr(raw, "to_dict"):
        raw = raw.to_dict()
    return raw if isinstance(raw, dict) else {}


def _build_record(
    key: str,
    label: str,
    group: str,
    status: str,
    system_finding: str,
    evidence: str,
    verification: str,
    mapped_count: Optional[int],
    nearest_facility: Optional[str],
    nearest_distance_km: Optional[float],
    search_radius_km: float,
    source: str,
    retrieved_at: str,
    user_confirmation: str = USER_CONF_UNANSWERED,
    road_class: Optional[str] = None,
    connection_verified: bool = False,
) -> dict:
    return {
        "key": key,
        "infrastructure": label,
        "group": group,
        "status": status,
        "user_confirmation": user_confirmation,
        "system_finding": system_finding,
        "evidence": evidence,
        "verification": verification,
        "mapped_count": mapped_count,
        "nearest_facility": nearest_facility,
        "nearest_road_class": road_class,
        "nearest_distance_km": nearest_distance_km,
        "search_radius_km": search_radius_km,
        "source": source,
        "retrieved_at": retrieved_at,
        "connection_verified": connection_verified,
        "user_reported_value": user_confirmation if user_confirmation != USER_CONF_UNANSWERED else None,
        "verification_limitation": (
            "GIS infrastructure mapping indicates nearby mapped features only. "
            "It does not independently confirm property-level utility connections or legal road access."
        ),
    }


def assess_property_utilities(
    lat: Optional[float],
    lon: Optional[float],
    facilities_raw: Optional[dict] = None,
    user_inputs: Optional[dict] = None,
    overpass_fetcher=None,
) -> Dict[str, Any]:
    """
    Build the simplified 4-category Essential Infrastructure & Connectivity assessment:
      1. road_connectivity
      2. water_availability
      3. electricity_availability
      4. public_transport
    """
    user_inputs = user_inputs or {}
    retrieved_at = datetime.now(timezone.utc).isoformat()

    user_confirmations = {
        "road_access": _format_user_confirmation(user_inputs.get("road_access")),
        "water_supply": _format_user_confirmation(user_inputs.get("water_supply")),
        "electricity": _format_user_confirmation(user_inputs.get("electricity_available")),
        "public_transport": _format_user_confirmation(user_inputs.get("public_transport_available")),
    }
    user_reported_extras = {
        "water_source_type": _clean_user_val(user_inputs.get("water_source_type")),
        "road_quality": _clean_user_val(user_inputs.get("road_quality")),
        "road_width_ft": (
            f"{user_inputs['road_width_ft']} ft"
            if user_inputs.get("road_width_ft") not in (None, "", "Unknown")
            else None
        ),
    }

    if lat is None or lon is None:
        return {
            "status": STATUS_UNKNOWN,
            "data_source": "None (Coordinates Missing)",
            "retrieved_at": retrieved_at,
            "gis_available": False,
            "coverage_pct": 0.0,
            "user_confirmations": user_confirmations,
            "user_reported_inputs": {k: v for k, v in user_reported_extras.items() if v is not None},
            "categories": [],
            "categories_by_key": {},
            "summary_metrics": {},
            "limitation_note": "Coordinates unavailable; GIS infrastructure mapping could not be queried.",
        }

    lat_f, lon_f = float(lat), float(lon)
    raw = overpass_fetcher(lat_f, lon_f) if overpass_fetcher else _fetch_utility_overpass(lat_f, lon_f)
    gis_ok = bool(raw.get("ok"))
    retrieved_at = raw.get("retrieved_at") or retrieved_at
    elements = raw.get("elements") or []

    road_els: List[dict] = []
    water_els: List[dict] = []
    electricity_els: List[dict] = []

    for el in elements:
        tags = el.get("tags") or {}
        if not tags:
            continue
        mm = str(tags.get("man_made", "")).lower()
        am = str(tags.get("amenity", "")).lower()
        pw = str(tags.get("power", "")).lower()
        hw = str(tags.get("highway", "")).lower()
        lu = str(tags.get("landuse", "")).lower()
        sub = str(tags.get("substance", "")).lower()
        dw = str(tags.get("drinking_water", "")).lower()
        pmp = str(tags.get("pump", "")).lower()

        if hw in (
            "motorway", "trunk", "primary", "secondary", "tertiary",
            "unclassified", "residential", "service", "living_street"
        ):
            road_els.append(el)

        if (
            mm in ("water_works", "pumping_station", "water_tower", "storage_tank", "reservoir_covered", "water_tap", "water_well")
            or (mm == "pipeline" and sub == "water")
            or lu == "reservoir"
            or am in ("drinking_water", "water_point")
            or dw == "yes"
            or pmp in ("manual", "powered", "yes")
        ):
            water_els.append(el)

        if pw in ("substation", "transformer", "plant", "line", "minor_line", "cable", "pole", "tower"):
            electricity_els.append(el)

    used_nom_fallback = False
    if not gis_ok and overpass_fetcher is None:
        nom_fb = _fetch_utility_nominatim_fallback(lat_f, lon_f)
        road_els.extend(nom_fb.get("road_els") or [])
        water_els.extend(nom_fb.get("water_els") or [])
        electricity_els.extend(nom_fb.get("elec_els") or [])
        used_nom_fallback = True

    categories: List[dict] = []

    # 1. ROAD CONNECTIVITY
    rd_st = _nearest_from_bucket(lat_f, lon_f, road_els, "Mapped Road", max_distance_km=3.0)
    if rd_st["count"] > 0 and (gis_ok or used_nom_fallback):
        rcls = rd_st["nearest_class"] or "road"
        src_lbl = "OpenStreetMap (Overpass API)" if gis_ok else "OpenStreetMap (Nominatim Fallback)"
        road_rec = _build_record(
            key="road_connectivity",
            label="Road Connectivity",
            group="Road",
            status=STATUS_AVAILABLE,
            system_finding=f"Nearest Mapped Road: {rd_st['nearest_name']} (Class: {rcls}; Proximity Only)",
            evidence=f"{rd_st['count']} road segment(s) mapped <=3 km; direct legal parcel access not confirmed by GIS.",
            verification="Verify Registered Direct Approach Road & Width",
            mapped_count=rd_st["count"],
            nearest_facility=rd_st["nearest_name"],
            nearest_distance_km=rd_st["nearest_distance_km"],
            search_radius_km=3.0,
            source=src_lbl,
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["road_access"],
            road_class=rcls,
        )
    elif not gis_ok:
        road_rec = _build_record(
            key="road_connectivity",
            label="Road Connectivity",
            group="Road",
            status=STATUS_UNKNOWN,
            system_finding="GIS Query Unavailable",
            evidence="OpenStreetMap Overpass road query unavailable; road proximity unconfirmed.",
            verification="Verify Legal Approach Road on Survey Sketch",
            mapped_count=None,
            nearest_facility=None,
            nearest_distance_km=None,
            search_radius_km=3.0,
            source="OpenStreetMap Overpass [Unavailable]",
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["road_access"],
        )
    else:
        road_rec = _build_record(
            key="road_connectivity",
            label="Road Connectivity",
            group="Road",
            status=STATUS_NOT_FOUND,
            system_finding="Not Found in GIS Mapping (<=3 km)",
            evidence="No classified OSM road segment mapped within 3.0 km; village or layout road may be unmapped.",
            verification="Inspect Approach Road Physically & on Survey Sketch",
            mapped_count=0,
            nearest_facility=None,
            nearest_distance_km=None,
            search_radius_km=3.0,
            source="OpenStreetMap (Overpass API)",
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["road_access"],
        )
    categories.append(road_rec)

    # 2. WATER AVAILABILITY
    wt_st = _nearest_from_bucket(lat_f, lon_f, water_els, "Water Infrastructure", max_distance_km=3.0)
    if wt_st["count"] > 0 and (gis_ok or used_nom_fallback):
        src_lbl = "OpenStreetMap (Overpass API)" if gis_ok else "OpenStreetMap (Nominatim Fallback)"
        water_rec = _build_record(
            key="water_availability",
            label="Water Availability",
            group="Water",
            status=STATUS_AVAILABLE,
            system_finding=f"Water Infrastructure Mapped ({wt_st['count']} <=3 km; Household Tap Unverified)",
            evidence=f"Nearest mapped water infra: {wt_st['nearest_name']} at {wt_st['nearest_distance_km']:.3f} km.",
            verification="Verify Household Piped Connection / Borewell Yield",
            mapped_count=wt_st["count"],
            nearest_facility=wt_st["nearest_name"],
            nearest_distance_km=wt_st["nearest_distance_km"],
            search_radius_km=3.0,
            source=src_lbl,
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["water_supply"],
            road_class=wt_st.get("nearest_class"),
        )
    elif not gis_ok:
        water_rec = _build_record(
            key="water_availability",
            label="Water Availability",
            group="Water",
            status=STATUS_UNKNOWN,
            system_finding="GIS Query Unavailable",
            evidence="OpenStreetMap Overpass water infrastructure query unavailable.",
            verification="Verify Municipal Tap / Borewell Connection On-Site",
            mapped_count=None,
            nearest_facility=None,
            nearest_distance_km=None,
            search_radius_km=3.0,
            source="OpenStreetMap Overpass [Unavailable]",
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["water_supply"],
        )
    else:
        water_rec = _build_record(
            key="water_availability",
            label="Water Availability",
            group="Water",
            status=STATUS_NOT_FOUND,
            system_finding="Not Found in GIS Mapping (Local Pipes / Borewells Rarely Mapped in OSM)",
            evidence="Zero piped water works, tanks, taps, or wells mapped <=3 km in OSM; does NOT prove absence of water.",
            verification="Check MCC / KUWSDB / Gram Panchayat Supply & Borewells",
            mapped_count=0,
            nearest_facility=None,
            nearest_distance_km=None,
            search_radius_km=3.0,
            source="OpenStreetMap (Overpass API)",
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["water_supply"],
        )
    categories.append(water_rec)

    # 3. ELECTRICITY AVAILABILITY
    el_st = _nearest_from_bucket(lat_f, lon_f, electricity_els, "Power Grid Asset", max_distance_km=3.0)
    if el_st["count"] > 0 and (gis_ok or used_nom_fallback):
        src_lbl = "OpenStreetMap (Overpass API)" if gis_ok else "OpenStreetMap (Nominatim Fallback)"
        elec_rec = _build_record(
            key="electricity_availability",
            label="Electricity Availability",
            group="Electricity",
            status=STATUS_AVAILABLE,
            system_finding=f"Electricity Grid Infra Mapped ({el_st['count']} <=3 km; Active Meter Unverified)",
            evidence=f"Nearest mapped grid asset: {el_st['nearest_name']} at {el_st['nearest_distance_km']:.3f} km.",
            verification="Verify Active CHESCOM Meter / Service Connection",
            mapped_count=el_st["count"],
            nearest_facility=el_st["nearest_name"],
            nearest_distance_km=el_st["nearest_distance_km"],
            search_radius_km=3.0,
            source=src_lbl,
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["electricity"],
            road_class=el_st.get("nearest_class"),
        )
    elif not gis_ok:
        elec_rec = _build_record(
            key="electricity_availability",
            label="Electricity Availability",
            group="Electricity",
            status=STATUS_UNKNOWN,
            system_finding="GIS Query Unavailable",
            evidence="OpenStreetMap Overpass electricity grid query unavailable.",
            verification="Verify Active CHESCOM Meter & LT Feeder On-Site",
            mapped_count=None,
            nearest_facility=None,
            nearest_distance_km=None,
            search_radius_km=3.0,
            source="OpenStreetMap Overpass [Unavailable]",
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["electricity"],
        )
    else:
        elec_rec = _build_record(
            key="electricity_availability",
            label="Electricity Availability",
            group="Electricity",
            status=STATUS_NOT_FOUND,
            system_finding="Not Found in GIS Mapping (Local LT Lines Often Unmapped in OSM)",
            evidence="Zero substations/power lines mapped <=3 km in OSM; does NOT imply electricity is unavailable.",
            verification="Check CHESCOM Feeder & Service Availability Locally",
            mapped_count=0,
            nearest_facility=None,
            nearest_distance_km=None,
            search_radius_km=3.0,
            source="OpenStreetMap (Overpass API)",
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["electricity"],
        )
    categories.append(elec_rec)

    # 4. PUBLIC TRANSPORT
    bs_entry = _facility_entry(facilities_raw, "bus_stop")
    rs_entry = _facility_entry(facilities_raw, "railway_station")
    bs_st = bs_entry.get("status")
    rs_st = rs_entry.get("status")
    bs_dist = bs_entry.get("nearest_distance_km")
    rs_dist = rs_entry.get("nearest_distance_km")
    bs_name = (bs_entry.get("nearest") or {}).get("name")
    rs_name = (rs_entry.get("nearest") or {}).get("name")
    bs_c3 = bs_entry.get("count_within_3km") or 0
    rs_c5 = rs_entry.get("count_within_5km") or 0
    has_in_radius_transit = (bs_dist is not None and bs_dist <= 3.0) or (rs_dist is not None and rs_dist <= 5.0)
    transit_incomplete = (not bs_entry and not rs_entry) or (
        bs_st in (None, "SOURCE_UNAVAILABLE", "PARTIAL") and rs_st in (None, "SOURCE_UNAVAILABLE", "PARTIAL")
    )
    if has_in_radius_transit:
        nearest_dist = bs_dist if (bs_dist is not None and bs_dist <= 3.0 and (rs_dist is None or bs_dist <= rs_dist)) else rs_dist
        nearest_lbl = bs_name if nearest_dist == bs_dist else rs_name
        pt_rec = _build_record(
            key="public_transport",
            label="Public Transport",
            group="Public Transport",
            status=STATUS_AVAILABLE,
            system_finding=(
                f"Transit Mapped ({f'Bus: {bs_dist:.2f} km' if bs_dist is not None else 'Bus: Not Found <=3km'}; "
                f"{f'Rail: {rs_dist:.2f} km' if rs_dist is not None else 'Rail: Not Found <=5km'})"
            ),
            evidence=(
                f"Bus stops <=3 km: {bs_c3}{f' (nearest {bs_name} @ {bs_dist:.2f} km)' if bs_name and bs_dist is not None else ''}; "
                f"Railway stations <=5 km: {rs_c5}{f' (nearest {rs_name} @ {rs_dist:.2f} km)' if rs_name and rs_dist is not None else ''}."
            ),
            verification="Confirm Active Bus Route Frequency On-Site",
            mapped_count=int(bs_c3) + int(rs_c5),
            nearest_facility=nearest_lbl,
            nearest_distance_km=round(float(nearest_dist), 3) if nearest_dist is not None else None,
            search_radius_km=3.0,
            source=bs_entry.get("source") or rs_entry.get("source") or _SOURCE_LABEL,
            retrieved_at=bs_entry.get("retrieved_at") or retrieved_at,
            user_confirmation=user_confirmations["public_transport"],
        )
    elif transit_incomplete or bs_st in (None, "SOURCE_UNAVAILABLE", "PARTIAL"):
        # Never report NOT FOUND when bus_stop query was unavailable or incomplete (PARTIAL)
        pt_rec = _build_record(
            key="public_transport",
            label="Public Transport",
            group="Public Transport",
            status=STATUS_UNKNOWN,
            system_finding="GIS Transit Query Incomplete / Unavailable",
            evidence=(
                f"Overpass transit query incomplete (bus status={bs_st or 'UNAVAILABLE'}"
                f"{f'; nearest mapped={bs_name} @ {bs_dist:.2f} km' if bs_name and bs_dist is not None else ''})."
            ),
            verification="Check KSRTC / City Bus Frequency Locally",
            mapped_count=None,
            nearest_facility=bs_name or rs_name,
            nearest_distance_km=bs_dist or rs_dist,
            search_radius_km=3.0,
            source=bs_entry.get("source") or _SOURCE_LABEL,
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["public_transport"],
        )
    else:
        pt_rec = _build_record(
            key="public_transport",
            label="Public Transport",
            group="Public Transport",
            status=STATUS_NOT_FOUND,
            system_finding="Not Found in GIS Mapping (<=3 km Bus / <=5 km Rail)",
            evidence=f"Nearest transit beyond radius (bus={bs_dist}, rail={rs_dist}). Informal village stops may be unmapped.",
            verification="Check Rural KSRTC Halt Stops Locally",
            mapped_count=0,
            nearest_facility=bs_name or rs_name,
            nearest_distance_km=bs_dist or rs_dist,
            search_radius_km=3.0,
            source=_SOURCE_LABEL,
            retrieved_at=retrieved_at,
            user_confirmation=user_confirmations["public_transport"],
        )
    categories.append(pt_rec)

    by_key = {c["key"]: c for c in categories}
    # Canonical & backward-compatible aliases for scoring/reporting
    by_key["nearest_road"] = road_rec
    by_key["water_supply"] = water_rec
    by_key["electricity"] = elec_rec

    evaluated_cnt = sum(1 for c in categories if c["status"] != STATUS_UNKNOWN)
    coverage_pct = round((evaluated_cnt / len(categories)) * 100.0, 1) if categories else 0.0
    any_data_available = gis_ok or any(c["status"] == STATUS_AVAILABLE for c in categories)
    overall_status = (
        STATUS_AVAILABLE
        if any(c["status"] == STATUS_AVAILABLE for c in categories)
        else (STATUS_UNKNOWN if not any_data_available else STATUS_NOT_FOUND)
    )

    return {
        "status": overall_status,
        "data_source": (
            _SOURCE_LABEL if gis_ok
            else ("OpenStreetMap (Nominatim Partial Fallback)" if any(c["status"] == STATUS_AVAILABLE for c in categories)
                  else "OpenStreetMap Overpass [Unavailable]")
        ),
        "retrieved_at": retrieved_at,
        "gis_available": any_data_available,
        "coverage_pct": coverage_pct,
        "user_confirmations": user_confirmations,
        "user_reported_inputs": {k: v for k, v in user_reported_extras.items() if v is not None},
        "categories": categories,
        "categories_by_key": by_key,
        "summary_metrics": {
            "nearest_road_name": rd_st["nearest_name"],
            "nearest_road_class": rd_st["nearest_class"],
            "nearest_road_distance_km": rd_st["nearest_distance_km"],
            "water_infra_count_3km": wt_st["count"],
            "water_infra_distance_km": wt_st["nearest_distance_km"],
            "electricity_infra_count_3km": el_st["count"],
            "electricity_infra_distance_km": el_st["nearest_distance_km"],
            "bus_stop_distance_km": bs_dist,
            "railway_distance_km": rs_dist,
            "bus_stops_3km": bs_c3,
            "railway_stations_5km": rs_c5,
        },
        "limitation_note": (
            "GIS infrastructure mapping indicates nearby mapped facilities only. "
            "It does not independently confirm property-level utility connections or legal road access."
        ),
    }
