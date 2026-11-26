"""
Admin Authentication & Role Management Endpoints:
- POST /api/admin/auth/login
- POST /api/admin/auth/logout
- GET  /api/admin/auth/session
- GET  /api/admin/auth/login-history
- GET  /api/admin/auth/admins
- POST /api/admin/auth/admins
- PATCH /api/admin/auth/admins/<admin_id>/status
"""
import uuid
from datetime import datetime, timezone
from ..compat_flask import Blueprint, request, jsonify, g
from ..config import AdminConfig
from ..database import db_instance, hash_password, verify_password
from ..audit.service import record_audit_log
from .security import (
    ROLE_PERMISSIONS,
    REVOKED_TOKENS,
    generate_admin_token,
    require_permission,
    check_rate_limit
)

auth_bp = Blueprint("admin_auth", __name__, url_prefix="/api/admin/auth")

@auth_bp.route("/login", methods=["POST"])
def login():
    ip = getattr(request, "remote_addr", "127.0.0.1") or "127.0.0.1"
    if not check_rate_limit(f"login:{ip}", AdminConfig.RATE_LIMIT_LOGIN_PER_MINUTE, 60):
        record_audit_log(
            action="ADMIN_LOGIN_RATE_LIMITED",
            resource="auth/login",
            result="DENIED",
            actor_override=ip,
            details="Exceeded maximum login attempts per minute."
        )
        return jsonify({"error": "Too many login attempts. Please wait 60 seconds.", "code": "RATE_LIMITED"}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required.", "code": "VALIDATION_ERROR"}), 400

    # Ensure normal users from `users` collection are explicitly rejected even if they submit valid user credentials
    admin_doc = db_instance["admin_accounts"].find_one({"username": username})
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not admin_doc:
        normal_user = db_instance["users"].find_one({"email": username})
        reason = "Normal platform user attempted admin portal login" if normal_user else "Account not found"
        db_instance["login_history"].insert_one({
            "event_id": f"LGN-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso,
            "username": username,
            "admin_id": None,
            "role": "STANDARD_USER" if normal_user else "NONE",
            "ip_address": ip,
            "status": "FAILED",
            "reason": reason
        })
        record_audit_log(
            action="ADMIN_LOGIN_FAILED",
            resource="auth/login",
            result="FAILED",
            actor_override=username,
            details=reason
        )
        return jsonify({"error": "Invalid administrator credentials.", "code": "INVALID_CREDENTIALS"}), 401

    if admin_doc.get("status") != "ACTIVE":
        db_instance["login_history"].insert_one({
            "event_id": f"LGN-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso,
            "username": username,
            "admin_id": admin_doc["admin_id"],
            "role": admin_doc["role"],
            "ip_address": ip,
            "status": "FAILED",
            "reason": f"Account status is {admin_doc.get('status')}"
        })
        record_audit_log(
            action="ADMIN_LOGIN_FAILED",
            resource="auth/login",
            result="FAILED",
            actor_override=username,
            actor_id_override=admin_doc["admin_id"],
            role_override=admin_doc["role"],
            details=f"Login blocked: account status is {admin_doc.get('status')}."
        )
        return jsonify({"error": "Administrator account is not active.", "code": "ACCOUNT_INACTIVE"}), 403

    if not verify_password(password, admin_doc.get("password_hash", "")):
        db_instance["admin_accounts"].update_one(
            {"admin_id": admin_doc["admin_id"]},
            {"$inc": {"failed_attempts": 1}}
        )
        db_instance["login_history"].insert_one({
            "event_id": f"LGN-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": now_iso,
            "username": username,
            "admin_id": admin_doc["admin_id"],
            "role": admin_doc["role"],
            "ip_address": ip,
            "status": "FAILED",
            "reason": "Invalid password"
        })
        record_audit_log(
            action="ADMIN_LOGIN_FAILED",
            resource="auth/login",
            result="FAILED",
            actor_override=username,
            actor_id_override=admin_doc["admin_id"],
            role_override=admin_doc["role"],
            details="Password verification failed."
        )
        return jsonify({"error": "Invalid administrator credentials.", "code": "INVALID_CREDENTIALS"}), 401

    # Successful authentication
    db_instance["admin_accounts"].update_one(
        {"admin_id": admin_doc["admin_id"]},
        {"$set": {"last_login": now_iso, "failed_attempts": 0}}
    )
    token = generate_admin_token(admin_doc)
    db_instance["login_history"].insert_one({
        "event_id": f"LGN-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": now_iso,
        "username": username,
        "admin_id": admin_doc["admin_id"],
        "role": admin_doc["role"],
        "ip_address": ip,
        "status": "SUCCESS",
        "reason": "Valid credentials"
    })
    record_audit_log(
        action="ADMIN_LOGIN",
        resource="auth/login",
        result="SUCCESS",
        actor_override=username,
        actor_id_override=admin_doc["admin_id"],
        role_override=admin_doc["role"],
        details="Administrator logged in successfully."
    )

    return jsonify({
        "token": token,
        "admin": {
            "admin_id": admin_doc["admin_id"],
            "username": admin_doc["username"],
            "full_name": admin_doc["full_name"],
            "role": admin_doc["role"],
            "department": admin_doc.get("department"),
            "status": admin_doc["status"],
            "permissions": sorted(list(ROLE_PERMISSIONS.get(admin_doc["role"], set())))
        },
        "adapter_mode": db_instance.adapter_mode
    }), 200

@auth_bp.route("/logout", methods=["POST"])
@require_permission("overview:view")
def logout():
    token = g.current_admin.get("token")
    if token:
        REVOKED_TOKENS.add(token)
    record_audit_log(
        action="ADMIN_LOGOUT",
        resource="auth/logout",
        result="SUCCESS",
        details="Session token explicitly revoked."
    )
    return jsonify({"message": "Logged out and token revoked."}), 200

@auth_bp.route("/session", methods=["GET"])
@require_permission("overview:view")
def current_session():
    return jsonify({
        "authenticated": True,
        "admin": {
            "admin_id": g.current_admin["admin_id"],
            "username": g.current_admin["username"],
            "full_name": g.current_admin["full_name"],
            "role": g.current_admin["role"],
            "permissions": g.current_admin["permissions"]
        },
        "adapter_mode": db_instance.adapter_mode
    }), 200

@auth_bp.route("/login-history", methods=["GET"])
@require_permission("audit:view")
def get_login_history():
    status_filter = request.args.get("status")
    query = {}
    if status_filter:
        query["status"] = status_filter.upper()
    records = db_instance["login_history"].find(query, {"_id": 0})
    records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    failed_count = sum(1 for r in records if r.get("status") == "FAILED")
    return jsonify({
        "login_history": records,
        "total_events": len(records),
        "failed_login_count": failed_count
    }), 200

@auth_bp.route("/admins", methods=["GET"])
@require_permission("admins:manage")
def list_admins():
    # Never expose password_hash
    admins = db_instance["admin_accounts"].find({}, {"_id": 0, "password_hash": 0})
    active_admins = [a for a in admins if a.get("status") == "ACTIVE"]
    super_admins = [a for a in admins if a.get("role") == "SUPER_ADMIN"]
    active_super_admins = [a for a in super_admins if a.get("status") == "ACTIVE"]
    consolidated_inactive = [a for a in admins if a.get("status") != "ACTIVE"]
    single_admin_mode = (len(active_admins) == 1 and len(active_super_admins) == 1)
    primary_active = active_super_admins[0] if active_super_admins else (active_admins[0] if active_admins else None)
    governance_summary = {
        "total_admins": len(admins),
        "active_admin_count": len(active_admins),
        "super_admin_count": len(super_admins),
        "active_super_admin_count": len(active_super_admins),
        "consolidated_inactive_count": len(consolidated_inactive),
        "single_admin_mode": single_admin_mode,
        "duplicate_super_admins": len(active_super_admins) > 1 or len(active_admins) > 1,
        "recommended_primary_super_admin": (
            f"{primary_active['username']} ({primary_active['admin_id']})"
            if primary_active
            else "superadmin (ADM-0002)"
        ),
        "migration_plan": (
            f"Single Active Super Admin Mode verified: '{primary_active['admin_id']}' ({primary_active['username']}) "
            f"is the sole active administrator. {len(consolidated_inactive)} historical administrative account(s) "
            "are preserved in DEACTIVATED state with all audit logs retained."
            if single_admin_mode and primary_active
            else "Multiple active administrative accounts detected. Consolidate so only ADM-0002 (superadmin) remains active."
        ),
    }
    return jsonify({
        "admins": admins,
        "governance_summary": governance_summary,
        "role_matrix": {k: sorted(list(v)) for k, v in ROLE_PERMISSIONS.items()}
    }), 200

@auth_bp.route("/admins", methods=["POST"])
@require_permission("admins:manage")
def create_admin():
    record_audit_log(
        action="ADMIN_CREATION_BLOCKED",
        resource="admin_accounts",
        result="DENIED",
        details="Creation of additional administrator accounts blocked under Single Active Super Admin Policy (ADM-0002)."
    )
    return jsonify({
        "error": "Single Active Super Admin Policy enforced: only ADM-0002 (superadmin) may hold active administrative access.",
        "code": "SINGLE_ADMIN_MODE_ENFORCED",
    }), 409

@auth_bp.route("/admins/<admin_id>/status", methods=["PATCH"])
@require_permission("admins:manage")
def update_admin_status(admin_id):
    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().upper()
    new_role = (data.get("role") or "").strip().upper()

    target = db_instance["admin_accounts"].find_one({"admin_id": admin_id})
    if not target:
        return jsonify({"error": "Administrator not found.", "code": "NOT_FOUND"}), 404

    current_admin_id = g.current_admin.get("admin_id")
    if new_status and new_status != "ACTIVE" and admin_id == current_admin_id:
        return jsonify({
            "error": "You cannot suspend or deactivate your own currently signed-in administrator account.",
            "code": "SELF_LOCK_BLOCKED"
        }), 400

    # Protect the last active SUPER_ADMIN from being suspended or demoted
    all_admins = db_instance["admin_accounts"].find({}, {"_id": 0, "password_hash": 0})
    active_supers = [a for a in all_admins if a.get("role") == "SUPER_ADMIN" and a.get("status") == "ACTIVE"]
    is_target_active_super = target.get("role") == "SUPER_ADMIN" and target.get("status") == "ACTIVE"
    if is_target_active_super and len(active_supers) <= 1:
        if (new_status and new_status != "ACTIVE") or (new_role and new_role != "SUPER_ADMIN"):
            return jsonify({
                "error": "At least one active SUPER_ADMIN account must remain enabled.",
                "code": "LAST_SUPER_ADMIN_PROTECTED"
            }), 400

    # Enforce single active administrator policy: do not reactivate consolidated historical accounts
    if new_status == "ACTIVE" and admin_id != "ADM-0002":
        return jsonify({
            "error": "Single Active Super Admin Policy enforced: consolidated historical accounts cannot be reactivated.",
            "code": "SINGLE_ADMIN_MODE_ENFORCED",
        }), 409

    updates = {}
    if new_status:
        if new_status not in ("ACTIVE", "SUSPENDED", "DEACTIVATED"):
            return jsonify({"error": "Invalid status value. Allowed: ACTIVE, SUSPENDED, DEACTIVATED.", "code": "VALIDATION_ERROR"}), 400
        updates["status"] = new_status
        updates["is_active"] = (new_status == "ACTIVE")
    if new_role:
        allowed_roles = {"SUPER_ADMIN", "DATA_ADMIN", "ML_ADMIN", "SYSTEM_ADMIN", "SUPPORT_ADMIN"}
        if new_role not in allowed_roles:
            return jsonify({
                "error": f"Invalid admin role. Supported roles: {sorted(list(allowed_roles))}.",
                "code": "VALIDATION_ERROR"
            }), 400
        updates["role"] = new_role

    if not updates:
        return jsonify({"error": "No valid updates provided.", "code": "VALIDATION_ERROR"}), 400

    db_instance["admin_accounts"].update_one({"admin_id": admin_id}, {"$set": updates})
    record_audit_log(
        action="ADMIN_ACCOUNT_UPDATED",
        resource=f"admin_accounts/{admin_id}",
        result="SUCCESS",
        details=f"Updated admin {admin_id}: {updates}"
    )
    updated = db_instance["admin_accounts"].find_one({"admin_id": admin_id}, {"_id": 0, "password_hash": 0})
    return jsonify({"admin": updated}), 200
