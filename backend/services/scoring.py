"""
Scoring service: Transparent, documented formulas for all evaluation scores.

All scores are 0–100. Every formula is documented below.
No arbitrary numbers — each weight is justified.
"""
import math
import logging

# Default weights (fractional, not percentage) used when no active WeightageVersion exists
# facility weight removed from scoring (now informational-only);
# weight redistributed: location +0.05, infrastructure +0.10, utility +0.05, environment -0.05
WEIGHTS = {
    "price":          0.30,
    "location":       0.25,
    "facility":       0.00,   # INFORMATIONAL ONLY — does not affect overall score
    "environment":    0.10,
    "infrastructure": 0.20,
    "utility":        0.15,
}

log = logging.getLogger(__name__)


# ─────────────────────────────────────────
# LOCATION SCORE (max 100)
# ─────────────────────────────────────────

def calc_location_score(data: dict) -> dict:
    breakdown = {}
    notes = []
    
    total_pts = 0
    max_pts = 0

    # 1. Road accessibility (0–25)
    road_pts = None
    road_width = _safe_float(data.get("road_width_ft"))
    road_quality = str(data.get("road_quality", "")).strip()
    
    if road_width is not None or road_quality:
        road_pts = 0
        if road_width is not None:
            if road_width >= 60: road_pts += 15
            elif road_width >= 40: road_pts += 12
            elif road_width >= 30: road_pts += 9
            elif road_width >= 20: road_pts += 6
            elif road_width >= 10: road_pts += 3
            else: road_pts += 1
        
        quality_map = {"macadam/asphalt": 10, "concrete": 10, "asphalt": 10, "tar": 8, "gravel": 5, "mud": 2, "unknown": 0}
        if road_quality.lower() in quality_map:
            road_pts += quality_map[road_quality.lower()]
            
        road_pts = min(road_pts, 25)
        total_pts += road_pts
        max_pts += 25
        breakdown["road_accessibility"] = {"score": road_pts, "max": 25, "note": f"Road width={road_width or 'Unavailable'}ft, quality={road_quality or 'Unavailable'}"}
    else:
        breakdown["road_accessibility"] = {"score": None, "max": 25, "note": "Data unavailable"}
        notes.append("Road accessibility data unavailable.")

    # 2. Main road proximity (0–20)
    main_road_pts = None
    dist_main = _safe_float(data.get("distance_to_main_road_km"))
    dist_hwy = _safe_float(data.get("distance_to_highway_km"))
    
    if dist_main is not None or dist_hwy is not None:
        main_road_pts = 0
        if dist_main is not None:
            if dist_main <= 0.5: main_road_pts += 12
            elif dist_main <= 1.0: main_road_pts += 10
            elif dist_main <= 2.0: main_road_pts += 7
            elif dist_main <= 3.0: main_road_pts += 4
            else: main_road_pts += 1
        if dist_hwy is not None:
            if dist_hwy <= 2.0: main_road_pts += 8
            elif dist_hwy <= 5.0: main_road_pts += 5
            elif dist_hwy <= 10.0: main_road_pts += 3
            else: main_road_pts += 1
        main_road_pts = min(main_road_pts, 20)
        total_pts += main_road_pts
        max_pts += 20
        breakdown["main_road_proximity"] = {"score": main_road_pts, "max": 20, "note": f"Main road={dist_main}km, Highway={dist_hwy}km"}
    else:
        breakdown["main_road_proximity"] = {"score": None, "max": 20, "note": "Data unavailable"}

    # 3. Public transport (0–25)
    pt_pts = None
    bus_dist = _safe_float(data.get("nearest_bus_stop_km"))
    rail_dist = _safe_float(data.get("nearest_railway_station_km"))
    
    if bus_dist is not None or rail_dist is not None:
        pt_pts = 0
        if bus_dist is not None:
            if bus_dist <= 0.5: pt_pts += 15
            elif bus_dist <= 1.0: pt_pts += 12
            elif bus_dist <= 2.0: pt_pts += 8
            elif bus_dist <= 3.0: pt_pts += 4
            else: pt_pts += 1
        if rail_dist is not None:
            if rail_dist <= 2.0: pt_pts += 10
            elif rail_dist <= 5.0: pt_pts += 7
            elif rail_dist <= 10.0: pt_pts += 4
            else: pt_pts += 1
        pt_pts = min(pt_pts, 25)
        total_pts += pt_pts
        max_pts += 25
        breakdown["public_transport"] = {"score": pt_pts, "max": 25, "note": f"Bus stop={bus_dist}km, Railway={rail_dist}km"}
    else:
        breakdown["public_transport"] = {"score": None, "max": 25, "note": "Data unavailable"}

    # 4. Connectivity flag (0–15)
    conn_pts = None
    pt_flag = str(data.get("public_transport_available", "")).strip().upper()
    if pt_flag in ["YES", "NO"]:
        conn_pts = 15 if pt_flag == "YES" else 5
        total_pts += conn_pts
        max_pts += 15
        breakdown["connectivity"] = {"score": conn_pts, "max": 15, "note": f"Public transport flag={pt_flag}"}
    else:
        breakdown["connectivity"] = {"score": None, "max": 15, "note": "Data unavailable"}

    # 5. Urban accessibility (0–15)
    ua_pts = None
    region = str(data.get("region_type", "")).strip().lower()
    if region:
        if "urban" in region: ua_pts = 15
        elif "peri" in region or "semi" in region: ua_pts = 10
        elif "rural" in region: ua_pts = 5
        else: ua_pts = 7
        total_pts += ua_pts
        max_pts += 15
        breakdown["urban_accessibility"] = {"score": ua_pts, "max": 15, "note": f"Region type={region}"}
    else:
        breakdown["urban_accessibility"] = {"score": None, "max": 15, "note": "Data unavailable"}

    if max_pts == 0:
        score = None
        notes.append("Location score unavailable because no location attributes were provided.")
    else:
        score = round((total_pts / max_pts * 100), 1)
        if max_pts < 100:
            notes.append(f"Calculated proportionally from available attributes ({max_pts}/100 points evaluated).")
    return {"score": score, "max": 100, "breakdown": breakdown, "notes": notes}


# ─────────────────────────────────────────
# FACILITY SCORE (max 100)
# ─────────────────────────────────────────

def calc_facility_score(facilities: dict) -> dict:
    breakdown = {}
    notes = []

    def nearest_km(ftype):
        f = facilities.get(ftype, {})
        return _safe_float(f.get("nearest_distance_km"))

    def count_3km(ftype):
        f = facilities.get(ftype, {})
        v = f.get("count_within_3km")
        return int(v) if v is not None else 0
        
    total_pts = 0
    max_pts = 0

    # 1. Schools (0–25)
    school_d = nearest_km("school")
    if school_d is not None:
        school_pts = _distance_pts(school_d, [(0.5, 25), (1.0, 20), (2.0, 15), (3.0, 10), (5.0, 5)], default=0)
        breakdown["schools"] = {"score": school_pts, "max": 25, "nearest_km": school_d, "count_3km": count_3km("school"), "rating": _label(school_d)}
        total_pts += school_pts
        max_pts += 25
    else:
        breakdown["schools"] = {"score": None, "max": 25, "rating": "Data unavailable"}

    # 2. Hospitals + clinics (0–25)
    hosp_d = nearest_km("hospital") or nearest_km("clinic")
    if hosp_d is not None:
        hosp_pts = _distance_pts(hosp_d, [(1.0, 25), (2.0, 20), (3.0, 15), (5.0, 8)], default=0)
        breakdown["hospitals"] = {"score": hosp_pts, "max": 25, "nearest_km": hosp_d, "count_3km": count_3km("hospital") + count_3km("clinic"), "rating": _label(hosp_d)}
        total_pts += hosp_pts
        max_pts += 25
    else:
        breakdown["hospitals"] = {"score": None, "max": 25, "rating": "Data unavailable"}

    # 3. Markets / supermarkets (0–20)
    market_d = nearest_km("supermarket") or nearest_km("market")
    if market_d is not None:
        market_pts = _distance_pts(market_d, [(0.5, 20), (1.0, 16), (2.0, 12), (3.0, 7)], default=0)
        breakdown["retail_access"] = {"score": market_pts, "max": 20, "nearest_km": market_d, "count_3km": count_3km("supermarket") + count_3km("market"), "rating": _label(market_d)}
        total_pts += market_pts
        max_pts += 20
    else:
        breakdown["retail_access"] = {"score": None, "max": 20, "rating": "Data unavailable"}

    # 4. Banks (0–15)
    bank_d = nearest_km("bank")
    if bank_d is not None:
        bank_pts = _distance_pts(bank_d, [(0.5, 15), (1.0, 12), (2.0, 8), (3.0, 5)], default=0)
        breakdown["banking"] = {"score": bank_pts, "max": 15, "nearest_km": bank_d, "count_3km": count_3km("bank"), "rating": _label(bank_d)}
        total_pts += bank_pts
        max_pts += 15
    else:
        breakdown["banking"] = {"score": None, "max": 15, "rating": "Data unavailable"}

    # 5. Police (0–15)
    police_d = nearest_km("police")
    if police_d is not None:
        police_pts = _distance_pts(police_d, [(1.0, 15), (2.0, 12), (3.0, 8), (5.0, 5)], default=0)
        breakdown["police"] = {"score": police_pts, "max": 15, "nearest_km": police_d, "rating": _label(police_d)}
        total_pts += police_pts
        max_pts += 15
    else:
        breakdown["police"] = {"score": None, "max": 15, "rating": "Data unavailable"}

    if max_pts == 0:
        notes.append("Nearby facility score unavailable because no facility data could be retrieved.")
        score = None
    else:
        score = round((total_pts / max_pts * 100), 1)
        if max_pts < 100:
            notes.append(f"Calculated proportionally from {max_pts}/100 points of facility data.")
    return {"score": score, "max": 100, "breakdown": breakdown, "notes": notes}


# ─────────────────────────────────────────
# INFRASTRUCTURE SCORE (max 100)
# ─────────────────────────────────────────

def calc_infrastructure_score(data: dict, utility_assessment: dict = None) -> dict:
    """
    Simplified 4-Category Evidence-Based Infrastructure Score (0-100):
      1. Road Connectivity        (0-25)
      2. Water Availability       (0-25)
      3. Electricity Availability (0-25)
      4. Public Transport         (0-25)

    Unknown / unmapped GIS categories are excluded from the denominator so missing
    OpenStreetMap coverage never penalizes a property. Nearby GIS assets never claim
    confirmed household connections or direct legal parcel access.
    """
    breakdown = {}
    notes = []
    total_pts = 0
    max_pts = 0
    contributing = []

    ua_by_key = (utility_assessment or {}).get("categories_by_key") or {}

    # 1. Road Connectivity (0–25)
    rd_ua = ua_by_key.get("road_connectivity") or ua_by_key.get("nearest_road") or {}
    rw = _safe_float(data.get("road_width_ft"))
    rq = str(data.get("road_quality", "")).lower()
    ra = str(data.get("road_access", "")).strip().upper()
    if rd_ua.get("status") == "Available / Mapped" and rd_ua.get("nearest_distance_km") is not None:
        d_nr = rd_ua["nearest_distance_km"]
        rcls = rd_ua.get("nearest_road_class") or "local"
        rd_pts = 20 if d_nr <= 0.25 else (17 if d_nr <= 0.8 else 13)
        if rw is not None and rw >= 30:
            rd_pts = min(25, rd_pts + 3)
        total_pts += rd_pts
        max_pts += 25
        contributing.append("road_connectivity (GIS)")
        breakdown["road_connectivity"] = {
            "score": rd_pts,
            "max": 25,
            "value": f"Nearest Road ({rcls}) {d_nr:.2f} km (Proximity Only)",
            "source": "gis",
        }
    elif rw is not None or rq in {"macadam/asphalt", "asphalt", "concrete", "tar", "gravel", "mud"} or ra in ("YES", "NO"):
        rd_pts = 0
        if ra == "NO":
            rd_pts = 0
        else:
            if rw is not None:
                rd_pts += 15 if rw >= 40 else (12 if rw >= 30 else (8 if rw >= 20 else 5))
            else:
                rd_pts += 10 if ra == "YES" else 6
            rq_map = {"macadam/asphalt": 10, "asphalt": 10, "concrete": 10, "tar": 8, "gravel": 5, "mud": 2}
            rd_pts += rq_map.get(rq, 5 if ra == "YES" else 0)
            rd_pts = min(25, rd_pts)
        total_pts += rd_pts
        max_pts += 25
        contributing.append("road_connectivity (User Reported)")
        breakdown["road_connectivity"] = {
            "score": rd_pts,
            "max": 25,
            "value": f"User Reported (Width={rw or '—'}ft, Quality={rq or '—'}, Access={ra or '—'})",
            "source": "user_reported",
        }
    else:
        breakdown["road_connectivity"] = {
            "score": None,
            "max": 25,
            "value": "Unknown / Not Found in GIS (Excluded)",
            "source": "none",
        }

    # 2. Water Availability (0–25)
    w_ua = ua_by_key.get("water_availability") or ua_by_key.get("water_supply") or {}
    water_user = str(data.get("water_supply", data.get("locality_water_supply", ""))).strip().upper()
    water_src = str(data.get("water_source_type", "")).lower()
    if w_ua.get("status") == "Available / Mapped":
        w_cnt = int(w_ua.get("mapped_count") or 1)
        w_pts = 20  # Capped at 20/25: nearby mapped water infra does not confirm tap connection
        total_pts += w_pts
        max_pts += 25
        contributing.append("water_availability (GIS)")
        breakdown["water_availability"] = {
            "score": w_pts,
            "max": 25,
            "value": f"Water Infra Mapped ({w_cnt} <=3km; Connection Unverified)",
            "source": "gis",
        }
    elif water_user in ("YES", "NO"):
        w_pts = (22 if "piped" in water_src else 18) if water_user == "YES" else 0
        total_pts += w_pts
        max_pts += 25
        contributing.append("water_availability (User Reported)")
        breakdown["water_availability"] = {
            "score": w_pts,
            "max": 25,
            "value": f"User Reported: {water_user}",
            "source": "user_reported",
        }
    else:
        breakdown["water_availability"] = {
            "score": None,
            "max": 25,
            "value": "Unknown / Not Found in GIS (Excluded)",
            "source": "none",
        }

    # 3. Electricity Availability (0–25)
    el_ua = ua_by_key.get("electricity_availability") or ua_by_key.get("electricity") or {}
    elec_user = str(data.get("electricity_available", data.get("electricity_available_locality", ""))).strip().upper()
    if el_ua.get("status") == "Available / Mapped":
        el_cnt = int(el_ua.get("mapped_count") or 1)
        el_pts = 20  # Capped at 20/25: nearby power infra does not confirm active meter
        total_pts += el_pts
        max_pts += 25
        contributing.append("electricity_availability (GIS)")
        breakdown["electricity_availability"] = {
            "score": el_pts,
            "max": 25,
            "value": f"Grid Infra Mapped ({el_cnt} <=3km; Meter Unverified)",
            "source": "gis",
        }
    elif elec_user in ("YES", "NO"):
        el_pts = 20 if elec_user == "YES" else 0
        total_pts += el_pts
        max_pts += 25
        contributing.append("electricity_availability (User Reported)")
        breakdown["electricity_availability"] = {
            "score": el_pts,
            "max": 25,
            "value": f"User Reported: {elec_user}",
            "source": "user_reported",
        }
    else:
        breakdown["electricity_availability"] = {
            "score": None,
            "max": 25,
            "value": "Unknown / Not Found in GIS (Excluded)",
            "source": "none",
        }

    # 4. Public Transport (0–25)
    pt_ua = ua_by_key.get("public_transport") or {}
    pt_user = str(data.get("public_transport_available", "")).strip().upper()
    if pt_ua.get("status") == "Available / Mapped":
        d_pt = pt_ua.get("nearest_distance_km")
        if d_pt is not None:
            pt_pts = 25 if d_pt <= 0.5 else (20 if d_pt <= 1.5 else (15 if d_pt <= 3.0 else 10))
        else:
            pt_pts = 15
        total_pts += pt_pts
        max_pts += 25
        contributing.append("public_transport (GIS)")
        breakdown["public_transport"] = {
            "score": pt_pts,
            "max": 25,
            "value": f"GIS Transit Stop ({d_pt:.2f} km)" if d_pt is not None else "GIS Transit Stop Mapped",
            "source": "gis",
        }
    elif pt_user in ("YES", "NO"):
        pt_pts = 20 if pt_user == "YES" else 0
        total_pts += pt_pts
        max_pts += 25
        contributing.append("public_transport (User Reported)")
        breakdown["public_transport"] = {
            "score": pt_pts,
            "max": 25,
            "value": f"User Reported: {pt_user}",
            "source": "user_reported",
        }
    else:
        breakdown["public_transport"] = {
            "score": None,
            "max": 25,
            "value": "Unknown / Not Found in GIS (Excluded)",
            "source": "none",
        }

    coverage_pct = round((max_pts / 100.0) * 100.0, 1)
    if max_pts == 0:
        score = None
        notes.append("Infrastructure score unavailable — no GIS or reported evidence evaluated.")
    else:
        score = round((total_pts / max_pts * 100), 1)
        notes.append(
            f"4-Factor Infrastructure Coverage: {coverage_pct}% ({max_pts}/100 weights from {', '.join(contributing)}). "
            "Unknown or unmapped categories excluded from denominator."
        )
    return {
        "score": score,
        "max": 100,
        "coverage_pct": coverage_pct,
        "contributing_categories": contributing,
        "breakdown": breakdown,
        "notes": notes,
    }


# ─────────────────────────────────────────
# UTILITY SCORE (max 100)
# ─────────────────────────────────────────

def calc_utility_score(data: dict, utility_assessment: dict = None) -> dict:
    """
    Evidence-based utility readiness indicator (0-100):
    - Only uses evidence-supported near-property utility infra or explicit optional user input.
    - Nearby lakes/waterbodies are NEVER equated to piped/potable water supply.
    - Nearby electrical grids indicate area infrastructure only (capped conservatively below 100%
      because active household meter connections remain unverified without official utility proof).
    - Categories classified as Not Found (due to sparse OSM) or Unknown are excluded from the
      denominator so missing data never falsely penalizes properties.
    """
    breakdown = {}
    notes = []
    total_pts = 0
    max_pts = 0
    contributing = []

    ua_by_key = (utility_assessment or {}).get("categories_by_key") or {}

    # 1. Electricity (0–50) — check substations/transformers + distribution lines
    el_sub_ua = ua_by_key.get("substations_transformers") or {}
    el_dist_ua = ua_by_key.get("power_distribution") or {}
    el_ua = ua_by_key.get("electricity") or {}
    el_mapped = any(x.get("status") == "Available / Mapped" for x in (el_ua, el_sub_ua, el_dist_ua))
    el_total_cnt = (
        int(el_ua.get("mapped_count") or 0)
        + int(el_sub_ua.get("mapped_count") or 0)
        + int(el_dist_ua.get("mapped_count") or 0)
    )
    elec = str(data.get("electricity_available", data.get("electricity_available_locality", ""))).upper()
    if el_mapped:
        # Conservative cap (40/50) — power lines/substations mapped nearby, active meter unverified
        elec_pts = 40
        total_pts += elec_pts
        max_pts += 50
        contributing.append("electricity (GIS Nearby Infra)")
        breakdown["electricity"] = {
            "score": elec_pts,
            "max": 50,
            "value": f"Grid Infra Nearby ({el_total_cnt} ≤3km; Meter Unverified)",
            "source": "gis",
        }
    elif utility_assessment is None and elec in ["YES", "NO"]:
        elec_pts = 50 if elec == "YES" else 0
        total_pts += elec_pts
        max_pts += 50
        contributing.append("electricity")
        breakdown["electricity"] = {"score": elec_pts, "max": 50, "value": "Available" if elec == "YES" else "Not Available", "source": "user_reported"}
    elif elec in ["YES", "NO"]:
        elec_pts = 35 if elec == "YES" else 0
        total_pts += elec_pts
        max_pts += 50
        contributing.append("electricity (User Reported)")
        breakdown["electricity"] = {
            "score": elec_pts,
            "max": 50,
            "value": f"User Reported: {elec} (Unverified)",
            "source": "user_reported",
        }
    else:
        breakdown["electricity"] = {
            "score": None,
            "max": 50,
            "value": "Unknown / Unverified (Excluded from Denominator)",
            "source": "none",
        }

    # 2. Water Supply (0–50) — strictly piped/water-works/tanks/taps/wells, NEVER lakes/canals
    w_keys = ("water_supply", "piped_water_supply", "water_tanks", "public_water_taps", "borewells")
    w_entries = [ua_by_key.get(k) or {} for k in w_keys]
    w_mapped = any(x.get("status") == "Available / Mapped" for x in w_entries)
    w_total_cnt = sum(int(x.get("mapped_count") or 0) for x in w_entries)
    water = str(data.get("water_supply", data.get("locality_water_supply", ""))).upper()
    water_src = str(data.get("water_source_type", "")).lower()
    if w_mapped:
        water_pts = 40  # Nearby potable/supply infra mapped; household connection unverified
        total_pts += water_pts
        max_pts += 50
        contributing.append("water_supply (GIS Utility Infra)")
        breakdown["water_supply"] = {
            "score": water_pts,
            "max": 50,
            "value": f"Water Supply Infra Mapped ({w_total_cnt} ≤3km; Tap Unverified)",
            "source": "gis",
        }
    elif utility_assessment is None and water in ["YES", "NO"]:
        water_pts = 0
        if water == "YES":
            water_pts = 50 if "piped" in water_src else 40
        total_pts += water_pts
        max_pts += 50
        contributing.append("water_supply")
        breakdown["water_supply"] = {"score": water_pts, "max": 50, "value": f"Available ({water_src})" if water == "YES" else "Not Available", "source": "user_reported"}
    elif water in ["YES", "NO"]:
        water_pts = (35 if "piped" in water_src else 30) if water == "YES" else 0
        total_pts += water_pts
        max_pts += 50
        contributing.append("water_supply (User Reported)")
        breakdown["water_supply"] = {
            "score": water_pts,
            "max": 50,
            "value": f"User Reported: {water}{f' ({water_src})' if water_src and water_src != 'unknown' else ''} (Unverified)",
            "source": "user_reported",
        }
    else:
        breakdown["water_supply"] = {
            "score": None,
            "max": 50,
            "value": "Unknown / Unverified (Excluded from Denominator)",
            "source": "none",
        }

    coverage_pct = round((max_pts / 100.0) * 100.0, 1)
    if max_pts == 0:
        score = None
        notes.append(
            "Utility score marked Unknown (N/A) — no GIS utility evidence or verified utility input available; excluded from overall weighting without penalty."
        )
    else:
        score = round((total_pts / max_pts * 100), 1)
        notes.append(
            f"Evaluated coverage: {coverage_pct}% ({max_pts}/100 weights from {', '.join(contributing)}). "
            "Surface waterbodies are NOT counted as piped water supply; unverified categories excluded."
        )
    return {
        "score": score,
        "max": 100,
        "coverage_pct": coverage_pct,
        "contributing_categories": contributing,
        "breakdown": breakdown,
        "notes": notes,
    }


# ─────────────────────────────────────────
# ENVIRONMENT SCORE (max 100)
# ─────────────────────────────────────────

def calc_environment_score(data: dict, gis_data: dict = None) -> dict:
    """
    Transparent environmental indicator (0-100):
      - waterbody_proximity (0-35): OSM surface waterbody straight-line distance
      - waterbody_density   (0-20): OSM waterbodies within 3 km
      - green_space_access  (0-20): OSM parks/green spaces proximity
      - official_flood_clearance (0-25): Authoritative gov flood/drainage record (None unless provided)

    Safeguards:
      - Unknown / unmapped waterbody distance is NEVER treated as safe (returns score=None).
      - Without official government flood/drainage verification, OSM-only indicators
        cannot score 100/100 (capped at <=75.0 / 100 matching actual OSM evidence weight).
    """
    breakdown = {}
    notes = []
    total_pts = 0
    max_pts = 0

    waterbody_dist = _safe_float(gis_data.get("distance_to_waterbody_km")) if gis_data else None
    waterbody_count = gis_data.get("waterbody_count_3km") if gis_data else None
    park_dist = _safe_float(gis_data.get("distance_to_park_km")) if gis_data else None
    official_flood_ok = data.get("official_flood_clearance_verified")

    if waterbody_dist is None:
        waterbody_dist = _safe_float(data.get("distance_to_nearest_waterbody_km"))
    if waterbody_count is None:
        waterbody_count = _safe_int(data.get("waterbody_count_3km"))
    if park_dist is None:
        park_dist = _safe_float(data.get("nearest_park_km"))

    # 1. Surface waterbody proximity (0-35) — OSM-derived only
    if waterbody_dist is not None:
        if waterbody_dist < 0.2:
            wb_pts = 5
            notes.append("WARNING: Very close to mapped water body (<0.2km). Elevated flood exposure risk; official verification required.")
        elif waterbody_dist < 0.5:
            wb_pts = 12
            notes.append("Close to mapped water body (<0.5km). Official flood-buffer check required.")
        elif waterbody_dist < 1.0:
            wb_pts = 22
        elif waterbody_dist < 2.0:
            wb_pts = 28
        else:
            wb_pts = 35
        total_pts += wb_pts
        max_pts += 35
        breakdown["waterbody_proximity"] = {"score": wb_pts, "max": 35, "value": f"{waterbody_dist:.2f}km (OSM)"}
    else:
        breakdown["waterbody_proximity"] = {"score": None, "max": 35, "value": "Insufficient evidence"}
        notes.append("OSM waterbody distance unavailable — unknown is not treated as safe.")

    # 2. Waterbody density within 3km (0-20) — only when proximity or positive count observed
    if waterbody_count is not None and (waterbody_dist is not None or waterbody_count > 0):
        if waterbody_count == 0:
            wc_pts = 20
        elif waterbody_count <= 2:
            wc_pts = 14
        elif waterbody_count <= 5:
            wc_pts = 8
        else:
            wc_pts = 4
            notes.append("Multiple mapped water bodies within 3km; drainage verification advised.")
        total_pts += wc_pts
        max_pts += 20
        breakdown["waterbody_density"] = {"score": wc_pts, "max": 20, "value": f"{waterbody_count} within 3km (OSM)"}
    else:
        breakdown["waterbody_density"] = {"score": None, "max": 20, "value": "Insufficient evidence"}

    # 3. Parks / Green space access (0-20) — OSM-derived
    if park_dist is not None:
        if park_dist <= 0.5:
            pk_pts = 20
        elif park_dist <= 1.5:
            pk_pts = 15
        elif park_dist <= 3.0:
            pk_pts = 10
        else:
            pk_pts = 5
        total_pts += pk_pts
        max_pts += 20
        breakdown["green_space_access"] = {"score": pk_pts, "max": 20, "value": f"{park_dist:.2f}km (OSM)"}
    else:
        breakdown["green_space_access"] = {"score": None, "max": 20, "value": "Data unavailable"}

    # 4. Official government flood/drainage verification (0-25)
    official_verified = False
    if str(official_flood_ok or "").strip().upper() in ("YES", "TRUE", "1"):
        official_verified = True
        total_pts += 25
        max_pts += 25
        breakdown["official_flood_clearance"] = {"score": 25, "max": 25, "value": "Verified"}
    else:
        breakdown["official_flood_clearance"] = {"score": None, "max": 25, "value": "Official check required"}

    coverage_pct = round((max_pts / 100.0) * 100.0, 1)

    if waterbody_dist is None and not official_verified:
        # Unknown/unmapped waterbody telemetry without official clearance -> insufficient evidence -> N/A
        score = None
        notes.append(
            "Environmental safety marked N/A (insufficient evidence): no verified waterbody distance or official flood-zone clearance; excluded from overall denominator."
        )
        source_label = "OpenStreetMap (insufficient coverage) | No official government flood record"
    elif not official_verified:
        # OSM-only proxy cannot score 100/100 without official flood/drainage records.
        # Scale proportionally within the 75-pt OSM ceiling so 100/100 requires verified official data.
        osm_ratio = (total_pts / max_pts) if max_pts > 0 else 0.0
        score = round(osm_ratio * 75.0, 1)
        notes.append(
            f"Preliminary OSM indicator only ({coverage_pct:.0f}% environmental coverage; capped at 75/100 because official MUDA / Minor Irrigation flood & drainage records are unverified)."
        )
        source_label = "OpenStreetMap (preliminary proxy only — not official flood-zone certification)"
    else:
        score = round((total_pts / max_pts * 100.0), 1) if max_pts > 0 else None
        source_label = "OpenStreetMap + Verified Official Records"

    return {
        "score": score,
        "max": 100,
        "coverage_pct": coverage_pct,
        "source": source_label,
        "breakdown": breakdown,
        "notes": notes,
        "disclaimer": "OSM waterbody proximity is a preliminary indicator only and cannot establish flood safety. Official Karnataka Minor Irrigation / MUDA flood maps required.",
    }


# ─────────────────────────────────────────
# PRICE SCORE (max 100)
# ─────────────────────────────────────────

def calc_price_score(predicted_price_per_sqft: float, dataset_p25: float, dataset_p75: float, dataset_median: float) -> dict:
    if predicted_price_per_sqft is None or predicted_price_per_sqft <= 0:
        return {"score": None, "max": 100, "breakdown": {}, "notes": ["Price score unavailable."]}

    p = predicted_price_per_sqft
    if p <= dataset_p25:
        score = 90 + min(10, 10 * (dataset_p25 - p) / max(dataset_p25, 1))
    elif p <= dataset_median:
        score = 70 + 20 * (dataset_median - p) / max(dataset_median - dataset_p25, 1)
    elif p <= dataset_p75:
        score = 50 + 20 * (dataset_p75 - p) / max(dataset_p75 - dataset_median, 1)
    elif p <= dataset_p75 * 1.5:
        score = 30 + 20 * (dataset_p75 * 1.5 - p) / max(dataset_p75 * 0.5, 1)
    else:
        score = max(10, 30 - 20 * (p - dataset_p75 * 1.5) / max(dataset_p75, 1))

    return {
        "score": round(min(100, max(0, score)), 1),
        "max": 100,
        "breakdown": {"predicted": p, "dataset_p25": dataset_p25, "dataset_median": dataset_median, "dataset_p75": dataset_p75},
        "notes": [],
        "benchmark": "Mysuru dataset price distribution"
    }


# ─────────────────────────────────────────
# OVERALL SCORE
# ─────────────────────────────────────────

def calc_overall_score(price_score, location_score, facility_score, environment_score, infrastructure_score, utility_score, weights_dict) -> dict:
    raw_components = {
        "price": float(price_score) if price_score is not None else None,
        "location": float(location_score) if location_score is not None else None,
        "facility": float(facility_score) if facility_score is not None else None,
        "environment": float(environment_score) if environment_score is not None else None,
        "infrastructure": float(infrastructure_score) if infrastructure_score is not None else None,
        "utility": float(utility_score) if utility_score is not None else None,
    }
    available = {
        k: v for k, v in raw_components.items()
        if v is not None and weights_dict.get(k, 0) > 0
    }

    if not available:
        return {"score": None, "components": raw_components, "weights": weights_dict, "notes": ["No scores available."]}

    total_weight = sum(weights_dict[k] for k in available)
    weighted_sum = sum(weights_dict[k] * available[k] for k in available)
    overall = round(weighted_sum / total_weight, 1) if total_weight > 0 else None

    display_components = {k: (round(v, 1) if v is not None else None) for k, v in raw_components.items()}
    missing = [k for k in raw_components if k not in available]
    notes = []
    if missing:
        notes.append(f"Components not scored (excluded from average): {', '.join(missing)}")

    return {
        "score": overall,
        "components": display_components,
        "weights": weights_dict,
        "available_weight": round(total_weight * (100 if total_weight <= 1.0 else 1), 1),
        "formula": "Overall = Σ(weight × component_score) / Σ(available_weights)",
        "notes": notes,
    }


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _safe_float(val):
    try:
        f = float(val)
        return f if not (f != f) else None
    except (TypeError, ValueError):
        return None

def _safe_int(val):
    try: return int(val)
    except (TypeError, ValueError): return None

def _distance_pts(dist_km, thresholds: list, default: int = 0) -> int:
    if dist_km is None: return default
    for max_km, pts in thresholds:
        if dist_km <= max_km: return pts
    return default

def _label(dist_km) -> str:
    if dist_km is None: return "Data unavailable"
    if dist_km <= 0.5: return "Excellent"
    elif dist_km <= 1.0: return "Very Good"
    elif dist_km <= 2.0: return "Good"
    elif dist_km <= 3.0: return "Moderate"
    elif dist_km <= 5.0: return "Fair"
    else: return "Poor"
