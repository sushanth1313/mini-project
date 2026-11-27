"""
Properties routes: CRUD for properties and dataset records.
"""
import json
from flask import Blueprint, request, jsonify
from sqlalchemy.orm import selectinload
from models import db, Property, DatasetRecord, VerificationItem
from documents.extractor import DEFAULT_VERIFICATION_ITEMS

properties_bp = Blueprint("properties", __name__, url_prefix="/api/properties")


def _resolve_request_user():
    """Return (is_customer, user_id, is_admin) cleanly from Bearer token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False, None, False
    try:
        from modules.admin_portal.auth_users import verify_portal_bearer_token
        ok, role, _msg, claims = verify_portal_bearer_token(auth.split(" ", 1)[1].strip())
        if not ok or not claims:
            return False, None, False
        if claims.get("token_type") == "user" and claims.get("user_id"):
            return True, int(claims["user_id"]), False
        return False, None, True
    except Exception:
        return False, None, False


@properties_bp.route("", methods=["GET"])
def list_properties():
    """List customer-owned properties (or guest-session unowned properties when anonymous; all for admins)."""
    is_customer, user_id, is_admin = _resolve_request_user()
    query = Property.query.options(selectinload(Property.evaluations))
    if is_customer and user_id is not None:
        query = query.filter(Property.user_id == user_id)
    elif not is_admin:
        query = query.filter(Property.user_id.is_(None))
    props = query.order_by(Property.created_at.desc()).all()
    result = []
    for p in props:
        d = p.to_dict()
        # Include latest evaluation summary
        if p.evaluations:
            latest = sorted(p.evaluations, key=lambda e: e.id, reverse=True)[0]
            d["latest_evaluation"] = {
                "id": latest.id,
                "overall_score": latest.overall_score,
                "predicted_price_per_sqft": latest.predicted_price_per_sqft,
                "predicted_total_price": latest.predicted_total_price,
                "confidence_level": latest.confidence_level,
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
            }
        else:
            d["latest_evaluation"] = None
        result.append(d)
    return jsonify({"properties": result, "count": len(result)})


@properties_bp.route("", methods=["POST"])
def create_property():
    """Create a new property record."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    # Validate required fields
    required = ["taluk", "village_or_locality", "land_area_sqft"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 422

    try:
        area = float(data["land_area_sqft"])
        if not (0 < area <= 50_000_000):
            return jsonify({"error": "land_area_sqft must be a positive number (<= 50,000,000)"}), 422
    except (ValueError, TypeError):
        return jsonify({"error": "land_area_sqft must be a valid number"}), 422

    from gis.geo_utils import is_in_mysuru_district, normalize_taluk, classify_region_type, normalize_coordinate_status

    raw_lat = data.get("latitude")
    raw_lon = data.get("longitude")
    if (raw_lat not in (None, "")) != (raw_lon not in (None, "")):
        return jsonify({"error": "Provide both latitude and longitude together"}), 422
    lat_chk, lon_chk = None, None
    if raw_lat not in (None, "") and raw_lon not in (None, ""):
        lat_chk = _safe_float(raw_lat)
        lon_chk = _safe_float(raw_lon)
        if lat_chk is None or lon_chk is None or not is_in_mysuru_district(lat_chk, lon_chk):
            return jsonify({
                "error": "Coordinates fall outside the Mysuru District boundary polygon. Latitude must be positive."
            }), 422

    canon_taluk = normalize_taluk(data["taluk"])
    resolved_region, _ = classify_region_type(
        taluk=canon_taluk,
        village_or_locality=data.get("village_or_locality"),
        land_type=data.get("land_type"),
        lat=lat_chk,
        lon=lon_chk,
        explicit_region_type=data.get("region_type"),
    )
    coord_stat = normalize_coordinate_status(data.get("coordinate_status"), default="USER_ENTERED") if (lat_chk is not None) else "LOCALITY_CENTROID"

    is_customer, user_id, _is_admin = _resolve_request_user()
    prop = Property(
        user_id=user_id if is_customer else None,
        name=data.get("name"),
        district=data.get("district", "Mysuru"),
        taluk=canon_taluk,
        village_or_locality=data["village_or_locality"].strip(),
        region_type=resolved_region,
        land_type=data.get("land_type"),
        listing_type=data.get("listing_type"),
        land_area_sqft=area,
        asking_price_inr=_safe_float(data.get("asking_price_inr")),
        latitude=lat_chk,
        longitude=lon_chk,
        coordinate_status=coord_stat,
        coordinate_source=data.get("coordinate_source"),
        road_width_ft=_safe_float(data.get("road_width_ft")),
        road_quality=data.get("road_quality"),
        road_access=data.get("road_access"),
        street_light_available=data.get("street_light_available"),
        public_transport_available=data.get("public_transport_available"),
        electricity_available=data.get("electricity_available"),
        water_supply=data.get("water_supply"),
        water_source_type=data.get("water_source_type"),
        dataset_record_id=data.get("dataset_record_id"),
    )
    db.session.add(prop)
    db.session.flush()  # get ID

    # Create default verification items
    for item_def in DEFAULT_VERIFICATION_ITEMS:
        vi = VerificationItem(
            property_id=prop.id,
            item_key=item_def["key"],
            item_label=item_def["label"],
            status="NEEDS_VERIFICATION",
        )
        db.session.add(vi)

    db.session.commit()
    return jsonify({"property": prop.to_dict(), "message": "Property created"}), 201


@properties_bp.route("/<int:prop_id>", methods=["GET"])
def get_property(prop_id):
    prop = Property.query.get_or_404(prop_id)
    d = prop.to_dict()
    evals = [e.to_dict() for e in sorted(prop.evaluations, key=lambda e: e.id, reverse=True)]
    if evals:
        ev0 = evals[0]
        try:
            from ml.lightweight import compute_reliability_lightweight as _reliability_indicator, _load_metrics
            metrics = _load_metrics()
            if metrics:
                ho_m = metrics.get("holdout_metrics") or {}
                ev0["total_dataset_records"] = metrics.get("total_records_in_file", 1050)
                ev0["holdout_records"] = (metrics.get("train_test_split") or {}).get("test_size", 158)
                ev0["kfold_r2"] = metrics.get("kfold_r2")
                ev0["kfold_mae"] = metrics.get("kfold_mae")
                ev0["groupkfold_r2"] = metrics.get("validation_r2")
                ev0["groupkfold_mae"] = metrics.get("validation_mae")
                ev0["holdout_r2"] = ho_m.get("r2") or metrics.get("holdout_r2")
                ev0["holdout_mae"] = ho_m.get("mae") or metrics.get("holdout_mae")
            if ev0.get("predicted_price_per_sqft") is not None:
                rel = _reliability_indicator(d, ev0["predicted_price_per_sqft"], metrics)
                ev0["reliability_indicator"] = rel
                ev0["comparable_records_count"] = rel.get("locality_count", 0)
                ev0["locality_median_psf"] = rel.get("locality_median_psf")
                ev0["locality_p25_psf"] = rel.get("locality_p25_psf")
                ev0["locality_p75_psf"] = rel.get("locality_p75_psf")
                # Populate contextual uncertainty basis consistent with predict.py
                is_sparse = (rel.get("locality_count", 0) or 0) < 3
                gkf_mae_v = metrics.get("validation_mae") if metrics else None
                ho_mae_v = (metrics.get("holdout_metrics") or {}).get("mae") if metrics else None
                if not ho_mae_v:
                    ho_mae_v = (metrics.get("holdout_mae") if metrics else None) or ev0.get("validation_mae")
                if is_sparse and gkf_mae_v:
                    ev0["uncertainty_mae_used"] = round(float(gkf_mae_v), 2)
                    ev0["uncertainty_basis"] = f"GroupKFold MAE (unseen/sparse locality: {rel.get('locality_count', 0)} training records)"
                else:
                    ev0["uncertainty_mae_used"] = round(float(ho_mae_v or 385.80), 2)
                    ev0["uncertainty_basis"] = f"Holdout MAE (seen locality: {rel.get('locality_count', 0)} training records)"
                ev0["uncertainty_explanation"] = (
                    f"Heuristic error spread of ±1.5 × {ev0['uncertainty_basis']} "
                    f"(±₹{ev0['uncertainty_mae_used'] * 1.5:,.2f}/sq.ft). Not a statistically calibrated confidence interval."
                )
            env_b = ev0.get("environment_breakdown") or {}
            ev0["environmental_coverage_pct"] = env_b.get("coverage_pct")
            ev0["environmental_source"] = env_b.get("source")
            infra_b = ev0.get("infrastructure_breakdown") or {}
            if isinstance(infra_b, dict) and infra_b.get("utility_assessment"):
                ev0["utility_assessment"] = infra_b["utility_assessment"]
            elif prop.latitude is not None and prop.longitude is not None:
                from gis.utility_service import assess_property_utilities
                ev0["utility_assessment"] = assess_property_utilities(
                    lat=prop.latitude,
                    lon=prop.longitude,
                    facilities_raw=ev0.get("facilities_detail") or {},
                    user_inputs=d,
                )
            if isinstance(infra_b, dict) and infra_b.get("property_classification"):
                ev0["property_classification"] = infra_b["property_classification"]
            else:
                from services.classification_service import build_property_classification_assessment
                ev0["property_classification"] = build_property_classification_assessment(
                    raw_data=d,
                    location_audit=ev0.get("location_audit") if isinstance(ev0.get("location_audit"), dict) else {},
                    uploaded_documents=[doc.to_dict() for doc in (prop.documents or [])],
                    prop_dict=d,
                )
            fac_det = ev0.get("facilities_detail") or {}
            retr = [v.get("retrieved_at") for v in fac_det.values() if v.get("retrieved_at")]
            if retr:
                ev0["last_gis_retrieved_at"] = max(retr)
            if not ev0.get("market_comparison"):
                from market.listing_service import fetch_market_listings
                mkt = fetch_market_listings(
                    locality=prop.village_or_locality or "",
                    taluk=prop.taluk or "Mysuru",
                    land_type=prop.land_type or "Residential",
                    listing_type=prop.listing_type or "Resale",
                    land_area_sqft=prop.land_area_sqft,
                    lat=prop.latitude,
                    lon=prop.longitude,
                )
                bench_psf = (mkt.get("market_benchmark") or {}).get("market_benchmark_psf")
                if bench_psf and bench_psf > 0:
                    if ev0.get("predicted_price_per_sqft"):
                        ml_psf = ev0["predicted_price_per_sqft"]
                        mkt["ml_vs_market_pct"] = round((ml_psf - bench_psf) / bench_psf * 100, 1)
                        mkt["ml_substantially_above_market"] = ml_psf > bench_psf * 1.5
                    if prop.asking_price_inr and prop.land_area_sqft:
                        ask_psf = prop.asking_price_inr / prop.land_area_sqft
                        mkt["asking_vs_market_pct"] = round((ask_psf - bench_psf) / bench_psf * 100, 1)
                ev0["market_comparison"] = mkt
            mkt_cur = ev0.get("market_comparison") or {}
            if isinstance(mkt_cur, dict) and not mkt_cur.get("valuation_summary"):
                from routes.evaluate import build_valuation_summary
                val_sum = build_valuation_summary(
                    eval_dict=ev0,
                    pred_result=None,
                    market_data=mkt_cur,
                    area=float(prop.land_area_sqft or 0),
                    asking_price_inr=prop.asking_price_inr,
                    locality=prop.village_or_locality or "",
                    taluk=prop.taluk or "Mysuru",
                )
                ev0["valuation_summary"] = val_sum
            elif isinstance(mkt_cur, dict):
                ev0["valuation_summary"] = mkt_cur.get("valuation_summary")
        except Exception:
            pass
    d["evaluations"] = evals
    d["documents"] = [doc.to_dict() for doc in prop.documents]
    d["reports"] = [r.to_dict() for r in prop.reports]
    return jsonify(d)


@properties_bp.route("/<int:prop_id>", methods=["PUT"])
def update_property(prop_id):
    prop = Property.query.get_or_404(prop_id)
    data = request.get_json(force=True) or {}

    updatable = [
        "name", "taluk", "village_or_locality", "region_type", "land_type",
        "listing_type", "asking_price_inr", "latitude", "longitude",
        "coordinate_status", "road_width_ft", "road_quality",
        "street_light_available", "public_transport_available",
        "electricity_available", "water_supply", "water_source_type",
    ]
    for field in updatable:
        if field in data:
            setattr(prop, field, data[field])

    if "land_area_sqft" in data:
        try:
            area = float(data["land_area_sqft"])
            if area > 0:
                prop.land_area_sqft = area
        except (ValueError, TypeError):
            pass

    db.session.commit()
    return jsonify({"property": prop.to_dict(), "message": "Property updated"})


@properties_bp.route("/<int:prop_id>", methods=["DELETE"])
def delete_property(prop_id):
    prop = Property.query.get_or_404(prop_id)
    try:
        from models import SavedProperty
        SavedProperty.query.filter_by(property_id=prop_id).delete()
    except Exception:
        pass
    try:
        from modules.land_document_analyzer.backend.app import _pipeline
        for rec in _pipeline.db.collection("analyses").find():
            if str((rec.get("property_info") or {}).get("property_id", "")).strip() == str(prop_id):
                aid = rec.get("analysis_id")
                if aid:
                    _pipeline.db.collection("analyses").delete_one({"analysis_id": aid})
    except Exception:
        pass
    db.session.delete(prop)
    db.session.commit()
    return jsonify({"message": "Property deleted"})


@properties_bp.route("/<int:prop_id>/gis", methods=["GET"])
def get_gis(prop_id):
    from models import PropertyEvaluation, GISAnalysis
    prop = Property.query.get_or_404(prop_id)
    # Get latest evaluation's GIS
    evaluations = sorted(prop.evaluations, key=lambda e: e.id, reverse=True)
    if not evaluations:
        return jsonify({"error": "No evaluation found for this property"}), 404
    ev = evaluations[0]
    if not ev.gis_analysis:
        return jsonify({"error": "No GIS analysis found"}), 404
    return jsonify(ev.gis_analysis.to_dict())


@properties_bp.route("/<int:prop_id>/facilities", methods=["GET"])
def get_facilities(prop_id):
    from models import PropertyEvaluation
    prop = Property.query.get_or_404(prop_id)
    evaluations = sorted(prop.evaluations, key=lambda e: e.id, reverse=True)
    if not evaluations:
        return jsonify({"facilities": [], "message": "No evaluation found"}), 200
    ev = evaluations[0]
    return jsonify({"facilities": [f.to_dict() for f in ev.facilities]})


@properties_bp.route("/<int:prop_id>/verification", methods=["GET"])
def get_verification(prop_id):
    from models import VerificationItem
    items = VerificationItem.query.filter_by(property_id=prop_id).all()
    return jsonify({"verification_items": [i.to_dict() for i in items]})


@properties_bp.route("/<int:prop_id>/verification/<int:item_id>", methods=["PUT"])
def update_verification_item(prop_id, item_id):
    from models import VerificationItem
    item = VerificationItem.query.filter_by(id=item_id, property_id=prop_id).first_or_404()
    data = request.get_json(force=True) or {}
    valid_statuses = ["EXTRACTED", "USER_CONFIRMED", "NEEDS_VERIFICATION", "NOT_FOUND"]
    if "status" in data and data["status"] in valid_statuses:
        item.status = data["status"]
    if "notes" in data:
        item.notes = data["notes"]
    db.session.commit()
    return jsonify({"item": item.to_dict()})


@properties_bp.route("/dataset", methods=["GET"])
def list_dataset():
    """Return imported dataset records for reference."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    taluk = request.args.get("taluk")
    land_type = request.args.get("land_type")

    q = DatasetRecord.query
    if taluk:
        q = q.filter(DatasetRecord.taluk == taluk)
    if land_type:
        q = q.filter(DatasetRecord.land_type == land_type)

    total = q.count()
    records = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "records": [r.to_dict() for r in records],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


def _safe_float(val):
    try:
        return float(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None
