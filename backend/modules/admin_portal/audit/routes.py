"""
Immutable Append-Only Audit Log Endpoints:
- GET    /api/admin/audit
- DELETE /api/admin/audit/<audit_id>  (Explicitly blocked with 403 IMMUTABLE_AUDIT_LOG)
- PATCH  /api/admin/audit/<audit_id>  (Explicitly blocked with 403 IMMUTABLE_AUDIT_LOG)
"""
from ..compat_flask import Blueprint, request, jsonify
from ..database import db_instance
from ..auth.security import require_permission
from .service import record_audit_log

audit_bp = Blueprint("admin_audit", __name__, url_prefix="/api/admin/audit")

@audit_bp.route("", methods=["GET"])
@require_permission("audit:view")
def list_audit_logs():
    action_q = (request.args.get("action") or "").strip().upper()
    role_q = (request.args.get("role") or "").strip().upper()
    result_q = (request.args.get("result") or "").strip().upper()
    search_q = (request.args.get("search") or "").strip().lower()

    logs = db_instance["audit_logs"].find({}, {"_id": 0})
    filtered = []
    for entry in logs:
        if action_q and action_q not in entry.get("action", "").upper():
            continue
        if role_q and entry.get("role") != role_q:
            continue
        if result_q and entry.get("result") != result_q:
            continue
        if search_q:
            haystack = f"{entry.get('audit_id', '')} {entry.get('actor', '')} {entry.get('action', '')} {entry.get('resource', '')} {entry.get('details', '')} {entry.get('correlation_id', '')}".lower()
            if search_q not in haystack:
                continue
        filtered.append(entry)

    filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify({
        "audit_logs": filtered,
        "total": len(filtered),
        "append_only_enforced": True
    }), 200

@audit_bp.route("/<audit_id>", methods=["DELETE", "PATCH", "PUT"])
@require_permission("audit:view")
def block_audit_modification(audit_id):
    record_audit_log(
        action="AUDIT_LOG_TAMPER_ATTEMPT_BLOCKED",
        resource=f"audit_logs/{audit_id}",
        result="DENIED",
        details=f"Attempted {request.method} on immutable append-only audit record {audit_id}."
    )
    return jsonify({
        "error": "Audit logs are strictly append-only and immutable. Editing or erasing audit records is prohibited.",
        "code": "IMMUTABLE_AUDIT_LOG"
    }), 403
