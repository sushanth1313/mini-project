"""
Smart Land Evaluation — Flask Backend
Entry point: python app.py
"""
import os
import sys
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from config import config
from models import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Ensure upload/report folders exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["REPORTS_FOLDER"], exist_ok=True)

    # Allow multi-PDF due-diligence packets cleanly up to 30 MB while individual legacy uploads validate 10 MB
    app.config["MAX_CONTENT_LENGTH"] = max(int(app.config.get("MAX_CONTENT_LENGTH") or 0), 30 * 1024 * 1024)

    # CORS
    origins = [o.strip() for o in app.config.get("CORS_ORIGINS", "").split(",") if o.strip()]
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": origins or "*",
                "allow_headers": ["Content-Type", "Authorization", "X-Client-Role", "X-User-Role"],
                "expose_headers": ["Content-Disposition"],
            }
        },
    )

    # Database
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _ensure_schema_migrations()
        _seed_data_sources()
        _seed_admin()
        _seed_weightage()
        from modules.admin_portal.database import seed_admin_and_platform_defaults
        seed_admin_and_platform_defaults()

    # Register core blueprints
    from routes.properties import properties_bp
    from routes.evaluate import evaluate_bp
    from routes.documents import documents_bp
    from routes.reports import reports_bp
    from routes.model import model_bp
    from routes.datasources import datasources_bp
    from routes.admin import admin_bp
    from routes.customer import customer_bp

    app.register_blueprint(properties_bp)
    app.register_blueprint(evaluate_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(model_bp)
    app.register_blueprint(datasources_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_bp)

    # Register integrated AI Document Analyzer & RBAC Admin Portal + User Auth blueprints
    from modules.land_document_analyzer.backend.app import document_analysis_bp
    from modules.admin_portal import register_admin_portal_blueprints
    from modules.admin_portal.auth_users import user_auth_bp

    app.register_blueprint(document_analysis_bp)
    app.register_blueprint(user_auth_bp)
    register_admin_portal_blueprints(app)

    # Health check
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "Smart Land Evaluation API"})

    # Global error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        log.error(f"Internal error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "File too large. Maximum size is 10MB."}), 413

    return app


def _ensure_schema_migrations():
    """Non-destructive column additions so existing SQLite/PostgreSQL property records are preserved."""
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(db.engine)
    alters = [
        ("properties", "entered_locality", "VARCHAR(200)"),
        ("properties", "entered_taluk", "VARCHAR(100)"),
        ("properties", "user_id", "INTEGER"),
        ("property_evaluations", "location_audit", "TEXT"),
        ("property_evaluations", "market_comparison", "TEXT"),
        ("admin_accounts", "status", "VARCHAR(30) DEFAULT 'ACTIVE'"),
    ]
    for table, col, col_type in alters:
        try:
            cols = [c["name"] for c in inspector.get_columns(table)]
            if col not in cols:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                db.session.commit()
                log.info(f"Migrated {table}.{col} cleanly.")
        except Exception as e:
            db.session.rollback()
            log.warning(f"Schema check skipped for {table}.{col}: {e}")

    # Non-destructive canonical enum normalization for existing PlatformUser & AdminAccount rows
    try:
        from models import AdminAccount, PlatformUser
        role_map = {
            "user": "STANDARD_USER",
            "buyer": "STANDARD_USER",
            "student": "STANDARD_USER",
            "standard_user": "STANDARD_USER",
            "analyst": "VALUATION_ANALYST",
            "valuation_analyst": "VALUATION_ANALYST",
            "legal_reviewer": "AUTHORIZED_SURVEYOR",
            "surveyor": "AUTHORIZED_SURVEYOR",
            "authorized_surveyor": "AUTHORIZED_SURVEYOR",
        }
        changed = False
        for u in PlatformUser.query.all():
            r_low = (u.role or "user").strip().lower()
            canon_r = role_map.get(r_low)
            if canon_r and u.role != canon_r:
                u.role = canon_r
                changed = True
            st_up = (u.status or "ACTIVE").strip().upper()
            if st_up in ("ACTIVE", "DEACTIVATED", "SUSPENDED") and u.status != st_up:
                u.status = st_up
                changed = True
        for a in AdminAccount.query.all():
            expected_st = "ACTIVE" if a.is_active else (a.status if a.status in ("SUSPENDED", "DEACTIVATED") else "DEACTIVATED")
            if a.status != expected_st:
                a.status = expected_st
                changed = True
        if changed:
            db.session.commit()
            log.info("Normalized legacy user role/status enums non-destructively.")
        from modules.admin_portal.database import consolidate_single_super_admin
        consolidate_single_super_admin("ADM-0002")
    except Exception as e:
        db.session.rollback()
        log.warning(f"Enum normalization skipped: {e}")


def _seed_admin():
    """Ensure base system administrator exists without exposing default credentials in logs."""
    from models import Admin
    from werkzeug.security import generate_password_hash
    if Admin.query.count() == 0:
        default_pw = os.getenv("DEFAULT_SUPER_ADMIN_PASSWORD", "ChangeMeAdmin@2026!")
        db.session.add(Admin(
            username="admin",
            password_hash=generate_password_hash(default_pw)
        ))
        db.session.commit()
        log.info("Base Admin table initialized.")

def _seed_weightage():
    from models import WeightageVersion
    if WeightageVersion.query.count() == 0:
        db.session.add(WeightageVersion(
            version=1,
            price_weight=30.0,
            location_weight=25.0,
            facility_weight=0.0,
            environment_weight=10.0,
            infrastructure_weight=20.0,
            utility_weight=15.0,
            is_active=True,
            created_by="system"
        ))
        db.session.commit()
        log.info("Default weightage seeded (4-factor scoring)")
    else:
        # Upgrade legacy system v1 weightage (facility_weight=15.0) to v2 (facility_weight=0.0)
        legacy_v1 = WeightageVersion.query.filter_by(
            version=1, created_by="system", is_active=True, facility_weight=15.0
        ).first()
        if legacy_v1 and WeightageVersion.query.count() == 1:
            legacy_v1.is_active = False
            db.session.add(WeightageVersion(
                version=2,
                price_weight=30.0,
                location_weight=25.0,
                facility_weight=0.0,
                environment_weight=10.0,
                infrastructure_weight=20.0,
                utility_weight=15.0,
                is_active=True,
                created_by="system"
            ))
            db.session.commit()
            log.info("Upgraded system weightage v1 -> v2 (facility removed from scoring)")

def _seed_data_sources():
    """Seed or upgrade legacy v1 data source metadata rows without wiping custom entries."""
    from models import DataSource
    if DataSource.query.count() > 0:
        legacy_ds = DataSource.query.filter_by(source_name="Mysuru Land Listings Dataset").first()
        if legacy_ds and "76 " in (legacy_ds.description or ""):
            legacy_ds.description = (
                "1,050 curated residential, commercial, industrial, and agricultural land records "
                "across all 7 Mysuru district taluks (892 training / 158 independent holdout test)."
            )
            legacy_ds.confidence = "Moderate-High (1,050 multi-taluk records; sparse in some rural villages)"
        for old_m in DataSource.query.filter(DataSource.source_type == "model").all():
            if "76 " in (old_m.description or "") or "RandomForest" in (old_m.source_name or ""):
                old_m.source_name = "ML Price Model (ExtraTreesRegressor)"
                old_m.description = (
                    "ExtraTreesRegressor pipeline (47 features, GroupKFold R²=0.7791, Holdout R²=0.8511) "
                    "trained on 892 Mysuru land records across 7 taluks. Indicative benchmark only."
                )
                old_m.confidence = "Holdout MAE ₹385.80/sq.ft | Unseen-Locality GroupKFold MAE ₹529.90/sq.ft"
        if not DataSource.query.filter_by(source_name="ArcGIS World Geocoder (Civic Fallback)").first():
            db.session.add(DataSource(
                source_name="ArcGIS World Geocoder (Civic Fallback)",
                source_type="GIS",
                source_url="https://geocode.arcgis.com",
                data_date="Retrieved live at query time",
                description=(
                    "Secondary coordinate-backed POI verification fallback for categories where "
                    "OpenStreetMap has sparse rural coverage (e.g., police stations, bus stops, banks), "
                    "with strict radius and category filtering."
                ),
                confidence="Fallback-verified with strict spatial & type validation",
                status="LIVE_API",
            ))
        db.session.commit()
        return
    sources = [
        DataSource(
            source_name="Mysuru Land Listings Dataset",
            source_type="dataset",
            source_url="https://housing.com/in/buy/mysore/plots-fid/",
            data_date="October 2026",
            description=(
                "1,050 curated residential, commercial, industrial, and agricultural land records "
                "across all 7 Mysuru district taluks (892 training / 158 independent holdout test)."
            ),
            confidence="Moderate-High (1,050 multi-taluk records; sparse in some rural villages)",
            status="ACTIVE",
        ),
        DataSource(
            source_name="OpenStreetMap / Overpass API",
            source_type="GIS",
            source_url="https://overpass-api.de",
            data_date="Retrieved live at query time",
            description=(
                "Primary GIS engine for nearby facilities across 13 categories plus waterbody and park analysis. "
                "Community-contributed data may have gaps in rural areas."
            ),
            confidence="Moderate (community-contributed, multi-source fallback enabled)",
            status="LIVE_API",
        ),
        DataSource(
            source_name="ArcGIS World Geocoder (Civic Fallback)",
            source_type="GIS",
            source_url="https://geocode.arcgis.com",
            data_date="Retrieved live at query time",
            description=(
                "Secondary coordinate-backed POI verification fallback for categories where "
                "OpenStreetMap has sparse rural coverage (e.g., police stations, bus stops, banks), "
                "with strict radius and category filtering."
            ),
            confidence="Fallback-verified with strict spatial & type validation",
            status="LIVE_API",
        ),
        DataSource(
            source_name="Nominatim / OpenStreetMap Geocoding",
            source_type="GIS",
            source_url="https://nominatim.openstreetmap.org",
            data_date="Retrieved live at query time",
            description=(
                "District-bounded geocoding and reverse geocoding across all 7 Mysuru taluks. "
                "Distinguishes locality centroids from manually pinned parcel coordinates."
            ),
            confidence="Locality-level centroid unless GPS/map pin verified",
            status="LIVE_API",
        ),
        DataSource(
            source_name="Karnataka Bhoomi (Land Records)",
            source_type="government",
            source_url="https://landrecords.karnataka.gov.in",
            data_date="N/A — external portal",
            description=(
                "Official Karnataka government land record system. "
                "Must be checked for RTC, Pahani, and ownership verification. "
                "NOT accessed by this platform."
            ),
            confidence="Authoritative (requires direct verification)",
            status="EXTERNAL_REFERENCE",
        ),
        DataSource(
            source_name="Kaveri Online (Property Registration)",
            source_type="government",
            source_url="https://kaverionline.karnataka.gov.in",
            data_date="N/A — external portal",
            description=(
                "Karnataka registration department portal for sale deed and "
                "encumbrance certificate verification. NOT accessed by this platform."
            ),
            confidence="Authoritative (requires direct verification)",
            status="EXTERNAL_REFERENCE",
        ),
        DataSource(
            source_name="ML Price Model (ExtraTreesRegressor)",
            source_type="model",
            source_url=None,
            data_date="Trained 2026",
            description=(
                "ExtraTreesRegressor pipeline (47 features, GroupKFold R²=0.7791, Holdout R²=0.8511) "
                "trained on 892 Mysuru land records across 7 taluks. Indicative benchmark only."
            ),
            confidence="Holdout MAE ₹385.80/sq.ft | Unseen-Locality GroupKFold MAE ₹529.90/sq.ft",
            status="ACTIVE",
        ),
    ]
    for s in sources:
        db.session.add(s)
    db.session.commit()
    log.info("Data sources seeded.")


if __name__ == "__main__":
    env = os.getenv("FLASK_ENV", "development")
    application = create_app(env)
    port = int(os.getenv("PORT", 5000))
    log.info(f"Starting Smart Land Evaluation API on port {port}")
    application.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
else:
    # WSGI entry point for Gunicorn (`gunicorn app:app`)
    app = create_app(os.getenv("FLASK_ENV", "production"))
