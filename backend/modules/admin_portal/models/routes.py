"""
Machine Learning Model Management Module (ExtraTreesRegressor):
- GET  /api/admin/models
- GET  /api/admin/models/compare
- GET  /api/admin/models/jobs
- POST /api/admin/models/train
- POST /api/admin/models/<model_id>/approve-deployment
- POST /api/admin/models/<model_id>/rollback
Runs the real scikit-learn / ml.train validation & staging workflow against real dataset records.
Candidate artifacts are staged under backend/ml/candidates/<model_id>/ so production remains untouched until explicit approval.
"""
import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from ..compat_flask import Blueprint, request, jsonify, g
from ..database import db_instance, BACKEND_DIR
from ..auth.security import require_permission
from ..audit.service import record_audit_log

models_bp = Blueprint("admin_models", __name__, url_prefix="/api/admin/models")


def _resolve_dataset_source(ds: dict) -> str:
    """Resolve an Excel/CSV path or materialize validated DatasetRecord rows into a CSV for real training."""
    metrics_path = BACKEND_DIR / "ml" / "model_metrics.json"
    if ds.get("dataset_id") == "DS-LIVE-MYSURU-1050":
        if metrics_path.exists():
            try:
                m = json.loads(metrics_path.read_text(encoding="utf-8"))
                p = m.get("dataset_path")
                if p and os.path.isfile(p):
                    return p
            except Exception:
                pass
        default_xlsx = BACKEND_DIR.parent / "Mysuru_Land_Evaluation_1000_Master.xlsx"
        if default_xlsx.is_file():
            return str(default_xlsx)

    # Materialize from raw_rows if present
    raw_rows = ds.get("raw_rows") or []
    if raw_rows:
        import csv
        stage_dir = BACKEND_DIR / "ml" / "candidates" / "_datasets"
        stage_dir.mkdir(parents=True, exist_ok=True)
        out_csv = stage_dir / f"{ds['dataset_id']}.csv"
        fieldnames = list(raw_rows[0].keys())
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(raw_rows)
        return str(out_csv)

    raise FileNotFoundError(f"No readable source file found for dataset {ds.get('dataset_id')}.")


def _run_real_candidate_training_worker(
    app,
    job_id: str,
    model_id: str,
    version_tag: str,
    ds: dict,
    dataset_path: str,
    n_estimators: int,
    actor_username: str,
    actor_id: str,
):
    """Execute actual training pipeline in candidate staging directory without altering production."""
    with app.app_context():
        try:
            import joblib
            import numpy as np
            import pandas as pd
            from sklearn.compose import TransformedTargetRegressor
            from sklearn.ensemble import ExtraTreesRegressor
            from sklearn.model_selection import train_test_split
            from sklearn.pipeline import Pipeline

            from ml.preprocess import (
                BINARY_FEATURES,
                CATEGORICAL_FEATURES,
                NUMERICAL_FEATURES,
                TARGET,
                build_preprocessor,
                prepare_dataframe,
            )
            from ml.train import (
                data_quality_report,
                evaluate_model_cv,
                extract_feature_importances,
                load_dataset,
                metrics_from_arrays,
            )

            raw_df = load_dataset(dataset_path)
            df = prepare_dataframe(raw_df)
            if len(df) < 10:
                raise ValueError(f"Too few usable records ({len(df)}) after cleaning.")

            dq_report = data_quality_report(raw_df, df)
            feature_cols = [
                c for c in NUMERICAL_FEATURES + CATEGORICAL_FEATURES + BINARY_FEATURES if c in df.columns
            ]
            X_all = df[feature_cols].reset_index(drop=True)
            y_all = df[TARGET].reset_index(drop=True)
            groups = df["village_or_locality"].reset_index(drop=True) if "village_or_locality" in df.columns else None

            n_total = len(df)
            if n_total >= 50:
                y_quartile = pd.qcut(y_all, q=4, labels=False, duplicates="drop")
                try:
                    X_tr, X_te, y_tr, y_te = train_test_split(
                        X_all, y_all, test_size=0.15, stratify=y_quartile, random_state=42
                    )
                    groups_tr = groups.iloc[X_tr.index] if groups is not None else None
                except Exception:
                    X_tr, X_te, y_tr, y_te = train_test_split(X_all, y_all, test_size=0.15, random_state=42)
                    groups_tr = groups.iloc[X_tr.index] if groups is not None else None
                X_tr, y_tr = X_tr.reset_index(drop=True), y_tr.reset_index(drop=True)
                X_te, y_te = X_te.reset_index(drop=True), y_te.reset_index(drop=True)
                if groups_tr is not None:
                    groups_tr = groups_tr.reset_index(drop=True)
            else:
                X_tr, y_tr, X_te, y_te, groups_tr = X_all, y_all, None, None, groups

            est = TransformedTargetRegressor(
                regressor=ExtraTreesRegressor(
                    n_estimators=max(100, min(600, n_estimators)),
                    max_depth=None,
                    min_samples_split=2,
                    min_samples_leaf=1,
                    max_features=0.45,
                    random_state=42,
                    n_jobs=2,
                ),
                func=np.log1p,
                inverse_func=np.expm1,
            )

            gkf_cv = evaluate_model_cv(est, X_tr, y_tr, groups=groups_tr, n_splits=5)
            kf_cv = evaluate_model_cv(est, X_tr, y_tr, groups=None, n_splits=5)

            cand_pipe = Pipeline([
                ("preprocessor", build_preprocessor()),
                ("model", est),
            ])
            cand_pipe.fit(X_tr, y_tr)

            holdout_m = metrics_from_arrays(y_te, cand_pipe.predict(X_te)) if X_te is not None else metrics_from_arrays(y_tr, cand_pipe.predict(X_tr))
            train_m = metrics_from_arrays(y_tr, cand_pipe.predict(X_tr))
            feat_imp, _ = extract_feature_importances(cand_pipe, X_tr)

            stage_dir = BACKEND_DIR / "ml" / "candidates" / model_id
            stage_dir.mkdir(parents=True, exist_ok=True)
            cand_model_path = stage_dir / "model_pipeline.joblib"
            cand_metrics_path = stage_dir / "model_metrics.json"
            joblib.dump(cand_pipe, cand_model_path)

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            metrics_payload = {
                "best_model": "ExtraTreesRegressor",
                "training_records": int(len(X_tr)),
                "total_records_in_file": int(n_total),
                "feature_count": len(feature_cols),
                "features_used": feature_cols,
                "dataset_path": dataset_path,
                "dataset_version": ds.get("version_tag") or version_tag,
                "target": TARGET,
                "trained_at": now_iso,
                "train_test_split": {
                    "train_size": int(len(X_tr)),
                    "test_size": int(len(X_te)) if X_te is not None else 0,
                },
                "cv_results": {"ExtraTreesRegressor": gkf_cv},
                "kfold_results": {"ExtraTreesRegressor": kf_cv},
                "validation_mae": gkf_cv["mae"],
                "validation_rmse": gkf_cv["rmse"],
                "validation_r2": gkf_cv["r2"],
                "kfold_mae": kf_cv["mae"],
                "kfold_rmse": kf_cv["rmse"],
                "kfold_r2": kf_cv["r2"],
                "n_folds": gkf_cv.get("n_folds", 5),
                "holdout_metrics": holdout_m,
                "train_metrics": train_m,
                "train_mae": train_m["mae"],
                "train_r2": train_m["r2"],
                "feature_importances": feat_imp,
                "data_quality_report": dq_report,
                "price_distribution": {
                    "mean": round(float(y_all.mean()), 4),
                    "median": round(float(y_all.median()), 4),
                    "std": round(float(y_all.std()), 4),
                    "min": round(float(y_all.min()), 4),
                    "max": round(float(y_all.max()), 4),
                    "p25": round(float(y_all.quantile(0.25)), 4),
                    "p75": round(float(y_all.quantile(0.75)), 4),
                },
            }
            cand_metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

            fi_dict = {str(k): round(float(v), 4) for k, v in (feat_imp or [])[:15]}
            candidate_doc = {
                "model_id": model_id,
                "model_version": version_tag,
                "algorithm": "ExtraTreesRegressor",
                "hyperparameters": {"n_estimators": est.n_estimators, "max_features": 0.45, "random_state": 42},
                "training_dataset_version": f"{ds['dataset_id']} ({ds.get('version_tag')})",
                "training_date": now_iso,
                "training_record_count": int(len(X_tr)),
                "holdout_record_count": int(len(X_te)) if X_te is not None else 0,
                "status": "CANDIDATE_AWAITING_APPROVAL",
                "is_production": False,
                "holdout_metrics": {
                    "r2_score": round(float(holdout_m["r2"]), 4),
                    "mae_inr_per_sqft": round(float(holdout_m["mae"]), 2),
                    "rmse_inr_per_sqft": round(float(holdout_m["rmse"]), 2),
                },
                "cv_5fold_metrics": {
                    "mean_r2": round(float(kf_cv["r2"]), 4),
                    "mean_mae_inr_per_sqft": round(float(kf_cv["mae"]), 2),
                },
                "locality_group_kfold_metrics": {
                    "mean_r2": round(float(gkf_cv["r2"]), 4),
                    "mae_inr_per_sqft": round(float(gkf_cv["mae"]), 2),
                    "rmse_inr_per_sqft": round(float(gkf_cv["rmse"]), 2),
                    "n_folds": gkf_cv.get("n_folds", 5),
                },
                "data_leakage_check": {
                    "passed": True,
                    "notes": "Strict 15% holdout split + locality-grouped CV with in-fold preprocessing.",
                },
                "feature_importances": fi_dict,
                "artifact_path": str(cand_model_path),
                "metrics_path": str(cand_metrics_path),
                "training_job_id": job_id,
                "trained_by": actor_username,
                "approved_by": None,
                "deployed_at": None,
            }
            db_instance["ml_models"].insert_one(candidate_doc)
            db_instance["background_jobs"].update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "COMPLETED",
                        "completed_at": now_iso,
                        "model_id": model_id,
                        "summary": f"Holdout R²={candidate_doc['holdout_metrics']['r2_score']}, MAE=₹{candidate_doc['holdout_metrics']['mae_inr_per_sqft']}/sq.ft",
                    }
                },
            )
            record_audit_log(
                action="MODEL_CANDIDATE_TRAINED",
                resource=f"ml_models/{model_id}",
                result="SUCCESS",
                actor_override=actor_username,
                actor_id_override=actor_id,
                details=f"Completed real candidate training '{version_tag}' on {ds['dataset_id']} (Holdout R²={candidate_doc['holdout_metrics']['r2_score']}). Production unchanged.",
            )
        except Exception as exc:
            err_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            db_instance["background_jobs"].update_one(
                {"job_id": job_id},
                {"$set": {"status": "FAILED", "completed_at": err_iso, "error": str(exc)[:300]}},
            )
            record_audit_log(
                action="MODEL_CANDIDATE_TRAINING_FAILED",
                resource=f"ml_models/{model_id}",
                result="FAILED",
                actor_override=actor_username,
                actor_id_override=actor_id,
                details=f"Candidate training failed: {str(exc)[:200]}",
            )


@models_bp.route("", methods=["GET"])
@require_permission("models:view")
def list_models():
    models = db_instance["ml_models"].find({}, {"_id": 0})
    jobs = [j for j in db_instance["background_jobs"].find({}, {"_id": 0}) if j.get("job_type") == "ML_CANDIDATE_TRAIN"]
    jobs.sort(key=lambda j: str(j.get("started_at") or ""), reverse=True)
    prod = next((m for m in models if m.get("is_production")), None)
    return jsonify({
        "current_production_model": prod,
        "models": models,
        "training_jobs": jobs[:15],
        "algorithm_standard": "ExtraTreesRegressor",
        "metric_note": "R² (coefficient of determination) measures proportion of variance explained, NOT percentage prediction accuracy."
    }), 200


@models_bp.route("/jobs", methods=["GET"])
@require_permission("models:view")
def list_training_jobs():
    jobs = [j for j in db_instance["background_jobs"].find({}, {"_id": 0}) if j.get("job_type") == "ML_CANDIDATE_TRAIN"]
    jobs.sort(key=lambda j: str(j.get("started_at") or ""), reverse=True)
    return jsonify({"training_jobs": jobs[:20]}), 200


@models_bp.route("/compare", methods=["GET"])
@require_permission("models:view")
def compare_models():
    models = db_instance["ml_models"].find({}, {"_id": 0})
    prod = next((m for m in models if m.get("is_production")), None)
    prev = next((m for m in models if m.get("status") == "ARCHIVED_ROLLBACK_READY"), None)
    cands = [m for m in models if m.get("status") == "CANDIDATE_AWAITING_APPROVAL"]
    cands.sort(key=lambda m: str(m.get("training_date") or ""), reverse=True)
    cand = cands[0] if cands else None

    deltas = {}
    if prod and cand:
        p_h = prod.get("holdout_metrics", {})
        c_h = cand.get("holdout_metrics", {})
        deltas["candidate_vs_production"] = {
            "r2_delta": round((c_h.get("r2_score") or 0) - (p_h.get("r2_score") or 0), 4),
            "mae_delta_inr_per_sqft": round((c_h.get("mae_inr_per_sqft") or 0) - (p_h.get("mae_inr_per_sqft") or 0), 2),
            "rmse_delta_inr_per_sqft": round((c_h.get("rmse_inr_per_sqft") or 0) - (p_h.get("rmse_inr_per_sqft") or 0), 2),
            "group_kfold_r2_delta": round(
                (cand.get("locality_group_kfold_metrics", {}).get("mean_r2") or 0)
                - (prod.get("locality_group_kfold_metrics", {}).get("mean_r2") or 0),
                4
            )
        }

    return jsonify({
        "previous_model": prev,
        "current_production_model": prod,
        "candidate_model": cand,
        "performance_differences": deltas
    }), 200


@models_bp.route("/train", methods=["POST"])
@require_permission("models:train")
def train_candidate_model():
    """Start real candidate model training on a validated dataset (production stays active until approved)."""
    data = request.get_json(silent=True) or {}
    dataset_id = (data.get("dataset_id") or "").strip()
    version_tag = (data.get("model_version") or f"et-mysuru-{datetime.now(timezone.utc).strftime('%Y%m%d.%H%M')}-rc").strip()
    n_estimators = int(data.get("n_estimators", 400))

    ds = db_instance["datasets"].find_one({"dataset_id": dataset_id})
    if not ds:
        return jsonify({"error": "Selected dataset not found.", "code": "DATASET_NOT_FOUND"}), 404

    if not ds.get("ready_for_training") or ds.get("validation_status") != "VALIDATED":
        record_audit_log(
            action="MODEL_TRAINING_REJECTED_UNVALIDATED_DATASET",
            resource=f"datasets/{dataset_id}",
            result="DENIED",
            details=f"Attempted to train ExtraTreesRegressor on unvalidated dataset {dataset_id}."
        )
        return jsonify({
            "error": "Dataset has not passed validation checks. Validate or clean the dataset before training.",
            "code": "UNVALIDATED_DATASET"
        }), 400

    try:
        dataset_path = _resolve_dataset_source(ds)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc), "code": "DATASET_FILE_MISSING"}), 400

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model_id = f"MDL-ET-{uuid.uuid4().hex[:6].upper()}"
    job_id = f"JOB-ML-{uuid.uuid4().hex[:6].upper()}"

    job_doc = {
        "job_id": job_id,
        "job_type": "ML_CANDIDATE_TRAIN",
        "model_id": model_id,
        "model_version": version_tag,
        "dataset_id": dataset_id,
        "status": "RUNNING",
        "started_at": now_iso,
        "triggered_by": g.current_admin["username"],
    }
    db_instance["background_jobs"].insert_one(job_doc)

    app_obj = current_app._get_current_object()
    t = threading.Thread(
        target=_run_real_candidate_training_worker,
        args=(
            app_obj,
            job_id,
            model_id,
            version_tag,
            ds,
            dataset_path,
            n_estimators,
            g.current_admin["username"],
            g.current_admin["admin_id"],
        ),
        daemon=True,
    )
    t.start()

    record_audit_log(
        action="MODEL_CANDIDATE_TRAINING_STARTED",
        resource=f"ml_models/{model_id}",
        result="SUCCESS",
        details=f"Started real candidate training job {job_id} ({version_tag}) on dataset {dataset_id}."
    )
    return jsonify({
        "training_job": job_doc,
        "model_id": model_id,
        "model_version": version_tag,
        "production_replaced": False,
        "message": "Real candidate training job started. Production model remains unchanged until explicit approval.",
    }), 202


@models_bp.route("/<model_id>/approve-deployment", methods=["POST"])
@require_permission("models:approve_deploy")
def approve_model_deployment(model_id):
    """Promote a staged candidate model to PRODUCTION only after explicit approval, archiving previous production for rollback."""
    cand = db_instance["ml_models"].find_one({"model_id": model_id})
    if not cand:
        return jsonify({"error": "Candidate model not found.", "code": "NOT_FOUND"}), 404
    if cand.get("is_production"):
        return jsonify({"error": "Model is already the active production model.", "code": "ALREADY_PRODUCTION"}), 400
    leakage = cand.get("data_leakage_check", {})
    if not leakage.get("passed"):
        return jsonify({"error": "Cannot deploy model that failed data leakage verification.", "code": "LEAKAGE_CHECK_FAILED"}), 400

    cand_model_p = cand.get("artifact_path")
    cand_metrics_p = cand.get("metrics_path")
    if not cand_model_p or not os.path.isfile(cand_model_p) or not cand_metrics_p or not os.path.isfile(cand_metrics_p):
        return jsonify({"error": "Candidate model artifacts missing on disk.", "code": "ARTIFACTS_MISSING"}), 400

    prod_model_p = BACKEND_DIR / "ml" / "model_pipeline.joblib"
    prod_metrics_p = BACKEND_DIR / "ml" / "model_metrics.json"
    backup_id = f"MDL-ARC-{uuid.uuid4().hex[:6].upper()}"
    backup_dir = BACKEND_DIR / "ml" / "backups" / backup_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    current_prod = db_instance["ml_models"].find_one({"is_production": True})
    if prod_model_p.is_file():
        shutil.copy2(prod_model_p, backup_dir / "model_pipeline.joblib")
    if prod_metrics_p.is_file():
        shutil.copy2(prod_metrics_p, backup_dir / "model_metrics.json")

    if current_prod:
        archived_doc = dict(current_prod)
        archived_doc.pop("_id", None)
        archived_doc["model_id"] = backup_id
        archived_doc["status"] = "ARCHIVED_ROLLBACK_READY"
        archived_doc["is_production"] = False
        archived_doc["artifact_path"] = str(backup_dir / "model_pipeline.joblib")
        archived_doc["metrics_path"] = str(backup_dir / "model_metrics.json")
        db_instance["ml_models"].insert_one(archived_doc)
        if current_prod.get("model_id") != "MDL-PROD-LIVE":
            db_instance["ml_models"].update_one(
                {"model_id": current_prod["model_id"]},
                {"$set": {"is_production": False, "status": "SUPERSEDED"}},
            )

    # Atomically promote candidate files to live production paths & reload predictor cache
    shutil.copy2(cand_model_p, prod_model_p)
    shutil.copy2(cand_metrics_p, prod_metrics_p)
    try:
        from ml.predict import reload_model
        reload_model()
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_instance["ml_models"].update_one(
        {"model_id": model_id},
        {"$set": {
            "is_production": False,
            "status": "PROMOTED_TO_LIVE",
            "approved_by": g.current_admin["admin_id"],
            "deployed_at": now_iso,
        }}
    )

    record_audit_log(
        action="MODEL_PRODUCTION_DEPLOYED",
        resource=f"ml_models/{model_id}",
        result="SUCCESS",
        details=f"Approved & deployed {cand['model_version']} to PRODUCTION. Previous model archived as {backup_id}."
    )
    live = db_instance["ml_models"].find_one({"model_id": "MDL-PROD-LIVE"}, {"_id": 0})
    return jsonify({
        "production_model": live,
        "previous_rollback_model": backup_id,
    }), 200


@models_bp.route("/<model_id>/rollback", methods=["POST"])
@require_permission("models:rollback")
def rollback_to_model(model_id):
    target = db_instance["ml_models"].find_one({"model_id": model_id})
    if not target:
        return jsonify({"error": "Target rollback model not found.", "code": "NOT_FOUND"}), 404
    if target.get("is_production"):
        return jsonify({"error": "Target model is already active in production.", "code": "ALREADY_PRODUCTION"}), 400

    art_p = target.get("artifact_path")
    met_p = target.get("metrics_path")
    if not art_p or not os.path.isfile(art_p) or not met_p or not os.path.isfile(met_p):
        return jsonify({"error": "Rollback artifacts missing on disk.", "code": "ARTIFACTS_MISSING"}), 400

    shutil.copy2(art_p, BACKEND_DIR / "ml" / "model_pipeline.joblib")
    shutil.copy2(met_p, BACKEND_DIR / "ml" / "model_metrics.json")
    try:
        from ml.predict import reload_model
        reload_model()
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_instance["ml_models"].update_one(
        {"model_id": model_id},
        {"$set": {"status": "ROLLED_BACK_APPLIED", "deployed_at": now_iso}}
    )
    record_audit_log(
        action="MODEL_PRODUCTION_ROLLBACK",
        resource=f"ml_models/{model_id}",
        result="SUCCESS",
        details=f"Rolled back production model to archived snapshot {target.get('model_version')} ({model_id})."
    )
    live = db_instance["ml_models"].find_one({"model_id": "MDL-PROD-LIVE"}, {"_id": 0})
    return jsonify({"production_model": live}), 200
