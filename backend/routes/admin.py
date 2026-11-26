"""
Admin API routes for site weightages and backward-compatible RBAC admin login.
Protected by Admin Portal RBAC permissions and append-only audit logging.
"""
from flask import Blueprint, g, jsonify, request
from models import WeightageVersion, db
from modules.admin_portal.audit.service import record_audit_log
from modules.admin_portal.auth.routes import login as rbac_admin_login
from modules.admin_portal.auth.security import require_permission
from modules.admin_portal.database import db_instance

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.route("/login", methods=["POST"])
def login():
    """Delegates cleanly to signed-JWT RBAC authentication (/api/admin/auth/login)."""
    return rbac_admin_login()


@admin_bp.route("/weightage", methods=["GET"])
@require_permission("settings:view")
def get_weightage():
    active = WeightageVersion.query.filter_by(is_active=True).first()
    versions = WeightageVersion.query.order_by(WeightageVersion.version.desc()).all()
    return jsonify({
        "active": active.to_dict() if active else None,
        "history": [v.to_dict() for v in versions],
    }), 200


@admin_bp.route("/weightage", methods=["POST"])
@require_permission("settings:manage")
def update_weightage():
    data = request.get_json(silent=True) or {}
    try:
        price_w = float(data["price_weight"])
        loc_w = float(data["location_weight"])
        fac_w = float(data["facility_weight"])
        env_w = float(data["environment_weight"])
        inf_w = float(data["infrastructure_weight"])
        util_w = float(data["utility_weight"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Invalid or missing weightage fields"}), 400

    if any(w < 0 or w > 100 for w in (price_w, loc_w, fac_w, env_w, inf_w, util_w)):
        return jsonify({"error": "All weights must be between 0 and 100."}), 400

    total = price_w + loc_w + fac_w + env_w + inf_w + util_w
    if abs(total - 100.0) > 0.01:
        return jsonify({"error": f"Weights must sum to 100%. Current sum is {total}%"}), 400

    WeightageVersion.query.update({WeightageVersion.is_active: False})
    latest = WeightageVersion.query.order_by(WeightageVersion.version.desc()).first()
    new_ver = (latest.version + 1) if latest else 1

    actor = g.current_admin.get("username") if getattr(g, "current_admin", None) else "admin"
    wv = WeightageVersion(
        version=new_ver,
        price_weight=price_w,
        location_weight=loc_w,
        facility_weight=fac_w,
        environment_weight=env_w,
        infrastructure_weight=inf_w,
        utility_weight=util_w,
        is_active=True,
        created_by=actor,
    )
    db.session.add(wv)
    db.session.commit()

    # Keep global settings in sync and emit immutable audit log
    db_instance["system_settings"].update_one(
        {"settings_id": "SYS-SET-MYSURU-01"},
        {"$set": {"scoring_weightages": wv.to_dict(), "updated_by": actor}},
        upsert=True,
    )
    record_audit_log(
        action="WEIGHTAGE_UPDATED",
        resource=f"weightage_versions/v{new_ver}",
        result="SUCCESS",
        details=wv.to_dict(),
    )
    return jsonify(wv.to_dict()), 201
