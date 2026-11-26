"""
Smart Land Valuation & Geospatial Analysis System — Modular Admin Portal Package.
Registers all 11 administrative blueprints onto the Flask application.
"""
from .compat_flask import Flask
from .auth.routes import auth_bp
from .overview.routes import overview_bp
from .users.routes import users_bp
from .evaluations.routes import evaluations_bp
from .datasets.routes import datasets_bp
from .models.routes import models_bp
from .gis.routes import gis_bp
from .documents.routes import documents_bp
from .reports.routes import reports_bp
from .monitoring.routes import monitoring_bp
from .audit.routes import audit_bp
from .settings.routes import settings_bp
from .support.routes import support_bp

def register_admin_portal_blueprints(app: Flask):
    app.register_blueprint(auth_bp)
    app.register_blueprint(overview_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(evaluations_bp)
    app.register_blueprint(datasets_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(gis_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(support_bp)
    return app

def create_admin_app() -> Flask:
    app = Flask(__name__)
    register_admin_portal_blueprints(app)
    return app
