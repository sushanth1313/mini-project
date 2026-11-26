"""
Security, Token Management, Rate Limiting & Role-Based Access Control (RBAC).
Enforces permissions strictly on the backend based on verified database roles.
Never trusts client-supplied role overrides in headers or request payloads.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
from functools import wraps

from ..config import AdminConfig
from ..database import db_instance
from ..compat_flask import request, jsonify, g
from ..audit.service import record_audit_log

# 5-Role Admin RBAC Matrix + backward-compatible ADMIN alias
_DATA_ADMIN_PERMS = {
    "overview:view",
    "datasets:view", "datasets:upload", "datasets:validate", "datasets:clean", "datasets:download",
    "models:view",
    "evaluations:view",
    "notifications:view", "notifications:manage",
}

_ML_ADMIN_PERMS = {
    "overview:view",
    "models:view", "models:train", "models:compare", "models:approve_deploy", "models:rollback",
    "datasets:view",
    "evaluations:view",
    "notifications:view", "notifications:manage",
}

_SYSTEM_ADMIN_PERMS = {
    "overview:view",
    "health:view", "health:check",
    "gis:view", "gis:manage_cache", "gis:configure",
    "audit:view",
    "settings:view",
    "notifications:view", "notifications:manage",
}

_SUPPORT_ADMIN_PERMS = {
    "overview:view",
    "users:view",
    "support:view", "support:reply", "support:manage",
    "notifications:view", "notifications:manage",
    "evaluations:view",
    "documents:view",
    "reports:view", "reports:download",
}

_ADMIN_PERMS = (
    _DATA_ADMIN_PERMS
    | _SYSTEM_ADMIN_PERMS
    | _SUPPORT_ADMIN_PERMS
    | {"users:manage", "evaluations:flag", "models:view", "reports:view", "reports:download", "reports:consistency"}
)

ROLE_PERMISSIONS = {
    "SUPER_ADMIN": {
        "overview:view",
        "admins:manage",
        "users:view", "users:manage", "users:roles", "users:delete_requests",
        "evaluations:view", "evaluations:flag",
        "datasets:view", "datasets:upload", "datasets:validate", "datasets:clean", "datasets:download",
        "models:view", "models:train", "models:compare", "models:approve_deploy", "models:rollback",
        "gis:view", "gis:manage_cache", "gis:configure",
        "documents:view", "documents:inspect_sensitive", "documents:retention", "documents:delete_requests",
        "reports:view", "reports:download", "reports:consistency",
        "health:view", "health:check",
        "audit:view",
        "settings:view", "settings:manage",
        "support:view", "support:reply", "support:manage",
        "notifications:view", "notifications:manage",
    },
    "DATA_ADMIN": _DATA_ADMIN_PERMS,
    "ML_ADMIN": _ML_ADMIN_PERMS,
    "SYSTEM_ADMIN": _SYSTEM_ADMIN_PERMS,
    "SUPPORT_ADMIN": _SUPPORT_ADMIN_PERMS,
    "ADMIN": _ADMIN_PERMS,
}

# Active session revocation list & rate-limiting buckets
REVOKED_TOKENS = set()
RATE_LIMIT_BUCKETS = {}

def check_rate_limit(bucket_key: str, max_requests: int, window_seconds: int = 60) -> bool:
    now = time.time()
    timestamps = RATE_LIMIT_BUCKETS.get(bucket_key, [])
    timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(timestamps) >= max_requests:
        RATE_LIMIT_BUCKETS[bucket_key] = timestamps
        return False
    timestamps.append(now)
    RATE_LIMIT_BUCKETS[bucket_key] = timestamps
    return True

def reset_rate_limits():
    RATE_LIMIT_BUCKETS.clear()

def generate_admin_token(admin_doc: dict) -> str:
    """Creates an HMAC-SHA256 signed JWT token containing admin_id, role, exp, and csrf_token."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": admin_doc["admin_id"],
        "username": admin_doc["username"],
        "role": admin_doc["role"],
        "iat": now,
        "exp": now + (AdminConfig.JWT_EXPIRY_MINUTES * 60),
        "jti": uuid.uuid4().hex,
        "csrf": uuid.uuid4().hex[:16]
    }
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(AdminConfig.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"

def decode_admin_token(token: str) -> dict:
    if not token or token in REVOKED_TOKENS:
        raise ValueError("Token is missing or has been revoked.")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token structure.")
    h_b64, p_b64, s_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    expected_sig = hmac.new(AdminConfig.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")
    if not hmac.compare_digest(s_b64, expected_b64):
        raise ValueError("Invalid cryptographic signature.")
    pad = "=" * (-len(p_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(p_b64 + pad).decode("utf-8"))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Session token has expired.")
    return payload

def require_permission(required_perm: str):
    """
    Decorator that authenticates the Bearer token, reloads the administrator
    record directly from the database (preventing privilege escalation via forged
    frontend payloads or stale tokens), and enforces the RBAC permission matrix.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            g.correlation_id = request.headers.get("X-Correlation-ID") or f"req-mys-{uuid.uuid4().hex[:8]}"
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                record_audit_log(
                    action="UNAUTHORIZED_ACCESS_ATTEMPT",
                    resource=request.path,
                    result="DENIED",
                    details="Missing Bearer token in Authorization header."
                )
                return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401

            token = auth_header.split(" ", 1)[1].strip()
            try:
                claims = decode_admin_token(token)
            except ValueError as err:
                record_audit_log(
                    action="INVALID_TOKEN_ACCESS_ATTEMPT",
                    resource=request.path,
                    result="DENIED",
                    details=str(err)
                )
                return jsonify({"error": str(err), "code": "INVALID_TOKEN"}), 401

            # Reload administrator from DB to guarantee live status and true backend role
            admin_doc = db_instance["admin_accounts"].find_one({"admin_id": claims.get("sub")})
            if not admin_doc:
                # Explicitly ensure normal users from `users` collection can never authenticate as admin
                record_audit_log(
                    action="NON_ADMIN_PRIVILEGE_ESCALATION_BLOCKED",
                    resource=request.path,
                    result="DENIED",
                    details=f"Subject {claims.get('sub')} does not exist in admin_accounts."
                )
                return jsonify({"error": "Administrator account not found", "code": "FORBIDDEN"}), 403

            if admin_doc.get("status") != "ACTIVE":
                record_audit_log(
                    action="INACTIVE_ADMIN_ACCESS_BLOCKED",
                    resource=request.path,
                    result="DENIED",
                    actor_override=admin_doc.get("username"),
                    actor_id_override=admin_doc.get("admin_id"),
                    role_override=admin_doc.get("role"),
                    details=f"Account status is {admin_doc.get('status')}."
                )
                return jsonify({"error": "Administrator account is deactivated or locked", "code": "ACCOUNT_INACTIVE"}), 403

            true_role = admin_doc.get("role")
            allowed_perms = ROLE_PERMISSIONS.get(true_role, set())

            # Detect any attempt by client to inject fake role in JSON payload or headers
            body = request.get_json(silent=True) or {}
            client_claimed_role = request.headers.get("X-Client-Role") or body.get("_injected_admin_role")
            if client_claimed_role and client_claimed_role != true_role:
                record_audit_log(
                    action="PRIVILEGE_ESCALATION_ATTEMPT_DETECTED",
                    resource=request.path,
                    result="DENIED",
                    actor_override=admin_doc["username"],
                    actor_id_override=admin_doc["admin_id"],
                    role_override=true_role,
                    details=f"Client attempted to claim role '{client_claimed_role}' while authenticated as '{true_role}'."
                )
                return jsonify({
                    "error": "Privilege escalation attempt blocked and logged.",
                    "code": "PRIVILEGE_ESCALATION_BLOCKED"
                }), 403

            if required_perm and required_perm not in allowed_perms:
                record_audit_log(
                    action="RBAC_PERMISSION_DENIED",
                    resource=request.path,
                    result="DENIED",
                    actor_override=admin_doc["username"],
                    actor_id_override=admin_doc["admin_id"],
                    role_override=true_role,
                    details=f"Role '{true_role}' lacks required permission '{required_perm}'."
                )
                return jsonify({
                    "error": f"Role '{true_role}' is not authorized for permission '{required_perm}'.",
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "required_permission": required_perm,
                    "current_role": true_role
                }), 403

            g.current_admin = {
                "admin_id": admin_doc["admin_id"],
                "username": admin_doc["username"],
                "full_name": admin_doc["full_name"],
                "role": true_role,
                "permissions": sorted(list(allowed_perms)),
                "token": token
            }
            return fn(*args, **kwargs)
        return wrapper
    return decorator
