"""
User Management Module:
- GET   /api/admin/users
- GET   /api/admin/users/<user_id>
- PATCH /api/admin/users/<user_id>/status
- PATCH /api/admin/users/<user_id>/role
- POST  /api/admin/users/<user_id>/deletion-request
Never exposes password hashes or authentication secrets.
"""
from datetime import datetime, timezone
from ..compat_flask import Blueprint, request, jsonify
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

users_bp = Blueprint("admin_users", __name__, url_prefix="/api/admin/users")

SAFE_USER_PROJECTION = {"_id": 0, "password_hash": 0, "auth_secret_token": 0}
ALLOWED_USER_ROLES = {"STANDARD_USER", "VALUATION_ANALYST", "AUTHORIZED_SURVEYOR"}

@users_bp.route("", methods=["GET"])
@require_permission("users:view")
def list_users():
    search = (request.args.get("search") or "").strip().lower()
    role_filter = (request.args.get("role") or "").strip().upper()
    status_filter = (request.args.get("status") or "").strip().upper()

    users = db_instance["users"].find({}, SAFE_USER_PROJECTION)
    filtered = []
    for u in users:
        if role_filter and u.get("role") != role_filter:
            continue
        if status_filter and u.get("account_status") != status_filter:
            continue
        if search:
            haystack = f"{u.get('user_id', '')} {u.get('full_name', '')} {u.get('email', '')} {u.get('registered_taluk', '')}".lower()
            if search not in haystack:
                continue
        filtered.append(u)

    return jsonify({
        "users": filtered,
        "total": len(filtered)
    }), 200

@users_bp.route("/<user_id>", methods=["GET"])
@require_permission("users:view")
def get_user_profile(user_id):
    user = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    if not user:
        return jsonify({"error": "User not found.", "code": "NOT_FOUND"}), 404

    eval_history = db_instance["property_evaluations"].find(
        {"user_id": user_id},
        {"_id": 0, "evaluation_id": 1, "property_label": 1, "taluk": 1, "predicted_price_inr": 1, "evaluation_date": 1, "evaluation_status": 1}
    )
    # Redact private raw document contents; show only job metadata & status
    doc_history = db_instance["document_analyses"].find(
        {"user_id": user_id},
        {"_id": 0, "job_id": 1, "property_reference": 1, "document_category": 1, "submitted_at": 1, "processing_status": 1, "official_verification_status": 1}
    )
    record_audit_log(
        action="USER_PROFILE_VIEWED",
        resource=f"users/{user_id}",
        result="SUCCESS",
        details=f"Viewed profile, evaluation history, and document metadata for {user_id}."
    )
    return jsonify({
        "user": user,
        "evaluation_history": eval_history,
        "document_analysis_history": doc_history
    }), 200

@users_bp.route("/<user_id>/status", methods=["PATCH"])
@require_permission("users:manage")
def update_user_status(user_id):
    data = request.get_json(silent=True) or {}
    raw_status = data.get("account_status") if data.get("account_status") is not None else data.get("status")
    new_status = (raw_status or "").strip().upper()
    reason = (data.get("reason") or "Administrative status update").strip()

    if new_status not in ("ACTIVE", "DEACTIVATED", "SUSPENDED"):
        return jsonify({"error": "Invalid account_status. Must be ACTIVE, DEACTIVATED, or SUSPENDED.", "code": "VALIDATION_ERROR"}), 400

    user = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    if not user:
        return jsonify({"error": "User not found.", "code": "NOT_FOUND"}), 404

    db_instance["users"].update_one({"user_id": user_id}, {"$set": {"account_status": new_status}})
    record_audit_log(
        action="USER_ACCOUNT_STATUS_CHANGED",
        resource=f"users/{user_id}",
        result="SUCCESS",
        details=f"Changed status from {user.get('account_status')} to {new_status}. Reason: {reason}"
    )
    updated = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    return jsonify({"user": updated}), 200

@users_bp.route("/<user_id>/role", methods=["PATCH"])
@require_permission("users:roles")
def update_user_role(user_id):
    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip().upper()

    if new_role not in ALLOWED_USER_ROLES:
        return jsonify({
            "error": f"Invalid user role. Allowed platform roles: {sorted(list(ALLOWED_USER_ROLES))}. Admin privileges cannot be granted via user role endpoint.",
            "code": "VALIDATION_ERROR"
        }), 400

    user = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    if not user:
        return jsonify({"error": "User not found.", "code": "NOT_FOUND"}), 404

    db_instance["users"].update_one({"user_id": user_id}, {"$set": {"role": new_role}})
    record_audit_log(
        action="USER_ROLE_CHANGED",
        resource=f"users/{user_id}",
        result="SUCCESS",
        details=f"Changed user role from {user.get('role')} to {new_role}."
    )
    updated = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    return jsonify({"user": updated}), 200

@users_bp.route("/<user_id>/deletion-request", methods=["POST"])
@require_permission("users:delete_requests")
def handle_deletion_request(user_id):
    data = request.get_json(silent=True) or {}
    decision = (data.get("decision") or "").strip().upper()
    notes = (data.get("notes") or "").strip()

    if decision not in ("APPROVED", "REJECTED"):
        return jsonify({"error": "Decision must be APPROVED or REJECTED.", "code": "VALIDATION_ERROR"}), 400

    user = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    if not user:
        return jsonify({"error": "User not found.", "code": "NOT_FOUND"}), 404

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    del_req = user.get("deletion_request", {})
    del_req["status"] = f"DELETION_{decision}"
    del_req["processed_at"] = now_iso
    del_req["admin_notes"] = notes

    new_status = "ARCHIVED_DELETED" if decision == "APPROVED" else user.get("account_status", "ACTIVE")
    db_instance["users"].update_one(
        {"user_id": user_id},
        {"$set": {"deletion_request": del_req, "account_status": new_status}}
    )
    record_audit_log(
        action=f"USER_DELETION_REQUEST_{decision}",
        resource=f"users/{user_id}",
        result="SUCCESS",
        details=f"Processed account deletion request for {user_id}: {decision}. Notes: {notes}"
    )
    updated = db_instance["users"].find_one({"user_id": user_id}, SAFE_USER_PROJECTION)
    return jsonify({"user": updated}), 200
