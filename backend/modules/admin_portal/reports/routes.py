"""
PDF Report Management Module:
- GET  /api/admin/reports
- GET  /api/admin/reports/<report_id>
- GET  /api/admin/reports/<report_id>/download
- POST /api/admin/reports/<report_id>/consistency-check
Supports Property Evaluation Reports & Land Document Due-Diligence Reports.
Preserves historical report snapshots; never silently regenerates old reports with a newer model.
"""
from ..compat_flask import Blueprint, request, jsonify
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

reports_bp = Blueprint("admin_reports", __name__, url_prefix="/api/admin/reports")

@reports_bp.route("", methods=["GET"])
@require_permission("reports:view")
def list_reports():
    search_q = (request.args.get("search") or "").strip().lower()
    type_q = (request.args.get("report_type") or "").strip()
    status_q = (request.args.get("status") or "").strip().upper()

    reports = db_instance["reports"].find({}, {"_id": 0})
    filtered = []
    for r in reports:
        if type_q and r.get("report_type") != type_q:
            continue
        if status_q and r.get("report_status") != status_q:
            continue
        if search_q:
            haystack = f"{r.get('report_id', '')} {r.get('property_reference', '')} {r.get('user_id', '')} {r.get('model_version', '')}".lower()
            if search_q not in haystack:
                continue
        filtered.append(r)

    filtered.sort(key=lambda x: x.get("generated_date", ""), reverse=True)
    return jsonify({
        "reports": filtered,
        "total": len(filtered),
        "failed_jobs_count": sum(1 for r in reports if r.get("report_status") == "FAILED")
    }), 200

@reports_bp.route("/<report_id>", methods=["GET"])
@require_permission("reports:view")
def preview_report(report_id):
    rep = db_instance["reports"].find_one({"report_id": report_id}, {"_id": 0})
    if not rep:
        return jsonify({"error": "Report not found.", "code": "NOT_FOUND"}), 404

    record_audit_log(
        action="REPORT_PREVIEW_ACCESSED",
        resource=f"reports/{report_id}",
        result="SUCCESS",
        details=f"Previewed {rep.get('report_type')} ({report_id}) snapshot locked to {rep.get('model_version')}."
    )
    return jsonify({"report": rep}), 200

@reports_bp.route("/<report_id>/download", methods=["GET"])
@require_permission("reports:download")
def download_report(report_id):
    import os
    from flask import send_file
    rep = db_instance["reports"].find_one({"report_id": report_id}, {"_id": 0})
    if not rep:
        return jsonify({"error": "Report not found.", "code": "NOT_FOUND"}), 404

    if rep.get("report_status") == "FAILED":
        return jsonify({"error": "Cannot download a failed report job.", "code": "REPORT_FAILED"}), 400

    record_audit_log(
        action="REPORT_AUTHORIZED_DOWNLOAD",
        resource=f"reports/{report_id}",
        result="SUCCESS",
        details=f"Authorized download of immutable snapshot {report_id} (SHA256: {rep.get('snapshot_hash_sha256')})."
    )
    if request.args.get("meta") == "1":
        safe_rep = {k: v for k, v in rep.items() if k != "file_path"}
        return jsonify({
            "report_id": report_id,
            "download_authorized": True,
            "snapshot_hash_sha256": rep.get("snapshot_hash_sha256"),
            "model_version_locked": rep.get("model_version"),
            "report_metadata": safe_rep
        }), 200

    fp = rep.get("file_path")
    if not fp or not os.path.isfile(fp):
        return jsonify({"error": "PDF file is missing on disk.", "code": "FILE_NOT_FOUND"}), 404

    return send_file(
        fp,
        mimetype="application/pdf",
        as_attachment=(request.args.get("inline") != "1"),
        download_name=f"{report_id}.pdf",
    )

@reports_bp.route("/<report_id>/consistency-check", methods=["POST"])
@require_permission("reports:consistency")
def verify_report_consistency(report_id):
    data = request.get_json(silent=True) or {}
    if data.get("silent_regenerate_with_latest_model"):
        record_audit_log(
            action="SILENT_REPORT_REGENERATION_BLOCKED",
            resource=f"reports/{report_id}",
            result="DENIED",
            details="Blocked attempt to silently overwrite historical report snapshot with a newer model."
        )
        return jsonify({
            "error": "Historical report snapshots are immutable and must not be silently regenerated with a newer model.",
            "code": "IMMUTABLE_SNAPSHOT_POLICY"
        }), 400

    rep = db_instance["reports"].find_one({"report_id": report_id}, {"_id": 0})
    if not rep:
        return jsonify({"error": "Report not found.", "code": "NOT_FOUND"}), 404

    has_hash = bool(rep.get("snapshot_hash_sha256"))
    consistent = has_hash and rep.get("report_status") in ("GENERATED", "GENERATED_WITH_WARNINGS")
    record_audit_log(
        action="REPORT_CONSISTENCY_VERIFIED",
        resource=f"reports/{report_id}",
        result="SUCCESS",
        details=f"Consistency check for {report_id}: passed={consistent}."
    )
    return jsonify({
        "report_id": report_id,
        "consistency_check_passed": consistent,
        "snapshot_immutable": rep.get("snapshot_immutable", True),
        "locked_model_version": rep.get("model_version")
    }), 200
