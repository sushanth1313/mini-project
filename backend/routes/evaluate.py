"""
Evaluate route: full property evaluation pipeline.
POST /api/evaluate — runs ML, GIS, scoring, saves to DB.
POST /api/predict-price — price-only prediction (no DB save).
"""
import gc
import json
import math
import logging
import os
import threading
import time
from flask import Blueprint, request, jsonify, current_app
from models import (
    db, Property, PropertyEvaluation, PricePrediction,
    GISAnalysis, FacilityRecord, DatasetRecord
)
from ml.preprocess import prepare_single_input
from ml.predict import predict_price_per_sqft, get_model_metrics
from gis.service import (
    get_nearby_facilities, geocode_locality,
    reverse_geocode_coords, resolve_entered_vs_coordinates, search_locations,
)
from services.scoring import (
    calc_location_score, calc_facility_score, calc_infrastructure_score,
    calc_utility_score, calc_environment_score, calc_price_score, calc_overall_score
)

log = logging.getLogger(__name__)
evaluate_bp = Blueprint("evaluate", __name__, url_prefix="/api")

# Serialize memory-intensive ML/GIS evaluation runs within a single Gunicorn worker
# so concurrent requests do not spike RSS above Render Free Tier's 512 MB limit.
_EVAL_LOCK = threading.Lock()


def _get_rss_mb() -> tuple[float, float]:
    """Return (current_rss_mb, peak_rss_mb) using OS-native APIs without secrets."""
    cur_mb, peak_mb = 0.0, 0.0
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        cur_mb = round(int(line.split()[1]) / 1024.0, 1)
                    elif line.startswith("VmHWM:"):
                        peak_mb = round(int(line.split()[1]) / 1024.0, 1)
        else:
            import psutil
            mi = psutil.Process(os.getpid()).memory_info()
            cur_mb = round(mi.rss / 1048576.0, 1)
            peak_mb = round(getattr(mi, "peak_wset", mi.rss) / 1048576.0, 1)
    except Exception:
        try:
            import resource
            peak_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
            cur_mb = peak_mb
        except Exception:
            pass
    return cur_mb, peak_mb


@evaluate_bp.route("/predict-price", methods=["POST"])
def predict_price():
    """
    Quick price prediction without saving to DB.
    Accepts property feature dict, returns prediction + model info.
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Validate area
    try:
        area = float(data.get("land_area_sqft", 0))
        if area <= 0:
            return jsonify({"error": "land_area_sqft must be a positive number"}), 422
    except (ValueError, TypeError):
        return jsonify({"error": "land_area_sqft must be a valid number"}), 422

    try:
        input_df = prepare_single_input(data)
        explain_flag = bool(data.get("explain", False))
        result = predict_price_per_sqft(input_df, explain=explain_flag)

        psf = result["predicted_price_per_sqft"]
        result["predicted_total_price"] = round(psf * area, 2)
        result["price_range_low_total"] = round(result["range_low_per_sqft"] * area, 2)
        result["price_range_high_total"] = round(result["range_high_per_sqft"] * area, 2)
        return jsonify({"prediction": result})
    except FileNotFoundError as e:
        return jsonify({
            "error": "ML model not trained yet",
            "detail": str(e),
            "action": "Run: python backend/ml/train.py --dataset <path>"
        }), 503
    except Exception as e:
        log.error(f"Prediction error: {e}", exc_info=True)
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500


@evaluate_bp.route("/reverse-geocode", methods=["POST", "GET"])
@evaluate_bp.route("/gis/reverse-geocode", methods=["POST", "GET"])
def reverse_geocode_endpoint():
    """
    Reverse-geocode (lat, lon) into Mysuru district locality, taluk, district, state
    plus rule-based region classification. Validates Mysuru District polygon.
    """
    from gis.geo_utils import is_in_mysuru_district, classify_region_type

    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        raw_lat = body.get("latitude", body.get("lat"))
        raw_lon = body.get("longitude", body.get("lon"))
        land_type = body.get("land_type")
    else:
        raw_lat = request.args.get("latitude", request.args.get("lat"))
        raw_lon = request.args.get("longitude", request.args.get("lon"))
        land_type = request.args.get("land_type")

    lat_val = _safe_float(raw_lat)
    lon_val = _safe_float(raw_lon)
    if lat_val is None or lon_val is None or not (math.isfinite(lat_val) and math.isfinite(lon_val)):
        return jsonify({"error": "Valid latitude and longitude are required"}), 422

    if not is_in_mysuru_district(lat_val, lon_val):
        return jsonify({
            "error": (
                f"Coordinates ({lat_val}, {lon_val}) fall outside the Mysuru District boundary polygon. "
                "Mysuru latitude must be positive (Northern Hemisphere)."
            ),
            "status": "OUTSIDE_DISTRICT",
        }), 422

    rev = reverse_geocode_coords(lat_val, lon_val)
    if rev["status"] == "UNAVAILABLE":
        return jsonify(rev), 503

    if rev.get("taluk") or rev.get("locality"):
        rt, rt_note = classify_region_type(
            taluk=rev.get("taluk"),
            village_or_locality=rev.get("locality"),
            land_type=land_type,
            lat=lat_val,
            lon=lon_val,
            explicit_region_type="Auto",
        )
        rev["region_type"] = rt
        rev["region_classification_note"] = rt_note

    return jsonify(rev), 200


@evaluate_bp.route("/gis/config", methods=["GET"])
def gis_runtime_config():
    """Return non-secret GIS provider capability flags, free providers & live KGIS coverage counts."""
    from gis.adapters.google import get_google_maps_status
    from gis.kgis_boundaries import get_kgis_coverage_summary
    gstat = get_google_maps_status()
    return jsonify({
        "google_geocoding_enabled": gstat["enabled"],
        "google_places_enabled": gstat["enabled"],
        "google_maps_status": gstat,
        "free_providers": [
            "Karnataka GIS (KGIS / KSRSAC Official Polygons)",
            "OpenStreetMap Overpass API",
            "Photon (Komoot OSM)",
            "Nominatim (OpenStreetMap)",
            "ArcGIS World Geocoder (Validated Secondary POI)",
        ],
        "kgis_boundaries_enabled": True,
        "primary_boundary_authority": "Karnataka GIS (KGIS / KSRSAC)",
        "kgis_coverage": get_kgis_coverage_summary(),
    }), 200


@evaluate_bp.route("/gis/search", methods=["GET", "POST"])
def gis_location_search():
    """
    Autocomplete location search constrained strictly to Mysuru District polygon.
    Supports GET ?q=...&limit=8 or POST {"query": ..., "limit": 8}.
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        query = body.get("q") or body.get("query") or ""
        limit = body.get("limit", 8)
    else:
        query = request.args.get("q") or request.args.get("query") or ""
        limit = request.args.get("limit", 8)

    try:
        limit_i = int(limit)
    except (ValueError, TypeError):
        limit_i = 8

    res = search_locations(str(query), limit=limit_i)
    status_code = 503 if res.get("status") == "SOURCE_UNAVAILABLE" else 200
    return jsonify(res), status_code


@evaluate_bp.route("/evaluate", methods=["POST"])
def run_evaluation():
    """Serialize heavy evaluation work under _EVAL_LOCK and log safe stage RSS/timings."""
    t_wait = time.perf_counter()
    acquired = _EVAL_LOCK.acquire(timeout=120)
    if not acquired:
        return jsonify({
            "error": "Another property evaluation is currently in progress. Please retry in a few seconds."
        }), 503
    cur0, peak0 = _get_rss_mb()
    log.info(f"[EVAL] acquired lock wait={time.perf_counter()-t_wait:.2f}s rss={cur0}MB peak={peak0}MB")
    try:
        resp = _run_evaluation_pipeline()
        cur1, peak1 = _get_rss_mb()
        log.info(f"[EVAL] completed elapsed={time.perf_counter()-t_wait:.2f}s rss={cur1}MB peak={max(peak0, peak1)}MB")
        return resp
    except Exception:
        db.session.rollback()
        raise
    finally:
        gc.collect()
        _EVAL_LOCK.release()


def _run_evaluation_pipeline():
    """
    Full evaluation pipeline:
    1. Validate + save property
    2. Run ML price prediction
    3. Geocode if needed
    4. Run GIS/Overpass for facilities
    5. Calculate all scores
    6. Save to DB
    7. Return full evaluation
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    raw_lat = data.get("latitude")
    raw_lon = data.get("longitude")
    has_lat = raw_lat not in (None, "")
    has_lon = raw_lon not in (None, "")

    # Require land_area_sqft always; require either (village_or_locality + taluk) OR valid (lat + lon)
    if not data.get("land_area_sqft"):
        return jsonify({"error": "Missing required field: land_area_sqft"}), 422
    if not (has_lat and has_lon) and (not data.get("taluk") or not data.get("village_or_locality")):
        return jsonify({"error": "Provide taluk & village_or_locality, or valid latitude & longitude coordinates"}), 422

    try:
        area = float(data["land_area_sqft"])
        if not math.isfinite(area) or area <= 0 or area > 50_000_000:
            return jsonify({"error": "land_area_sqft must be a finite positive number (1 to 50,000,000)"}), 422
    except (ValueError, TypeError):
        return jsonify({"error": "land_area_sqft must be a valid number"}), 422

    asking_val = _safe_float(data.get("asking_price_inr"))
    if data.get("asking_price_inr") not in (None, "") and (asking_val is None or not math.isfinite(asking_val) or asking_val < 0):
        return jsonify({"error": "asking_price_inr must be a valid non-negative number"}), 422

    from gis.geo_utils import (
        is_in_mysuru_district, normalize_taluk,
        classify_region_type, normalize_coordinate_status,
    )

    if has_lat != has_lon:
        return jsonify({"error": "Both latitude and longitude must be provided together, or leave both blank for geocoding"}), 422
    lat_chk, lon_chk = None, None
    if has_lat and has_lon:
        lat_chk = _safe_float(raw_lat)
        lon_chk = _safe_float(raw_lon)
        if lat_chk is None or lon_chk is None or not math.isfinite(lat_chk) or not math.isfinite(lon_chk):
            return jsonify({"error": "latitude and longitude must be valid numbers"}), 422
        if not is_in_mysuru_district(lat_chk, lon_chk):
            return jsonify({
                "error": (
                    f"Coordinates ({lat_chk}, {lon_chk}) fall outside the Mysuru District boundary polygon. "
                    "Mysuru latitude must be positive (Northern Hemisphere)."
                )
            }), 422

    entered_taluk_raw = data.get("taluk")
    entered_loc_raw = (data.get("village_or_locality") or "").strip()
    entered_taluk_canon = normalize_taluk(entered_taluk_raw) if entered_taluk_raw else "Mysuru"
    warnings = []
    location_audit = None

    # Resolve coordinates <-> locality bidirectionally
    coord_source = data.get("coordinate_source")
    if lat_chk is not None and lon_chk is not None:
        lat, lon = lat_chk, lon_chk
        # Honest default: manually typed coordinates without explicit precision are USER_ENTERED, never SURVEYED/EXACT
        coord_status = normalize_coordinate_status(data.get("coordinate_status"), default="USER_ENTERED")
        location_audit = resolve_entered_vs_coordinates(lat, lon, entered_loc_raw, entered_taluk_canon)
        canon_locality = location_audit.get("canonical_locality") or entered_loc_raw or "Locality could not be confidently resolved"
        canon_taluk = location_audit.get("canonical_taluk") or entered_taluk_canon
        canon_district = location_audit.get("resolved_district") or data.get("district", "Mysuru")
        if location_audit.get("warning"):
            warnings.append(location_audit["warning"])
        if not coord_source:
            prov = location_audit.get("reverse_provider") or "Karnataka GIS (KGIS)"
            coord_source = f"User Coordinates + {prov}"
    else:
        lat, lon = None, None
        coord_status = "LOCALITY_CENTROID"
        canon_locality = entered_loc_raw
        canon_taluk = entered_taluk_canon
        canon_district = data.get("district", "Mysuru")
        geo = geocode_locality(canon_locality, canon_taluk, canon_district)
        if geo:
            from gis.kgis_boundaries import lookup_kgis_location
            lat, lon = geo["lat"], geo["lon"]
            coord_status = geo["coordinate_status"]
            coord_source = geo["coordinate_source"]
            kgis_fwd = lookup_kgis_location(float(lat), float(lon))
            location_audit = {
                "entered_locality": entered_loc_raw,
                "entered_taluk": entered_taluk_canon,
                "resolved_locality": canon_locality,
                "resolved_taluk": kgis_fwd.get("kgis_taluk") or canon_taluk,
                "resolved_district": canon_district,
                "resolved_state": "Karnataka",
                "revenue_village": kgis_fwd.get("revenue_village_display") or kgis_fwd.get("revenue_village") or canon_locality,
                "urban_locality": kgis_fwd.get("urban_locality"),
                "ward_number": kgis_fwd.get("ward_number"),
                "ward_name": kgis_fwd.get("ward_name"),
                "hobli": kgis_fwd.get("hobli"),
                "gram_panchayat_lgd_code": kgis_fwd.get("lgd_gp_code"),
                "municipal_body": kgis_fwd.get("local_body"),
                "likely_planning_authority": kgis_fwd.get("likely_planning_authority"),
                "boundary_source": kgis_fwd.get("source"),
                "point_in_polygon": bool(kgis_fwd.get("point_in_polygon")),
                "reverse_display_name": geo.get("display_name"),
                "reverse_provider": geo.get("coordinate_source"),
                "resolution_status": "FORWARD_GEOCODED",
                "mismatch_detected": False,
            }
            warnings.append(
                f"Coordinates geocoded to locality centroid ({lat:.4f}, {lon:.4f}). "
                "Not an exact property location."
            )
        else:
            location_audit = {
                "entered_locality": entered_loc_raw,
                "entered_taluk": entered_taluk_canon,
                "canonical_locality": canon_locality,
                "canonical_taluk": canon_taluk,
                "resolution_status": "FORWARD_GEOCODE_UNAVAILABLE",
                "mismatch_detected": False,
            }
            warnings.append(
                "Could not geocode location within Mysuru District. GIS analysis unavailable; "
                "provide latitude/longitude for full spatial analysis."
            )

    # When location mismatch corrected taluk/locality from coords, re-evaluate Auto region (and warn if user region conflicts)
    explicit_reg = data.get("region_type")
    if location_audit and location_audit.get("resolution_status") == "CORRECTED_FROM_COORDS":
        resolved_region, region_note = classify_region_type(
            taluk=canon_taluk,
            village_or_locality=canon_locality,
            land_type=data.get("land_type"),
            lat=lat,
            lon=lon,
            explicit_region_type="Auto",
        )
        if explicit_reg and str(explicit_reg).strip().lower() not in ("", "auto", "unknown", resolved_region.lower()):
            region_note += f" (Re-classified from '{explicit_reg}' based on coordinate-resolved location.)"
    else:
        resolved_region, region_note = classify_region_type(
            taluk=canon_taluk,
            village_or_locality=canon_locality,
            land_type=data.get("land_type"),
            lat=lat,
            lon=lon,
            explicit_region_type=explicit_reg,
        )

    # Allow linking to an existing property
    prop_id = data.get("property_id")
    if prop_id:
        prop = Property.query.get(prop_id)
        if not prop:
            return jsonify({"error": f"Property {prop_id} not found"}), 404
        if lat and lon and not prop.latitude:
            prop.latitude = lat
            prop.longitude = lon
            prop.coordinate_status = coord_status
            prop.coordinate_source = coord_source
        if not prop.region_type or prop.region_type.lower() in ("auto", "unknown"):
            prop.region_type = resolved_region
    else:
        auth_uid = None
        try:
            auth_hdr = request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                from modules.admin_portal.auth_users import verify_portal_bearer_token
                ok, _role, _msg, claims = verify_portal_bearer_token(auth_hdr.split(" ", 1)[1].strip())
                if ok and claims and claims.get("token_type") == "user" and claims.get("user_id"):
                    auth_uid = int(claims["user_id"])
        except Exception:
            auth_uid = None

        # Property label (prop.name) remains strictly unchanged; canonical locality/taluk resolved above
        prop = Property(
            user_id=auth_uid,
            name=data.get("name"),
            district=canon_district,
            taluk=canon_taluk,
            village_or_locality=canon_locality,
            entered_locality=entered_loc_raw or None,
            entered_taluk=entered_taluk_canon if entered_taluk_raw else None,
            region_type=resolved_region,
            land_type=data.get("land_type"),
            listing_type=data.get("listing_type"),
            land_area_sqft=area,
            asking_price_inr=_safe_float(data.get("asking_price_inr")),
            latitude=lat,
            longitude=lon,
            coordinate_status=coord_status,
            coordinate_source=coord_source,
            road_width_ft=_safe_float(data.get("road_width_ft")),
            road_quality=data.get("road_quality"),
            road_access=data.get("road_access"),
            street_light_available=data.get("street_light_available"),
            public_transport_available=data.get("public_transport_available"),
            electricity_available=data.get("electricity_available"),
            water_supply=data.get("water_supply"),
            water_source_type=data.get("water_source_type"),
        )
        db.session.add(prop)
        db.session.commit()

        # Default verification items
        from documents.extractor import DEFAULT_VERIFICATION_ITEMS
        from models import VerificationItem
        for item_def in DEFAULT_VERIFICATION_ITEMS:
            db.session.add(VerificationItem(
                property_id=prop.id,
                item_key=item_def["key"],
                item_label=item_def["label"],
                status="NEEDS_VERIFICATION",
            ))

    evaluation = PropertyEvaluation(property_id=prop.id)
    db.session.add(evaluation)
    db.session.commit()

    gis_data_dict = {}

    # Unified input dict ensuring ML, reliability, scoring, DB and PDF share one source of truth
    unified_data = dict(data)
    unified_data["taluk"] = prop.taluk
    unified_data["village_or_locality"] = prop.village_or_locality
    unified_data["region_type"] = prop.region_type
    if prop.latitude is not None and prop.longitude is not None:
        unified_data["latitude"] = prop.latitude
        unified_data["longitude"] = prop.longitude

    lat = prop.latitude
    lon = prop.longitude

    # ── Step 1: GIS Facility Analysis (runs before ML & Scoring) ──────────
    facilities_raw = {}
    if lat and lon:
        try:
            overpass_url = current_app.config.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
            overpass_timeout = min(int(current_app.config.get("OVERPASS_TIMEOUT", 12) or 12), 15)
            facilities_raw = get_nearby_facilities(
                lat, lon,
                overpass_url,
                overpass_timeout,
                locality=prop.village_or_locality or "",
                district=prop.district or ""
            )

            statuses = [v.get("status") for v in facilities_raw.values()]
            any_data = any(v.get("nearest") is not None for v in facilities_raw.values())
            any_error = any(s in ("SOURCE_UNAVAILABLE", "PARTIAL") for s in statuses)
            if not any_data and all(s == "SOURCE_UNAVAILABLE" for s in statuses):
                warnings.append(
                    "GIS analysis (OpenStreetMap) is temporarily unavailable across all categories. "
                    "Price evaluation is still available."
                )
            elif any_error:
                failed_cats = [k for k, v in facilities_raw.items() if v.get("status") in ("SOURCE_UNAVAILABLE", "PARTIAL")]
                warnings.append(
                    f"GIS query partially completed; incomplete/unavailable categories: {', '.join(failed_cats)}."
                )
        except Exception as e:
            log.error(f"GIS error: {e}", exc_info=True)
            warnings.append(
                "GIS analysis is temporarily unavailable. "
                f"Price evaluation is still available. Error: {str(e)[:80]}"
            )

        wb_data = facilities_raw.get("waterbody", {})
        wb_dist = wb_data.get("nearest_distance_km")
        wb_count = wb_data.get("count_within_3km") if wb_data.get("status") not in ("SOURCE_UNAVAILABLE", "PARTIAL") else None

        statuses = [v.get("status") for v in facilities_raw.values()] if facilities_raw else []
        if not facilities_raw or all(s == "SOURCE_UNAVAILABLE" for s in statuses):
            gis_status_str = "UNAVAILABLE"
        elif any(s in ("SOURCE_UNAVAILABLE", "PARTIAL") for s in statuses):
            gis_status_str = "PARTIAL"
        else:
            gis_status_str = "GIS_DERIVED"

        gis_rec = GISAnalysis(
            evaluation_id=evaluation.id,
            latitude=lat,
            longitude=lon,
            coordinate_status=prop.coordinate_status or "LOCALITY_CENTROID",
            source="OpenStreetMap",
            status=gis_status_str,
            distance_to_waterbody_km=wb_dist,
            waterbody_count_3km=wb_count,
        )
        db.session.add(gis_rec)
        db.session.flush()
        gis_data_dict = gis_rec.to_dict()

        for ftype, fdata in facilities_raw.items():
            nearest = fdata.get("nearest")
            nearest_d = fdata.get("nearest_distance_km")
            db.session.add(FacilityRecord(
                evaluation_id=evaluation.id,
                facility_type=ftype,
                name=nearest.get("name") if isinstance(nearest, dict) else None,
                distance_km=nearest_d,
                latitude=nearest.get("latitude", nearest.get("lat")) if isinstance(nearest, dict) else None,
                longitude=nearest.get("longitude", nearest.get("lon")) if isinstance(nearest, dict) else None,
                count_within_1km=fdata.get("count_within_1km"),
                count_within_3km=fdata.get("count_within_3km"),
                count_within_5km=fdata.get("count_within_5km"),
                source=fdata.get("source", "OSM/Overpass API"),
                status=fdata.get("status", "SUCCESS"),
            ))

    # Populate unified_data with retrieved live GIS distances & 3km counts before ML
    gis_dist_key_map = {
        "school": "nearest_school_km",
        "hospital": "nearest_hospital_km",
        "supermarket": "nearest_supermarket_km",
        "market": "nearest_market_km",
        "pharmacy": "nearest_pharmacy_km",
        "police": "nearest_police_station_km",
        "bank": "nearest_bank_km",
        "bus_stop": "nearest_bus_stop_km",
        "railway_station": "nearest_railway_station_km",
        "waterbody": "distance_to_nearest_waterbody_km",
    }
    gis_count_key_map = {
        "school": "school_count_3km",
        "hospital": "hospital_count_3km",
        "market": "market_count_3km",
        "supermarket": "supermarket_count_3km",
        "bank": "bank_count_3km",
        "bus_stop": "bus_stop_count_3km",
        "pharmacy": "pharmacy_count_3km",
        "police": "police_station_count_3km",
        "railway_station": "railway_station_count_3km",
        "waterbody": "waterbody_count_3km",
    }
    for ftype, fdata in facilities_raw.items():
        dk = gis_dist_key_map.get(ftype)
        if dk and unified_data.get(dk) in (None, "") and fdata.get("nearest_distance_km") is not None:
            unified_data[dk] = fdata["nearest_distance_km"]
        ck = gis_count_key_map.get(ftype)
        if ck and unified_data.get(ck) in (None, "") and fdata.get("count_within_3km") is not None:
            unified_data[ck] = fdata["count_within_3km"]

    # Combine hospital and clinic distance conservatively if nearest hospital wasn't closer
    if unified_data.get("nearest_hospital_km") in (None, "") and facilities_raw.get("clinic", {}).get("nearest_distance_km") is not None:
        unified_data["nearest_hospital_km"] = facilities_raw["clinic"]["nearest_distance_km"]

    # ── Step 2: ML Price Prediction (uses real GIS features + canonical ML land_type) ─
    pred_result = None
    try:
        from services.classification_service import map_land_type_for_ml
        from ml.predict import impute_missing_gis_features
        ml_input_dict = dict(unified_data)
        if ml_input_dict.get("village_or_locality") in ("Locality Requires Verification", "Locality could not be confidently resolved"):
            ml_input_dict["village_or_locality"] = "Unknown"
        ml_input_dict["land_type"] = map_land_type_for_ml(ml_input_dict.get("land_type"))
        # Prevent missing/unavailable GIS from falling back to rural-heavy district medians
        ml_input_dict = impute_missing_gis_features(ml_input_dict)
        input_df = prepare_single_input(ml_input_dict)
        pred_result = predict_price_per_sqft(input_df, input_data=ml_input_dict, explain=True)
        cur_m, peak_m = _get_rss_mb()
        log.info(f"[EVAL-ML] rss={cur_m}MB peak={peak_m}MB")
        psf = pred_result["predicted_price_per_sqft"]

        evaluation.predicted_price_per_sqft = psf
        evaluation.predicted_total_price = round(psf * area, 2)
        evaluation.price_range_low = pred_result["range_low_per_sqft"]
        evaluation.price_range_high = pred_result["range_high_per_sqft"]
        evaluation.model_used = pred_result["model_used"]
        evaluation.training_records = pred_result["training_records"]
        evaluation.validation_mae = pred_result["validation_mae"]
        evaluation.validation_rmse = pred_result["validation_rmse"]
        evaluation.validation_r2 = pred_result["validation_r2"]
        evaluation.confidence_level = pred_result["data_quality"]

        db.session.add(PricePrediction(
            evaluation_id=evaluation.id,
            model_name=pred_result["model_used"],
            predicted_price_per_sqft=psf,
            mae=pred_result["validation_mae"],
            rmse=pred_result["validation_rmse"],
            r2=pred_result["validation_r2"],
            input_features=json.dumps(unified_data),
        ))
        db.session.commit()
    except FileNotFoundError:
        warnings.append("ML model not trained. Run training script to enable price prediction.")
    except Exception as e:
        log.error(f"ML prediction failed: {e}", exc_info=True)
        warnings.append(f"Price prediction encountered an error: {str(e)[:100]}")

    # ── Step 4: Scoring ──────────────────────────────────────────────────
    # Merge data with facilities for scoring (using unified canonical fields)
    flat = prop.to_dict()
    flat.update(unified_data)
    # Add distances from live GIS if available
    for ftype, fdata in facilities_raw.items():
        d_km = fdata.get("nearest_distance_km")
        count = fdata.get("count_within_3km")
        key_map = {
            "school": "nearest_school_km",
            "hospital": "nearest_hospital_km",
            "supermarket": "nearest_supermarket_km",
            "market": "nearest_market_km",
            "bus_stop": "nearest_bus_stop_km",
            "railway_station": "nearest_railway_station_km",
            "bank": "nearest_bank_km",
            "police": "nearest_police_station_km",
            "park": "nearest_park_km",
        }
        if ftype in key_map:
            flat[key_map[ftype]] = d_km
        count_map = {
            "school": "school_count_3km",
            "hospital": "hospital_count_3km",
            "bus_stop": "bus_stop_count_3km",
            "bank": "bank_count_3km",
        }
        if ftype in count_map and count is not None:
            flat[count_map[ftype]] = count

    # Also add waterbody, canal & park explicitly for the environment score & risk checks
    if "waterbody" in facilities_raw:
        wb_data = facilities_raw["waterbody"]
        wb_dist = wb_data.get("nearest_distance_km")
        wb_count = wb_data.get("count_within_3km") if wb_data.get("status") not in ("SOURCE_UNAVAILABLE", "PARTIAL") else None
        gis_data_dict["distance_to_waterbody_km"] = wb_dist
        gis_data_dict["waterbody_count_3km"] = wb_count
        gis_data_dict["waterbody_name"] = (wb_data.get("nearest") or {}).get("name")
    if "canal" in facilities_raw:
        cn_data = facilities_raw["canal"]
        gis_data_dict["distance_to_canal_km"] = cn_data.get("nearest_distance_km")
        gis_data_dict["canal_name"] = (cn_data.get("nearest") or {}).get("name")
    if "park" in facilities_raw:
        pk_data = facilities_raw["park"]
        gis_data_dict["distance_to_park_km"] = pk_data.get("nearest_distance_km")
        gis_data_dict["park_name"] = (pk_data.get("nearest") or {}).get("name")

    from gis.utility_service import assess_property_utilities
    from services.classification_service import build_property_classification_assessment
    utility_assessment = assess_property_utilities(
        lat=lat,
        lon=lon,
        facilities_raw=facilities_raw,
        user_inputs={
            **flat,
            "drainage_available": data.get("drainage_available"),
            "other_infrastructure": data.get("other_infrastructure"),
        },
    )
    prop_classification = build_property_classification_assessment(
        raw_data=data,
        location_audit=location_audit,
        uploaded_documents=[d.to_dict() for d in (prop.documents or [])],
        prop_dict=flat,
    )

    location_res = calc_location_score(flat)
    facility_res = calc_facility_score(facilities_raw if facilities_raw else _build_fac_from_data(flat))
    infra_res = calc_infrastructure_score(flat, utility_assessment=utility_assessment)
    infra_res["utility_assessment"] = utility_assessment
    infra_res["property_classification"] = prop_classification
    utility_res = calc_utility_score(flat, utility_assessment=utility_assessment)
    env_res = calc_environment_score(flat, gis_data_dict)

    evaluation.location_score = location_res["score"]
    evaluation.facility_score = facility_res["score"]
    evaluation.infrastructure_score = infra_res["score"]
    evaluation.utility_score = utility_res["score"]
    evaluation.environment_score = env_res["score"]

    evaluation.location_breakdown = json.dumps(location_res)
    evaluation.facility_breakdown = json.dumps(facility_res)
    evaluation.infrastructure_breakdown = json.dumps(infra_res)
    evaluation.utility_breakdown = json.dumps(utility_res)
    evaluation.environment_breakdown = json.dumps(env_res)

    # Price score (vs dataset distribution)
    price_score_val = None
    if pred_result:
        metrics = get_model_metrics()
        dist = metrics.get("price_distribution", {})
        p25 = dist.get("p25", 2000)
        p75 = dist.get("p75", 5000)
        median = dist.get("median", 3500)
        price_score_res = calc_price_score(
            pred_result["predicted_price_per_sqft"], p25, p75, median
        )
        evaluation.price_score = price_score_res.get("score")
        price_score_val = price_score_res.get("score")
    else:
        price_score_res = {"score": None, "notes": ["Price prediction unavailable."]}

    # Overall
    from models import WeightageVersion
    active_weights = WeightageVersion.query.filter_by(is_active=True).first()
    
    if active_weights:
        weights_dict = {
            "price": active_weights.price_weight / 100,
            "location": active_weights.location_weight / 100,
            "facility": active_weights.facility_weight / 100,
            "environment": active_weights.environment_weight / 100,
            "infrastructure": active_weights.infrastructure_weight / 100,
            "utility": active_weights.utility_weight / 100,
        }
        evaluation.weightage_version_id = active_weights.id
        evaluation.price_weight = active_weights.price_weight
        evaluation.location_weight = active_weights.location_weight
        evaluation.facility_weight = active_weights.facility_weight
        evaluation.environment_weight = active_weights.environment_weight
        evaluation.infrastructure_weight = active_weights.infrastructure_weight
        evaluation.utility_weight = active_weights.utility_weight
    else:
        from services.scoring import WEIGHTS
        weights_dict = WEIGHTS
        evaluation.price_weight = WEIGHTS["price"] * 100
        evaluation.location_weight = WEIGHTS["location"] * 100
        evaluation.facility_weight = WEIGHTS["facility"] * 100
        evaluation.environment_weight = WEIGHTS["environment"] * 100
        evaluation.infrastructure_weight = WEIGHTS["infrastructure"] * 100
        evaluation.utility_weight = WEIGHTS["utility"] * 100

    overall_res = calc_overall_score(
        price_score_val,
        evaluation.location_score,
        evaluation.facility_score,
        evaluation.environment_score,
        evaluation.infrastructure_score,
        evaluation.utility_score,
        weights_dict
    )
    evaluation.overall_score = overall_res["score"]
    evaluation.warnings = json.dumps(warnings)
    evaluation.location_audit = json.dumps(location_audit) if location_audit else None

    db.session.commit()

    # Build full response
    eval_dict = evaluation.to_dict()
    eval_dict["property"] = prop.to_dict()
    eval_dict["gis"] = gis_data_dict
    eval_dict["facilities_detail"] = {
        k: {
            "nearest": v.get("nearest"),
            "nearest_distance_km": v.get("nearest_distance_km"),
            "count_within_1km": v.get("count_within_1km"),
            "count_within_3km": v.get("count_within_3km"),
            "count_within_5km": v.get("count_within_5km"),
            "source": v.get("source"),
            "status": v.get("status"),
            "coverage": v.get("coverage"),
            "retrieved_at": v.get("retrieved_at"),
            "distance_type": "straight_line_haversine",
        }
        for k, v in facilities_raw.items()
    } if facilities_raw else {}
    eval_dict["overall_breakdown"] = overall_res
    eval_dict["utility_assessment"] = utility_assessment
    eval_dict["property_classification"] = prop_classification
    eval_dict["price_score_detail"] = price_score_res if pred_result else {}
    eval_dict["region_classification_note"] = region_note
    eval_dict["environmental_coverage_pct"] = env_res.get("coverage_pct", 0.0)
    eval_dict["environmental_source"] = env_res.get("source")
    eval_dict["last_gis_retrieved_at"] = gis_data_dict.get("retrieved_at")
    eval_dict["location_audit"] = location_audit
    eval_dict["warnings"] = warnings
    # Expose price_score at top level for dashboard convenience
    eval_dict["price_score"] = evaluation.price_score

    # Reliability, dataset split & locality stats from prediction result
    if pred_result:
        eval_dict["total_dataset_records"]    = pred_result.get("total_dataset_records", 1050)
        eval_dict["holdout_records"]          = pred_result.get("holdout_records", 158)
        eval_dict["kfold_r2"]                 = pred_result.get("kfold_r2")
        eval_dict["kfold_mae"]                = pred_result.get("kfold_mae")
        eval_dict["groupkfold_r2"]            = pred_result.get("groupkfold_r2")
        eval_dict["groupkfold_mae"]           = pred_result.get("groupkfold_mae")
        eval_dict["holdout_r2"]               = pred_result.get("holdout_r2")
        eval_dict["holdout_mae"]              = pred_result.get("holdout_mae")
        eval_dict["uncertainty_mae_used"]     = pred_result.get("uncertainty_mae_used")
        eval_dict["uncertainty_basis"]        = pred_result.get("uncertainty_basis")
        eval_dict["uncertainty_explanation"]  = pred_result.get("uncertainty_explanation")
        eval_dict["reliability_indicator"]    = pred_result.get("reliability_indicator")
        eval_dict["comparable_records_count"] = pred_result.get("comparable_records_count")
        eval_dict["stratum_records_count"]    = pred_result.get("stratum_records_count")
        eval_dict["locality_median_psf"]      = pred_result.get("locality_median_psf")
        eval_dict["locality_p25_psf"]         = pred_result.get("locality_p25_psf")
        eval_dict["locality_p75_psf"]         = pred_result.get("locality_p75_psf")
        # Asking price comparison
        asking = _safe_float(data.get("asking_price_inr"))
        pred_total_v = evaluation.predicted_total_price
        if asking and pred_total_v:
            eval_dict["asking_vs_prediction_pct"] = round((asking - pred_total_v) / pred_total_v * 100, 1)

    # Expose SHAP explanation whenever prediction succeeded (even if market fetch fails)
    if pred_result and pred_result.get("explanation"):
        eval_dict["explanation"] = pred_result["explanation"]

    # ── Step 5: Local Real Estate Market Research ─────────────────────────
    market_data = {}
    asking = _safe_float(data.get("asking_price_inr"))
    try:
        from market.listing_service import fetch_market_listings
        market_data = fetch_market_listings(
            locality=canon_locality,
            taluk=canon_taluk,
            land_type=data.get("land_type", "Residential"),
            listing_type=data.get("listing_type", "Resale"),
            land_area_sqft=area,
            lat=lat,
            lon=lon,
        )
        if pred_result and market_data.get("market_benchmark", {}).get("market_benchmark_psf"):
            benchmark_psf = market_data["market_benchmark"]["market_benchmark_psf"]
            ml_psf = pred_result["predicted_price_per_sqft"]
            if benchmark_psf and benchmark_psf > 0:
                market_data["ml_vs_market_pct"] = round((ml_psf - benchmark_psf) / benchmark_psf * 100, 1)
                market_data["ml_substantially_above_market"] = ml_psf > benchmark_psf * 1.5
            if asking:
                asking_psf = asking / area if area else None
                if asking_psf and benchmark_psf > 0:
                    market_data["asking_vs_market_pct"] = round((asking_psf - benchmark_psf) / benchmark_psf * 100, 1)
        val_summary = build_valuation_summary(
            eval_dict=eval_dict,
            pred_result=pred_result,
            market_data=market_data,
            area=area,
            asking_price_inr=asking,
            locality=canon_locality,
            taluk=canon_taluk,
        )
        market_data["valuation_summary"] = val_summary
        eval_dict["valuation_summary"] = val_summary
        eval_dict["market_comparison"] = market_data
        evaluation.market_comparison = json.dumps(market_data)
        db.session.commit()
        log.info(f"Market research: {market_data.get('status')} — {market_data.get('total_count', 0)} comparable(s)")
    except Exception as e:
        log.warning(f"Market listing service failed: {e}")
        eval_dict["market_comparison"] = {"status": "SOURCE_UNAVAILABLE", "error": str(e)[:100]}
        eval_dict["valuation_summary"] = build_valuation_summary(
            eval_dict=eval_dict,
            pred_result=pred_result,
            market_data={},
            area=area,
            asking_price_inr=asking,
            locality=canon_locality,
            taluk=canon_taluk,
        )

    return jsonify({"evaluation": eval_dict}), 200


def build_valuation_summary(
    eval_dict: dict,
    pred_result: dict | None,
    market_data: dict | None,
    area: float,
    asking_price_inr: float | None,
    locality: str,
    taluk: str,
) -> dict:
    """
    Build structured separation of ML Model Estimate vs Comparable Market Range
    vs User Asking Price with contextual uncertainty & difference explanations.
    Never blindly averages ML predictions and market asking prices.
    """
    pred_res = pred_result or {}
    mkt = market_data or {}
    mb = mkt.get("market_benchmark") or {}
    rel = pred_res.get("reliability_indicator") or eval_dict.get("reliability_indicator") or {}

    ml_psf = pred_res.get("predicted_price_per_sqft") or eval_dict.get("predicted_price_per_sqft")
    ml_low = pred_res.get("range_low_per_sqft") or eval_dict.get("price_range_low")
    ml_high = pred_res.get("range_high_per_sqft") or eval_dict.get("price_range_high")
    ml_total = round(ml_psf * area, 2) if (ml_psf and area) else eval_dict.get("predicted_total_price")

    bench_psf = mb.get("market_benchmark_psf")
    bench_total = round(bench_psf * area, 2) if (bench_psf and area) else None

    ask_psf = round(float(asking_price_inr) / area, 2) if (asking_price_inr and area) else None

    ml_vs_mkt_pct = None
    ml_vs_mkt_psf = None
    if ml_psf and bench_psf and bench_psf > 0:
        ml_vs_mkt_pct = round((ml_psf - bench_psf) / bench_psf * 100, 1)
        ml_vs_mkt_psf = round(ml_psf - bench_psf, 2)

    ask_vs_ml_pct = None
    ask_vs_ml_psf = None
    if ask_psf and ml_psf and ml_psf > 0:
        ask_vs_ml_pct = round((ask_psf - ml_psf) / ml_psf * 100, 1)
        ask_vs_ml_psf = round(ask_psf - ml_psf, 2)

    ask_vs_mkt_pct = None
    ask_vs_mkt_psf = None
    if ask_psf and bench_psf and bench_psf > 0:
        ask_vs_mkt_pct = round((ask_psf - bench_psf) / bench_psf * 100, 1)
        ask_vs_mkt_psf = round(ask_psf - bench_psf, 2)

    loc_cnt = rel.get("locality_count", eval_dict.get("comparable_records_count", 0)) or 0
    gkf_mae = pred_res.get("groupkfold_mae") or eval_dict.get("groupkfold_mae")
    holdout_mae = pred_res.get("holdout_mae") or eval_dict.get("holdout_mae") or eval_dict.get("validation_mae")
    unc_basis = pred_res.get("uncertainty_basis") or eval_dict.get("uncertainty_basis")
    unc_mae = pred_res.get("uncertainty_mae_used") or eval_dict.get("uncertainty_mae_used")

    notes = []
    if loc_cnt < 3:
        notes.append(
            f"'{locality}' ({taluk} Taluk) has only {loc_cnt} exact training record(s) in the 1,050-record dataset; "
            f"uncertainty therefore uses out-of-locality GroupKFold MAE (₹{gkf_mae:,.2f}/sq.ft) rather than seen-locality Holdout MAE (₹{holdout_mae:,.2f}/sq.ft)."
            if gkf_mae and holdout_mae else
            f"'{locality}' has sparse dataset coverage ({loc_cnt} exact record(s)); wider GroupKFold error expectation applies."
        )
    else:
        notes.append(
            f"'{locality}' has {loc_cnt} training records; uncertainty spread uses independent Holdout MAE (₹{holdout_mae:,.2f}/sq.ft)."
            if holdout_mae else
            f"'{locality}' has {loc_cnt} training records in the dataset."
        )

    if ml_vs_mkt_pct is not None and bench_psf:
        dir_txt = "above" if ml_vs_mkt_pct >= 0 else "below"
        notes.append(
            f"ML estimate (₹{ml_psf:,.0f}/sq.ft) is {abs(ml_vs_mkt_pct):.1f}% {dir_txt} the comparable asking median "
            f"(₹{bench_psf:,.0f}/sq.ft across {mb.get('live_count', 0)} live portal + {mb.get('historical_count', 0)} historical listings) "
            f"because the tree ensemble weights taluk/stratum and accessibility patterns whereas local comparables reflect active asking rates."
        )
    elif ml_psf:
        notes.append(
            "Few or no external portal comparables were retrieved to cross-check the ML estimate; treat ML output purely as a dataset-derived benchmark."
        )

    if ask_psf and ml_psf:
        a_ml_dir = "above" if (ask_vs_ml_pct or 0) >= 0 else "below"
        msg = f"Seller asking rate (₹{ask_psf:,.0f}/sq.ft) is {abs(ask_vs_ml_pct or 0):.1f}% {a_ml_dir} ML estimate"
        if ask_vs_mkt_pct is not None:
            a_mkt_dir = "above" if ask_vs_mkt_pct >= 0 else "below"
            msg += f" and {abs(ask_vs_mkt_pct):.1f}% {a_mkt_dir} the local comparable median"
        notes.append(msg + ". Do not average ML and asking benchmarks; negotiate from local registered comps and field inspection.")

    # Extract concise SHAP feature drivers (supports ml/explain.py 'top_factors' and legacy 'top_contributors')
    top_drivers = []
    expl = pred_res.get("explanation") or eval_dict.get("explanation") or {}
    raw_factors = expl.get("top_factors") or expl.get("top_contributors") or []
    for item in raw_factors[:5]:
        if isinstance(item, dict) and (item.get("feature") or item.get("display_name")):
            imp = item.get("impact_inr_per_sqft")
            if imp is None:
                imp = item.get("shap_value", 0)
            imp_val = round(float(imp), 2)
            top_drivers.append({
                "feature": item.get("display_name") or item.get("feature"),
                "raw_feature": item.get("feature"),
                "impact_psf": imp_val,
                "direction": item.get("direction") or ("increases" if imp_val >= 0 else "decreases"),
                "explanation": item.get("explanation") or "",
            })

    return {
        "ml_estimate": {
            "price_per_sqft": ml_psf,
            "total_price_inr": ml_total,
            "range_low_per_sqft": ml_low,
            "range_high_per_sqft": ml_high,
            "range_low_total_inr": round(ml_low * area, 2) if (ml_low and area) else None,
            "range_high_total_inr": round(ml_high * area, 2) if (ml_high and area) else None,
            "uncertainty_mae_used": unc_mae,
            "uncertainty_basis": unc_basis,
            "uncertainty_explanation": pred_res.get("uncertainty_explanation") or eval_dict.get("uncertainty_explanation"),
            "is_calibrated_confidence_interval": False,
            "model_used": eval_dict.get("model_used"),
            "top_drivers": top_drivers,
        },
        "market_comparables": {
            "status": mkt.get("status", "NO_LISTINGS"),
            "benchmark_median_psf": bench_psf,
            "benchmark_total_for_area_inr": bench_total,
            "iqr_p25_psf": mb.get("market_p25_psf"),
            "iqr_p75_psf": mb.get("market_p75_psf"),
            "observed_min_psf": mb.get("market_min_psf"),
            "observed_max_psf": mb.get("market_max_psf"),
            "live_count": mb.get("live_count", mkt.get("live_count", 0)),
            "historical_count": mb.get("historical_count", mkt.get("historical_count", 0)),
            "total_count": mkt.get("total_count", 0),
            "dataset_comparison_tier": mkt.get("dataset_comparison_tier") or mb.get("dataset_comparison_tier"),
            "dataset_comparison_note": mkt.get("dataset_comparison_note") or mb.get("dataset_comparison_note") or mb.get("note"),
            "sources": mkt.get("sources") or [],
            "source_urls": mkt.get("source_urls") or [],
            "note": mb.get("note"),
        },
        "user_asking": {
            "total_price_inr": float(asking_price_inr),
            "price_per_sqft": ask_psf,
        } if asking_price_inr else None,
        "differences": {
            "ml_vs_market_pct": ml_vs_mkt_pct,
            "ml_vs_market_psf": ml_vs_mkt_psf,
            "asking_vs_ml_pct": ask_vs_ml_pct,
            "asking_vs_ml_psf": ask_vs_ml_psf,
            "asking_vs_market_pct": ask_vs_mkt_pct,
            "asking_vs_market_psf": ask_vs_mkt_psf,
            "ml_substantially_above_market": bool(ml_psf and bench_psf and ml_psf > bench_psf * 1.5),
        },
        "difference_explanation": " ".join(notes),
    }


def _safe_float(val):
    try:
        return float(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _build_fac_from_data(flat: dict) -> dict:
    """Build facilities dict from flat data fields (for scoring when GIS unavailable)."""
    fac = {}
    pairs = [
        ("school", "nearest_school_km"),
        ("hospital", "nearest_hospital_km"),
        ("supermarket", "nearest_supermarket_km"),
        ("market", "nearest_market_km"),
        ("bus_stop", "nearest_bus_stop_km"),
        ("railway_station", "nearest_railway_station_km"),
        ("bank", "nearest_bank_km"),
        ("police", "nearest_police_station_km"),
        ("pharmacy", "nearest_pharmacy_km"),
    ]
    for ftype, key in pairs:
        val = flat.get(key)
        d_km = None
        try:
            if val is not None and val != "":
                d_km = float(val)
        except Exception:
            pass
        count_key = ftype + "_count_3km"
        count = flat.get(count_key)
        fac[ftype] = {
            "nearest": {"name": "", "distance_km": d_km} if d_km else None,
            "nearest_distance_km": d_km,
            "count_within_3km": int(count) if count is not None else 0,
            "source": "User-provided / Dataset",
        }
    return fac
