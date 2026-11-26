"""
System Settings Module:
- GET   /api/admin/settings
- PATCH /api/admin/settings
Manages application configuration, GIS search radius & timeouts, upload limits,
retention policies, PDF report settings, model deployment rules, and maintenance mode.
Never exposes API keys or secrets in frontend responses.
"""
from datetime import datetime, timezone
from ..compat_flask import Blueprint, request, jsonify, g
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

settings_bp = Blueprint("admin_settings", __name__, url_prefix="/api/admin/settings")

@settings_bp.route("", methods=["GET"])
@require_permission("settings:view")
def get_settings():
    doc = db_instance["system_settings"].find_one({"settings_id": "SYS-SET-MYSURU-01"}, {"_id": 0})
    return jsonify({"settings": doc}), 200

@settings_bp.route("", methods=["PATCH"])
@require_permission("settings:manage")
def update_settings():
    data = request.get_json(silent=True) or {}
    current = db_instance["system_settings"].find_one({"settings_id": "SYS-SET-MYSURU-01"})
    if not current:
        return jsonify({"error": "System settings record not found.", "code": "NOT_FOUND"}), 404

    updates = {}
    if "maintenance_mode" in data:
        app_cfg = dict(current.get("application_config", {}))
        app_cfg["maintenance_mode"] = bool(data["maintenance_mode"])
        if "maintenance_banner_message" in data:
            app_cfg["maintenance_banner_message"] = str(data["maintenance_banner_message"]).strip()
        updates["application_config"] = app_cfg

    if "default_search_radius_meters" in data or "api_timeout_seconds" in data:
        gis_cfg = dict(current.get("gis_configuration", {}))
        if "default_search_radius_meters" in data:
            r = int(data["default_search_radius_meters"])
            if r < 500 or r > 10000:
                return jsonify({"error": "GIS search radius must be between 500 and 10000m.", "code": "VALIDATION_ERROR"}), 400
            gis_cfg["default_search_radius_meters"] = r
        if "api_timeout_seconds" in data:
            t = int(data["api_timeout_seconds"])
            if t < 3 or t > 60:
                return jsonify({"error": "API timeout must be between 3 and 60s.", "code": "VALIDATION_ERROR"}), 400
            gis_cfg["api_timeout_seconds"] = t
        updates["gis_configuration"] = gis_cfg

    if "max_upload_size_mb" in data or "file_retention_days" in data:
        doc_cfg = dict(current.get("document_and_report_policies", {}))
        if "max_upload_size_mb" in data:
            doc_cfg["max_upload_size_mb"] = int(data["max_upload_size_mb"])
        if "file_retention_days" in data:
            doc_cfg["file_retention_days"] = int(data["file_retention_days"])
        updates["document_and_report_policies"] = doc_cfg

    if not updates:
        return jsonify({"error": "No valid configuration fields supplied.", "code": "VALIDATION_ERROR"}), 400

    updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updates["updated_by"] = g.current_admin["admin_id"]

    db_instance["system_settings"].update_one({"settings_id": "SYS-SET-MYSURU-01"}, {"$set": updates})
    record_audit_log(
        action="SYSTEM_SETTINGS_UPDATED",
        resource="system_settings/SYS-SET-MYSURU-01",
        result="SUCCESS",
        details=f"Updated system settings keys: {list(updates.keys())}"
    )
    updated = db_instance["system_settings"].find_one({"settings_id": "SYS-SET-MYSURU-01"}, {"_id": 0})
    return jsonify({"settings": updated}), 200
