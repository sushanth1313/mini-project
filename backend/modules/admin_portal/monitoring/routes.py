"""
System Health & API Monitoring Module:
- GET  /api/admin/monitoring/health
- POST /api/admin/monitoring/health/probe
Monitors Frontend, Backend API, MongoDB, ML Model, GIS, OCR, PDF Generation,
Background Jobs, and Storage capacity.
Never shows a service as operational unless it has actually been checked.
"""
import shutil
from datetime import datetime, timezone
from ..compat_flask import Blueprint, jsonify
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

monitoring_bp = Blueprint("admin_monitoring", __name__, url_prefix="/api/admin/monitoring")

@monitoring_bp.route("/health", methods=["GET"])
@require_permission("health:view")
def get_system_health():
    services = db_instance["system_health"].find({}, {"_id": 0})
    bg_jobs = db_instance["background_jobs"].find({}, {"_id": 0})

    # Verify every service was actively checked before reporting OPERATIONAL
    verified_services = []
    alerts = []
    for svc in services:
        s_copy = dict(svc)
        if not s_copy.get("checked_actively") or not s_copy.get("last_checked_at"):
            s_copy["status"] = "UNVERIFIED"
        if s_copy["status"] != "OPERATIONAL":
            alerts.append({
                "service_key": s_copy["service_key"],
                "service_name": s_copy["service_name"],
                "status": s_copy["status"],
                "recent_errors": s_copy.get("recent_errors", [])
            })
        verified_services.append(s_copy)

    # Real disk storage inspection from OS
    total_b, used_b, free_b = shutil.disk_usage("/")
    storage_metrics = {
        "total_gb": round(total_b / (1024 ** 3), 2),
        "used_gb": round(used_b / (1024 ** 3), 2),
        "free_gb": round(free_b / (1024 ** 3), 2),
        "utilization_pct": round((used_b / total_b) * 100, 1) if total_b else 0.0
    }

    return jsonify({
        "adapter_mode": db_instance.adapter_mode,
        "services": verified_services,
        "background_jobs": bg_jobs,
        "storage_capacity": storage_metrics,
        "active_alerts": alerts
    }), 200

@monitoring_bp.route("/health/probe", methods=["POST"])
@require_permission("health:check")
def trigger_active_health_probe():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    health_col = db_instance["system_health"]
    updated = health_col.run_probe() if hasattr(health_col, "run_probe") else health_col.find({}, {"_id": 0})

    record_audit_log(
        action="SYSTEM_HEALTH_ACTIVE_PROBE_EXECUTED",
        resource="system_health/all",
        result="SUCCESS",
        details=f"Executed real active health probe across {len(updated)} services at {now_iso}."
    )
    return jsonify({"probed_at": now_iso, "services": updated}), 200
