"""
Model metrics and info routes.
"""
from flask import Blueprint, jsonify
from ml.lightweight import get_model_metrics

model_bp = Blueprint("model", __name__, url_prefix="/api/model")


@model_bp.route("/metrics", methods=["GET"])
def model_metrics():
    metrics = get_model_metrics()
    return jsonify(metrics)


@model_bp.route("/reload", methods=["POST"])
def reload_model():
    """Force reload the model from disk (after retraining)."""
    try:
        from ml.predict import reload_model as _reload
        _reload()
        return jsonify({"message": "Model reloaded successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
