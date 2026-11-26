"""
Admin Analytics Dashboard Endpoint:
- GET /api/admin/overview/metrics
Computes every KPI, chart series, alert, recent activity, and background job
directly from the database collections (zero hardcoded static numbers).
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
from flask import current_app
from ..compat_flask import Blueprint, jsonify
from ..config import MYSURU_TALUKS, PROPERTY_TYPES
from ..database import db_instance
from ..auth.security import require_permission

overview_bp = Blueprint("admin_overview", __name__, url_prefix="/api/admin/overview")

_CACHE_LOCK = threading.Lock()
_METRICS_CACHE = {"ts": 0.0, "payload": None}
_METRICS_TTL_SECONDS = 15.0


def invalidate_overview_cache() -> None:
    """Clear short-lived overview cache when underlying data changes."""
    with _CACHE_LOCK:
        _METRICS_CACHE["ts"] = 0.0
        _METRICS_CACHE["payload"] = None


def _count_generated_reports() -> int:
    """Count generated PDF reports without SHA-256 disk hashing or full joins."""
    count = 0
    meta_map = {
        m.get("report_id"): m
        for m in db_instance.kv_report_meta._list_docs()
        if m.get("report_id")
    }
    try:
        from models import Report
        for r_id, file_path in Report.query.with_entities(Report.id, Report.file_path).all():
            rid = f"RPT-{r_id:04d}"
            meta = meta_map.get(rid, {})
            exists = bool(file_path and os.path.isfile(file_path))
            status = meta.get("report_status") or ("GENERATED" if exists else "FAILED")
            if status in ("GENERATED", "GENERATED_WITH_WARNINGS"):
                count += 1
    except Exception:
        pass
    try:
        from modules.land_document_analyzer.backend.app import _pipeline
        for a in _pipeline.db.collection("analyses").find({}, {"_id": 0, "report_pdf_path": 1}):
            pdf_p = a.get("report_pdf_path")
            if pdf_p and os.path.isfile(pdf_p):
                count += 1
    except Exception:
        pass
    return count


@overview_bp.route("/metrics", methods=["GET"])
@require_permission("overview:view")
def get_dashboard_metrics():
    now_mono = time.monotonic()
    with _CACHE_LOCK:
        if _METRICS_CACHE["payload"] is not None and (now_mono - _METRICS_CACHE["ts"]) < _METRICS_TTL_SECONDS:
            return jsonify(_METRICS_CACHE["payload"]), 200

    app_obj = current_app._get_current_object()

    def _run_in_ctx(fn):
        with app_obj.app_context():
            try:
                return fn()
            finally:
                try:
                    from models import db
                    db.session.remove()
                except Exception:
                    pass

    def _fetch_ticket_kpis():
        pending, high_prio = 0, 0
        try:
            from models import SupportTicket
            pending = SupportTicket.query.filter(
                SupportTicket.status.in_(("OPEN", "IN_PROGRESS", "AWAITING_USER"))
            ).count()
            high_prio = SupportTicket.query.filter(
                SupportTicket.status.notin_(("RESOLVED", "CLOSED")),
                SupportTicket.priority.in_(("HIGH", "URGENT")),
            ).count()
        except Exception:
            pass
        return pending, high_prio

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_users = pool.submit(_run_in_ctx, lambda: db_instance["users"].find({}, {"_id": 0, "password_hash": 0, "auth_secret_token": 0}))
        f_evals = pool.submit(_run_in_ctx, lambda: db_instance["property_evaluations"].find({}, {"_id": 0}))
        f_docs = pool.submit(_run_in_ctx, lambda: db_instance["document_analyses"].find({}, {"_id": 0}))
        f_reports_cnt = pool.submit(_run_in_ctx, _count_generated_reports)
        f_datasets = pool.submit(_run_in_ctx, lambda: db_instance["datasets"].find({}, {"_id": 0}))
        f_models = pool.submit(_run_in_ctx, lambda: db_instance["ml_models"].find({}, {"_id": 0}))
        f_gis_ep = pool.submit(_run_in_ctx, lambda: db_instance["gis_endpoints"].find({}, {"_id": 0}))
        f_gis_logs = pool.submit(_run_in_ctx, lambda: db_instance["gis_logs"].find({}, {"_id": 0}))
        f_bg_jobs = pool.submit(_run_in_ctx, lambda: db_instance["background_jobs"].find({}, {"_id": 0}))
        f_audits = pool.submit(_run_in_ctx, lambda: db_instance["audit_logs"].find({}, {"_id": 0}))
        f_tickets = pool.submit(_run_in_ctx, _fetch_ticket_kpis)

        users = f_users.result()
        evals = f_evals.result()
        docs = f_docs.result()
        reports_generated = f_reports_cnt.result()
        datasets = f_datasets.result()
        models = f_models.result()
        gis_endpoints = f_gis_ep.result()
        gis_logs = f_gis_logs.result()
        bg_jobs = f_bg_jobs.result()
        audits = f_audits.result()
        pending_support_tickets, open_high_priority_tickets = f_tickets.result()

    from datetime import datetime, timezone
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_users = len(users)
    active_users = sum(1 for u in users if u.get("account_status") == "ACTIVE")
    total_evaluations = len(evals)
    evaluations_today = sum(1 for e in evals if str(e.get("evaluation_date", "")).startswith(today_prefix))
    total_doc_analyses = len(docs)

    # Active validated dataset records count
    validated_datasets = [d for d in datasets if d.get("ready_for_training")]
    latest_dataset_records = max((d.get("row_count", 0) for d in validated_datasets), default=0)

    # Current production model
    prod_model = next((m for m in models if m.get("is_production")), None)
    prod_model_version = prod_model["model_version"] if prod_model else "NONE"

    # GIS service availability & failed API requests
    operational_gis = sum(1 for g in gis_endpoints if g.get("availability_status") == "OPERATIONAL")
    gis_availability_pct = round((operational_gis / len(gis_endpoints)) * 100, 1) if gis_endpoints else 0.0
    failed_api_requests = sum(g.get("failed_requests_24h", 0) for g in gis_endpoints)

    # Charts derived directly from database documents
    taluk_counts = Counter(e.get("taluk") for e in evals)
    taluk_distribution = [{"taluk": t, "evaluations": taluk_counts.get(t, 0)} for t in MYSURU_TALUKS]

    prop_type_counts = Counter(e.get("property_type") for e in evals)
    property_type_distribution = [{"property_type": pt, "count": prop_type_counts.get(pt, 0)} for pt in PROPERTY_TYPES]

    evals_by_date = Counter(str(e.get("evaluation_date", ""))[:10] for e in evals if e.get("evaluation_date"))
    evaluations_over_time = [
        {"date": dt, "count": cnt}
        for dt, cnt in sorted(evals_by_date.items())
    ]

    reg_by_month = Counter(str(u.get("registration_date", ""))[:7] for u in users if u.get("registration_date"))
    user_registration_trends = [
        {"month": m, "registrations": cnt}
        for m, cnt in sorted(reg_by_month.items())
    ]

    doc_status_counts = Counter(d.get("processing_status") for d in docs)
    document_analysis_status = [
        {"status": st, "count": cnt}
        for st, cnt in doc_status_counts.items()
    ]

    gis_status_counts = Counter(l.get("status") for l in gis_logs)
    gis_retrieval_rates = [
        {"status": st, "count": gis_status_counts.get(st, 0)}
        for st in ("SUCCESS", "NO_DATA", "PARTIAL", "SOURCE_UNAVAILABLE")
    ]

    model_performance_history = [
        {
            "model_version": m["model_version"],
            "r2_score": m.get("holdout_metrics", {}).get("r2_score"),
            "mae_inr_per_sqft": m.get("holdout_metrics", {}).get("mae_inr_per_sqft"),
            "rmse_inr_per_sqft": m.get("holdout_metrics", {}).get("rmse_inr_per_sqft"),
            "status": m.get("status")
        }
        for m in models
    ]

    # System Alerts & Failed Background Jobs (strictly deduplicated by module, alert_type, reference)
    failed_jobs = [j for j in bg_jobs if j.get("status") == "FAILED"]
    system_alerts = []
    seen_alert_keys = set()

    def _add_alert(severity: str, module: str, alert_type: str, reference: str, message: str):
        key = (module, alert_type, str(reference or "").strip())
        if key in seen_alert_keys:
            return
        seen_alert_keys.add(key)
        system_alerts.append({
            "severity": severity,
            "module": module,
            "alert_type": alert_type,
            "reference": reference,
            "message": message,
        })

    for e in evals:
        if e.get("evaluation_status") == "FAILED":
            _add_alert(
                "HIGH",
                "Property Evaluations",
                "EVALUATION_FAILED",
                e["evaluation_id"],
                e.get("failure_reason", "Evaluation failed."),
            )
        elif e.get("flagged_suspicious"):
            _add_alert(
                "MEDIUM",
                "Property Evaluations",
                "FLAGGED_SUSPICIOUS",
                e["evaluation_id"],
                e.get("flag_reason", "Flagged suspicious valuation."),
            )
    for d in docs:
        if d.get("cross_document_mismatch_detected"):
            ref_id = d.get("job_id") or d.get("property_reference")
            _add_alert(
                "HIGH",
                "Document Analyzer",
                "CROSS_DOC_MISMATCH",
                ref_id,
                f"Cross-document mismatch detected on {d.get('property_reference', ref_id)}.",
            )
    for fj in failed_jobs:
        _add_alert(
            "HIGH",
            "System Health",
            "BACKGROUND_JOB_FAILED",
            fj.get("job_id") or fj.get("name") or "bg-job",
            fj.get("error") or fj.get("message") or "Background job failed.",
        )

    recent_activities = sorted(audits, key=lambda x: x.get("timestamp", ""), reverse=True)[:8]
    recent_evaluations = sorted(evals, key=lambda x: x.get("evaluation_date", ""), reverse=True)[:5]

    payload = {
        "adapter_mode": db_instance.adapter_mode,
        "database_architecture": {
            "primary_store": "SQLite (smart_land_eval.db)",
            "secondary_document_store": "JSON local store synced selectively to SQLite Document/DocumentExtraction/VerificationItem tables",
            "sync_note": "Active operational records run on local SQLite + runtime caches rather than an external MongoDB cluster.",
        },
        "kpis": {
            "total_users": total_users,
            "active_users": active_users,
            "total_property_evaluations": total_evaluations,
            "evaluations_today": evaluations_today,
            "total_document_analyses": total_doc_analyses,
            "reports_generated": reports_generated,
            "pending_support_tickets": pending_support_tickets,
            "open_high_priority_tickets": open_high_priority_tickets,
            "dataset_records": latest_dataset_records,
            "current_production_model": prod_model_version,
            "gis_service_availability_pct": gis_availability_pct,
            "failed_api_requests_24h": failed_api_requests
        },
        "charts": {
            "evaluations_over_time": evaluations_over_time,
            "taluk_wise_distribution": taluk_distribution,
            "property_type_distribution": property_type_distribution,
            "user_registration_trends": user_registration_trends,
            "document_analysis_status": document_analysis_status,
            "gis_retrieval_breakdown": gis_retrieval_rates,
            "ml_model_performance_history": model_performance_history
        },
        "recent_activities": recent_activities,
        "recent_evaluations": recent_evaluations,
        "system_alerts": system_alerts,
        "failed_background_jobs": failed_jobs
    }
    with _CACHE_LOCK:
        _METRICS_CACHE["ts"] = time.monotonic()
        _METRICS_CACHE["payload"] = payload
    return jsonify(payload), 200
