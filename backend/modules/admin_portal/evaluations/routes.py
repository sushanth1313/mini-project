"""
Property Evaluation Management Module:
- GET  /api/admin/evaluations
- GET  /api/admin/evaluations/<evaluation_id>
- POST /api/admin/evaluations/<evaluation_id>/flag
Enforces immutability of historical predicted prices & valuation outputs;
administrative flags and review notes are appended with full audit logging.
"""
import uuid
from datetime import datetime, timezone
from ..compat_flask import Blueprint, request, jsonify, g
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

evaluations_bp = Blueprint("admin_evaluations", __name__, url_prefix="/api/admin/evaluations")

@evaluations_bp.route("", methods=["GET"])
@require_permission("evaluations:view")
def list_evaluations():
    from gis.geo_utils import normalize_taluk
    eval_id_q = (request.args.get("evaluation_id") or "").strip().lower()
    search_q = (request.args.get("search") or "").strip().lower()
    taluk_q_raw = (request.args.get("taluk") or "").strip()
    taluk_q = normalize_taluk(taluk_q_raw) if taluk_q_raw else ""
    locality_q = (request.args.get("locality") or "").strip().lower()
    prop_type_q = (request.args.get("property_type") or "").strip()
    status_q = (request.args.get("status") or "").strip().upper()
    flagged_only = str(request.args.get("flagged") or "").strip().lower() in ("true", "1", "yes")
    date_q = (request.args.get("date") or "").strip()
    page = max(1, int(request.args.get("page") or 1))
    per_page = min(100, max(1, int(request.args.get("per_page") or 20)))

    all_evals = db_instance["property_evaluations"].find({}, {"_id": 0})
    results = []
    for ev in all_evals:
        if eval_id_q and eval_id_q not in ev.get("evaluation_id", "").lower():
            continue
        if taluk_q and normalize_taluk(ev.get("taluk") or "") != taluk_q:
            continue
        if locality_q and locality_q not in ev.get("locality", "").lower():
            continue
        if prop_type_q and ev.get("property_type") != prop_type_q:
            continue
        if status_q and ev.get("evaluation_status") != status_q:
            continue
        if flagged_only and not ev.get("flagged_suspicious"):
            continue
        if date_q and not str(ev.get("evaluation_date", "")).startswith(date_q):
            continue
        if search_q:
            hay = (
                f"{ev.get('evaluation_id', '')} {ev.get('property_label', '')} "
                f"{ev.get('locality', '')} {ev.get('taluk', '')} "
                f"{ev.get('user_name', '')} {ev.get('user_id', '')}"
            ).lower()
            if search_q not in hay:
                continue
        results.append(ev)

    results.sort(key=lambda x: x.get("evaluation_date", ""), reverse=True)
    total = len(results)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    paged = results[start:start + per_page]

    return jsonify({
        "evaluations": paged,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "failed_count": sum(1 for e in results if e.get("evaluation_status") == "FAILED"),
        "flagged_count": sum(1 for e in results if e.get("flagged_suspicious"))
    }), 200

@evaluations_bp.route("/<evaluation_id>", methods=["GET"])
@require_permission("evaluations:view")
def get_evaluation_detail(evaluation_id):
    ev = db_instance["property_evaluations"].find_one({"evaluation_id": evaluation_id}, {"_id": 0})
    if not ev:
        return jsonify({"error": "Property evaluation not found.", "code": "NOT_FOUND"}), 404

    linked_report = None
    if ev.get("report_id"):
        linked_report = db_instance["reports"].find_one({"report_id": ev["report_id"]}, {"_id": 0})

    # Attach full SQLite breakdown (sub-scores, market benchmark, GIS facilities, location audit)
    sqlite_detail = {}
    try:
        from models import FacilityRecord, PropertyEvaluation
        ev_id_num = ev.get("id")
        if ev_id_num:
            raw_ev = PropertyEvaluation.query.get(int(ev_id_num))
            if raw_ev:
                d = raw_ev.to_dict()
                facs = FacilityRecord.query.filter_by(evaluation_id=raw_ev.id).all()
                sqlite_detail = {
                    "price_score": d.get("price_score"),
                    "location_score": d.get("location_score"),
                    "facility_score": d.get("facility_score"),
                    "environment_score": d.get("environment_score"),
                    "infrastructure_score": d.get("infrastructure_score"),
                    "utility_score": d.get("utility_score"),
                    "location_audit": d.get("location_audit"),
                    "market_comparison": d.get("market_comparison"),
                    "warnings": d.get("warnings") or [],
                    "facilities": [f.to_dict() for f in facs],
                }
    except Exception:
        sqlite_detail = {}

    record_audit_log(
        action="EVALUATION_DETAIL_VIEWED",
        resource=f"property_evaluations/{evaluation_id}",
        result="SUCCESS",
        details=f"Inspected evaluation {evaluation_id} ({ev.get('taluk')} - {ev.get('locality')})."
    )
    return jsonify({
        "evaluation": {**ev, **sqlite_detail},
        "linked_pdf_report": linked_report
    }), 200

@evaluations_bp.route("/<evaluation_id>/flag", methods=["POST"])
@require_permission("evaluations:flag")
def flag_evaluation(evaluation_id):
    data = request.get_json(silent=True) or {}
    # Strictly block any attempt to overwrite historical predicted_price_inr or asking_price_inr
    if "predicted_price_inr" in data or "asking_price_inr" in data or "scoring_breakdown" in data:
        record_audit_log(
            action="HISTORICAL_EVALUATION_TAMPER_BLOCKED",
            resource=f"property_evaluations/{evaluation_id}",
            result="DENIED",
            details="Attempted to modify immutable historical valuation prediction or scoring breakdown."
        )
        return jsonify({
            "error": "Historical evaluation predictions and scores are immutable and cannot be modified.",
            "code": "IMMUTABLE_HISTORICAL_RECORD"
        }), 400

    ev = db_instance["property_evaluations"].find_one({"evaluation_id": evaluation_id}, {"_id": 0})
    if not ev:
        return jsonify({"error": "Property evaluation not found.", "code": "NOT_FOUND"}), 404

    flagged = bool(data.get("flagged_suspicious", True))
    reason = (data.get("flag_reason") or "").strip()
    comment = (data.get("admin_comment") or reason).strip()

    if flagged and not reason:
        return jsonify({"error": "A flag_reason is required when flagging an evaluation.", "code": "VALIDATION_ERROR"}), 400

    note_entry = {
        "note_id": f"NOTE-{uuid.uuid4().hex[:6].upper()}",
        "actor": g.current_admin["admin_id"],
        "actor_username": g.current_admin["username"],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "comment": comment or ("Cleared suspicious flag" if not flagged else reason)
    }

    new_status = "FLAGGED" if flagged else ("FAILED" if ev.get("evaluation_status") == "FAILED" else "COMPLETED")
    db_instance["property_evaluations"].update_one(
        {"evaluation_id": evaluation_id},
        {
            "$set": {
                "flagged_suspicious": flagged,
                "flag_reason": reason if flagged else None,
                "evaluation_status": new_status
            },
            "$push": {"admin_notes": note_entry}
        }
    )

    record_audit_log(
        action="EVALUATION_FLAG_UPDATED",
        resource=f"property_evaluations/{evaluation_id}",
        result="SUCCESS",
        details=f"Set flagged_suspicious={flagged} on {evaluation_id}. Reason: {reason}"
    )
    updated = db_instance["property_evaluations"].find_one({"evaluation_id": evaluation_id}, {"_id": 0})
    return jsonify({"evaluation": updated}), 200
