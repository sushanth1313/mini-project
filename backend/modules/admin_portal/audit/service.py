"""
Immutable Append-Only Audit Logging Service.
Records every administrative action with correlation ID, timestamp, actor, role,
action, resource, and result. Redacts sensitive keys (passwords, tokens, raw documents).
"""
import uuid
from datetime import datetime, timezone
from flask import has_request_context
from ..database import db_instance
from ..compat_flask import request, g

FORBIDDEN_LOG_KEYS = {
    "password", "password_hash", "token", "access_token", "secret",
    "auth_secret_token", "raw_document_bytes", "private_document_content"
}

def sanitize_audit_metadata(meta: dict) -> dict:
    if not isinstance(meta, dict):
        return {}
    cleaned = {}
    for k, v in meta.items():
        if k.lower() in FORBIDDEN_LOG_KEYS or "password" in k.lower() or "token" in k.lower() or "secret" in k.lower():
            cleaned[k] = "[REDACTED_SENSITIVE]"
        elif isinstance(v, dict):
            cleaned[k] = sanitize_audit_metadata(v)
        else:
            cleaned[k] = v
    return cleaned

def record_audit_log(
    action: str,
    resource: str,
    result: str,
    details: str = "",
    actor_override: str = None,
    actor_id_override: str = None,
    role_override: str = None,
    metadata: dict = None
) -> dict:
    in_req = has_request_context()
    admin_ctx = (getattr(g, "current_admin", None) or {}) if in_req else {}
    correlation_id = (
        (getattr(g, "correlation_id", None) or request.headers.get("X-Correlation-ID"))
        if in_req
        else None
    ) or f"req-mys-{uuid.uuid4().hex[:8]}"

    entry = {
        "audit_id": f"AUD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": actor_override or admin_ctx.get("username", "anonymous"),
        "actor_id": actor_id_override or admin_ctx.get("admin_id", "UNAUTHENTICATED"),
        "role": role_override or admin_ctx.get("role", "NONE"),
        "action": action,
        "resource": resource,
        "result": result,
        "correlation_id": correlation_id,
        "details": details,
        "metadata": sanitize_audit_metadata(metadata or {})
    }
    db_instance["audit_logs"].insert_one(entry)
    return entry
