"""
Reports routes: generate and download PDF evaluation reports.
"""
import os
import logging
from flask import Blueprint, jsonify, send_file, current_app, request
from models import db, Property, PropertyEvaluation, Report, FacilityRecord, Document, VerificationItem
from reports.generator import generate_pdf_report
from datetime import datetime

log = logging.getLogger(__name__)
reports_bp = Blueprint("reports", __name__, url_prefix="/api")


@reports_bp.route("/properties/<int:prop_id>/report", methods=["POST"])
def generate_report(prop_id):
    """Generate a PDF evaluation report for a property."""
    prop = Property.query.get_or_404(prop_id)

    # Get latest evaluation
    evaluations = sorted(prop.evaluations, key=lambda e: e.id, reverse=True)
    if not evaluations:
        return jsonify({"error": "No evaluation found. Run an evaluation first."}), 400

    ev = evaluations[0]

    # Gather data
    facilities = FacilityRecord.query.filter_by(evaluation_id=ev.id).all()
    documents = Document.query.filter_by(property_id=prop_id).all()
    verification_items = VerificationItem.query.filter_by(property_id=prop_id).all()

    # Enrich evaluation dict with reliability indicator, locality stats & reconciled model metadata
    prop_dict = prop.to_dict()
    ev_dict = ev.to_dict()
    try:
        from ml.predict import _reliability_indicator, _load_metrics
        metrics = _load_metrics()
        if metrics:
            ev_dict["total_dataset_records"] = metrics.get("total_records_in_file", 1050)
            ev_dict["feature_count"] = metrics.get("feature_count", 47)
            ev_dict["training_records"] = ev_dict.get("training_records") or metrics.get("training_records", 892)
            ev_dict["holdout_records"] = (metrics.get("train_test_split") or {}).get("test_size", 158)
            ev_dict["holdout_metrics"] = metrics.get("holdout_metrics", {})
            ev_dict["kfold_r2"] = metrics.get("kfold_r2")
            ev_dict["kfold_mae"] = metrics.get("kfold_mae")
            ev_dict["groupkfold_r2"] = metrics.get("validation_r2")
            ev_dict["groupkfold_mae"] = metrics.get("validation_mae")
        env_b = ev_dict.get("environment_breakdown") or {}
        ev_dict["environmental_coverage_pct"] = env_b.get("coverage_pct")
        ev_dict["environmental_source"] = env_b.get("source")
        infra_b = ev_dict.get("infrastructure_breakdown") or {}
        if isinstance(infra_b, dict) and infra_b.get("utility_assessment"):
            ev_dict["utility_assessment"] = infra_b["utility_assessment"]
        elif prop.latitude is not None and prop.longitude is not None:
            from gis.utility_service import assess_property_utilities
            fac_map_for_ua = {}
            for f in facilities:
                fd = f.to_dict()
                fac_map_for_ua[fd["facility_type"]] = {
                    "nearest": {"name": fd.get("name"), "latitude": fd.get("latitude"), "longitude": fd.get("longitude")},
                    "nearest_distance_km": fd.get("distance_km"),
                    "count_within_1km": fd.get("count_within_1km"),
                    "count_within_3km": fd.get("count_within_3km"),
                    "count_within_5km": fd.get("count_within_5km"),
                    "source": fd.get("source"),
                    "status": fd.get("status"),
                    "retrieved_at": fd.get("retrieved_at"),
                }
            ev_dict["utility_assessment"] = assess_property_utilities(
                lat=prop.latitude,
                lon=prop.longitude,
                facilities_raw=fac_map_for_ua,
                user_inputs=prop_dict,
            )
        if isinstance(infra_b, dict) and infra_b.get("property_classification"):
            ev_dict["property_classification"] = infra_b["property_classification"]
        else:
            from services.classification_service import build_property_classification_assessment
            ev_dict["property_classification"] = build_property_classification_assessment(
                raw_data=prop_dict,
                location_audit=ev_dict.get("location_audit") if isinstance(ev_dict.get("location_audit"), dict) else {},
                uploaded_documents=[d.to_dict() for d in documents],
                prop_dict=prop_dict,
            )
        if ev.gis_analysis and ev.gis_analysis.retrieved_at:
            ev_dict["last_gis_retrieved_at"] = ev.gis_analysis.retrieved_at.isoformat()
        if ev.predicted_price_per_sqft is not None:
            rel = _reliability_indicator(prop_dict, ev.predicted_price_per_sqft, metrics)
            ev_dict["reliability_indicator"] = rel
            ev_dict["comparable_records_count"] = rel.get("locality_count", 0)
            ev_dict["stratum_records_count"] = rel.get("stratum_count", 0)
            ev_dict["locality_median_psf"] = rel.get("locality_median_psf")
            ev_dict["locality_p25_psf"] = rel.get("locality_p25_psf")
            ev_dict["locality_p75_psf"] = rel.get("locality_p75_psf")
        if not ev_dict.get("market_comparison"):
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
                if ev.predicted_price_per_sqft:
                    ml_psf = ev.predicted_price_per_sqft
                    mkt["ml_vs_market_pct"] = round((ml_psf - bench_psf) / bench_psf * 100, 1)
                    mkt["ml_substantially_above_market"] = ml_psf > bench_psf * 1.5
                if prop.asking_price_inr and prop.land_area_sqft:
                    ask_psf = prop.asking_price_inr / prop.land_area_sqft
                    mkt["asking_vs_market_pct"] = round((ask_psf - bench_psf) / bench_psf * 100, 1)
            ev_dict["market_comparison"] = mkt
        if isinstance(ev_dict.get("market_comparison"), dict) and ev_dict["market_comparison"].get("valuation_summary"):
            ev_dict["valuation_summary"] = ev_dict["market_comparison"]["valuation_summary"]
        elif isinstance(ev_dict.get("market_comparison"), dict):
            from routes.evaluate import build_valuation_summary
            val_sum = build_valuation_summary(
                eval_dict=ev_dict,
                pred_result=None,
                market_data=ev_dict["market_comparison"],
                area=prop.land_area_sqft or 0,
                asking_price_inr=prop.asking_price_inr,
                locality=prop.village_or_locality or "",
                taluk=prop.taluk or "Mysuru",
            )
            ev_dict["valuation_summary"] = val_sum
    except Exception as e:
        log.warning(f"Could not compute reliability/metadata for report: {e}")

    # Build paths
    reports_folder = current_app.config["REPORTS_FOLDER"]
    os.makedirs(reports_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evaluation_report_{prop_id}_{timestamp}.pdf"
    output_path = os.path.join(reports_folder, filename)

    try:
        generate_pdf_report(
            property_data=prop_dict,
            evaluation=ev_dict,
            facilities=[f.to_dict() for f in facilities],
            documents=[d.to_dict() for d in documents],
            verification_items=[v.to_dict() for v in verification_items],
            output_path=output_path,
        )
    except Exception as e:
        log.error(f"Report generation failed: {e}", exc_info=True)
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

    # Save report record
    file_size = os.path.getsize(output_path)
    report = Report(
        property_id=prop_id,
        evaluation_id=ev.id,
        filename=filename,
        file_path=output_path,
        file_size_bytes=file_size,
    )
    db.session.add(report)
    db.session.commit()

    return send_file(
        output_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):
    report = Report.query.get_or_404(report_id)
    return jsonify(report.to_dict())


@reports_bp.route("/reports/<int:report_id>/download", methods=["GET"])
def download_report(report_id):
    report = Report.query.get_or_404(report_id)
    if not os.path.exists(report.file_path):
        return jsonify({"error": "Report file not found on disk"}), 404
    return send_file(
        report.file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=report.filename,
    )


@reports_bp.route("/reports", methods=["GET"])
def list_reports():
    reports = Report.query.order_by(Report.generated_at.desc()).all()
    return jsonify({"reports": [r.to_dict() for r in reports]})
