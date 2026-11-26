"""
Data sources routes.
"""
from flask import Blueprint, jsonify
from models import db, DataSource

datasources_bp = Blueprint("datasources", __name__, url_prefix="/api/data-sources")


@datasources_bp.route("", methods=["GET"])
def list_data_sources():
    sources = DataSource.query.order_by(DataSource.source_type).all()
    
    from gis.service import check_gis_sources
    live_status = check_gis_sources()
    
    return jsonify({
        "data_sources": [s.to_dict() for s in sources],
        "live_status": live_status
    })
