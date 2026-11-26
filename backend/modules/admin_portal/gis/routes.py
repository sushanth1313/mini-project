"""
GIS and Geospatial Monitoring Module:
- GET   /api/admin/gis/overview
- GET   /api/admin/gis/logs
- POST  /api/admin/gis/cache/clear
- PATCH /api/admin/gis/config
Monitors OpenStreetMap Overpass API, Nominatim geocoding/reverse geocoding,
13 facility categories, 7 Mysuru taluks, and enforces strict 4-tier statuses:
SUCCESS, NO_DATA, PARTIAL, SOURCE_UNAVAILABLE (never converts API failure into empty success).
"""
from datetime import datetime, timezone
from ..compat_flask import Blueprint, request, jsonify
from ..config import GIS_FACILITY_CATEGORIES, MYSURU_TALUKS
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

gis_bp = Blueprint("admin_gis", __name__, url_prefix="/api/admin/gis")

VALID_GIS_STATUSES = {"SUCCESS", "NO_DATA", "PARTIAL", "SOURCE_UNAVAILABLE"}

@gis_bp.route("/overview", methods=["GET"])
@require_permission("gis:view")
def get_gis_overview():
    endpoints = db_instance["gis_endpoints"].find({}, {"_id": 0})
    cfg = db_instance["gis_config"].find_one({"config_id": "GIS-CFG-MYSURU"}, {"_id": 0})
    logs = db_instance["gis_logs"].find({}, {"_id": 0})
    failed_queries = [l for l in logs if l.get("status") in ("SOURCE_UNAVAILABLE", "PARTIAL")]
    try:
        from gis.adapters.google import get_google_maps_status
        g_status = get_google_maps_status()
    except Exception:
        g_status = {"api_key_configured": False, "enabled": False}

    return jsonify({
        "endpoints": endpoints,
        "configuration": cfg,
        "google_maps_status": g_status,
        "facility_categories": GIS_FACILITY_CATEGORIES,
        "supported_taluks": MYSURU_TALUKS,
        "status_definitions": {
            "SUCCESS": "Retrieval completed and results were found.",
            "NO_DATA": "Retrieval completed successfully but no matching mapped feature was found.",
            "PARTIAL": "Retrieval completeness is uncertain.",
            "SOURCE_UNAVAILABLE": "The external service failed or was unavailable."
        },
        "failed_or_partial_queries": failed_queries
    }), 200

@gis_bp.route("/logs", methods=["GET"])
@require_permission("gis:view")
def get_gis_logs():
    status_q = (request.args.get("status") or "").strip().upper()
    taluk_q = (request.args.get("taluk") or "").strip()

    logs = db_instance["gis_logs"].find({}, {"_id": 0})
    filtered = []
    for l in logs:
        if status_q and l.get("status") != status_q:
            continue
        if taluk_q and l.get("taluk") != taluk_q:
            continue
        filtered.append(l)

    filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify({"logs": filtered, "total": len(filtered)}), 200

@gis_bp.route("/cache/clear", methods=["POST"])
@require_permission("gis:manage_cache")
def clear_gis_cache():
    cfg = db_instance["gis_config"].find_one({"config_id": "GIS-CFG-MYSURU"})
    prev_entries = cfg.get("cached_entries_count", 0) if cfg else 0
    memory_purged = 0
    try:
        from gis.adapters.osm import GIS_CACHE, GIS_STATUS_CACHE
        from gis.adapters.arcgis import ARCGIS_CACHE
        from gis.service import LOCATION_SEARCH_CACHE, REVERSE_GEOCODE_CACHE
        for cache_obj in (GIS_CACHE, GIS_STATUS_CACHE, ARCGIS_CACHE, LOCATION_SEARCH_CACHE, REVERSE_GEOCODE_CACHE):
            if hasattr(cache_obj, "clear"):
                memory_purged += len(cache_obj) if hasattr(cache_obj, "__len__") else 0
                cache_obj.clear()
    except Exception:
        pass

    purged_total = max(prev_entries, memory_purged)
    db_instance["gis_config"].update_one(
        {"config_id": "GIS-CFG-MYSURU"},
        {"$set": {
            "cached_entries_count": 0,
            "last_cache_purged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }}
    )
    record_audit_log(
        action="GIS_CACHE_PURGED",
        resource="gis_config/GIS-CFG-MYSURU",
        result="SUCCESS",
        details=f"Purged {purged_total} cached GIS entries (OSM, ArcGIS, Nominatim search & reverse geocode caches)."
    )
    updated = db_instance["gis_config"].find_one({"config_id": "GIS-CFG-MYSURU"}, {"_id": 0})
    return jsonify({
        "message": f"Cleared {purged_total} cached GIS entries across OSM, ArcGIS, and Nominatim caches.",
        "purged_in_memory": memory_purged,
        "configuration": updated,
    }), 200

@gis_bp.route("/config", methods=["PATCH"])
@require_permission("gis:configure")
def update_gis_configuration():
    data = request.get_json(silent=True) or {}
    updates = {}

    if "search_radius_meters" in data:
        radius = int(data["search_radius_meters"])
        if radius < 500 or radius > 10000:
            return jsonify({"error": "search_radius_meters must be between 500 and 10000 meters.", "code": "VALIDATION_ERROR"}), 400
        updates["search_radius_meters"] = radius

    if "api_timeout_seconds" in data:
        timeout = int(data["api_timeout_seconds"])
        if timeout < 3 or timeout > 60:
            return jsonify({"error": "api_timeout_seconds must be between 3 and 60 seconds.", "code": "VALIDATION_ERROR"}), 400
        updates["api_timeout_seconds"] = timeout

    if "permitted_fallback_endpoints" in data:
        fallbacks = data["permitted_fallback_endpoints"]
        if not isinstance(fallbacks, list) or not all(str(u).startswith("https://") for u in fallbacks):
            return jsonify({"error": "permitted_fallback_endpoints must be a list of https:// URLs.", "code": "VALIDATION_ERROR"}), 400
        updates["permitted_fallback_endpoints"] = fallbacks

    if "google_maps_enabled" in data:
        g_enabled = bool(data["google_maps_enabled"])
        updates["google_maps_enabled"] = g_enabled
        try:
            from gis.adapters.google import set_google_maps_enabled
            set_google_maps_enabled(g_enabled)
        except Exception:
            pass

    if not updates:
        return jsonify({"error": "No valid GIS configuration parameters provided.", "code": "VALIDATION_ERROR"}), 400

    db_instance["gis_config"].update_one({"config_id": "GIS-CFG-MYSURU"}, {"$set": updates})
    record_audit_log(
        action="GIS_CONFIGURATION_UPDATED",
        resource="gis_config/GIS-CFG-MYSURU",
        result="SUCCESS",
        details=f"Updated GIS settings: {updates}"
    )
    updated = db_instance["gis_config"].find_one({"config_id": "GIS-CFG-MYSURU"}, {"_id": 0})
    return jsonify({"configuration": updated}), 200
