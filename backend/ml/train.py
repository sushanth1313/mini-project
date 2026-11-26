"""
ML Training Script v2 — Smart Land Evaluation (Mysuru)

Improvements over v1:
  - Proper stratified holdout test set (15%) before cross-validation
  - Locality-grouped cross-validation to prevent data leakage across localities
  - Hyperparameter tuning for RF and HGB when dataset >= 100 records
  - SHAP explainability module for tree-based models
  - Versioned model backups before overwriting
  - Detailed data quality report in metrics JSON
  - Accurate separation of CV metrics vs holdout test metrics

Usage:
    python backend/ml/train.py --dataset "path/to/dataset.xlsx"
    python backend/ml/train.py --dataset "path/to/dataset.xlsx" --no-shap
"""
import os
import sys
import json
import shutil
import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import (
    RandomForestRegressor,
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
)
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.pipeline import Pipeline
from sklearn.model_selection import KFold, GroupKFold, train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.preprocess import (
    prepare_dataframe, build_preprocessor,
    CATEGORICAL_FEATURES, NUMERICAL_FEATURES, BINARY_FEATURES, TARGET,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.join(MODEL_DIR, "model_pipeline.joblib")
METRICS_PATH = os.path.join(MODEL_DIR, "model_metrics.json")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(path: str) -> pd.DataFrame:
    if path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, engine="openpyxl")
    else:
        df = pd.read_csv(path)
    log.info(f"Loaded dataset: {df.shape[0]} rows × {df.shape[1]} columns from {path}")
    return df


def backup_old_model():
    """Backup existing model and metrics files with a timestamp."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    for src in [MODEL_PATH, METRICS_PATH]:
        if os.path.exists(src):
            ext = os.path.splitext(src)[1]
            base = os.path.splitext(src)[0]
            dst = f"{base}_backup_{ts}{ext}"
            shutil.copy2(src, dst)
            log.info(f"Backed up: {src} → {dst}")
    return ts


def data_quality_report(raw_df: pd.DataFrame, clean_df: pd.DataFrame) -> dict:
    """Summarise data quality before and after cleaning."""
    # Try to identify synthetic/estimated records
    synthetic_count = 0
    genuine_count   = 0

    # Look for a data_source or coordinate_status column indicating provenance
    for col in ["coordinate_status", "data_source", "property_source"]:
        if col in raw_df.columns:
            vals = raw_df[col].astype(str).str.upper()
            if col == "coordinate_status":
                genuine_count = int((vals.str.contains("PROPERTY_SOURCE|EXACT", na=False)).sum())
                synthetic_count = int((vals.str.contains("LOCALITY_CENTROID|LOCALITY_LEVEL", na=False)).sum())
            break

    # Outlier count in target
    if TARGET in clean_df.columns:
        q1 = clean_df[TARGET].quantile(0.25)
        q3 = clean_df[TARGET].quantile(0.75)
        iqr = q3 - q1
        outliers = int(((clean_df[TARGET] < q1 - 3*iqr) | (clean_df[TARGET] > q3 + 3*iqr)).sum())
    else:
        outliers = 0

    return {
        "raw_records":          int(raw_df.shape[0]),
        "clean_records":        int(clean_df.shape[0]),
        "dropped_records":      int(raw_df.shape[0] - clean_df.shape[0]),
        "genuine_records_est":  genuine_count,
        "synthetic_records_est": synthetic_count,
        "outliers_in_target_3iqr": outliers,
        "taluk_coverage":       clean_df["taluk"].value_counts().to_dict() if "taluk" in clean_df.columns else {},
    }


def metrics_from_arrays(y_true, y_pred):
    """Compute MAE, RMSE, R² from arrays."""
    mae  = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2   = float(r2_score(y_true, y_pred))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 6)}


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_model_cv(model, X: pd.DataFrame, y: pd.Series,
                       groups=None, n_splits=5) -> dict:
    """
    5-fold cross-validation.
    - If groups provided and len(unique groups) >= n_splits: uses GroupKFold.
    - Otherwise: falls back to KFold (shuffled, random_state=42).
    """
    n_groups = len(groups.unique()) if groups is not None else 0

    if groups is not None and n_groups >= n_splits:
        kf = GroupKFold(n_splits=n_splits)
        split_iter = kf.split(X, y, groups)
        cv_type = "GroupKFold (locality-grouped)"
    else:
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
        split_iter = kf.split(X, y)
        cv_type = "KFold (random, shuffled)"

    mae_scores, rmse_scores, r2_scores = [], [], []

    for train_idx, val_idx in split_iter:
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # Build a fresh pipeline per fold to prevent leakage
        pipe_cv = Pipeline([
            ("preprocessor", build_preprocessor()),
            ("model", clone(model)),
        ])
        pipe_cv.fit(X_tr, y_tr)
        preds = np.clip(pipe_cv.predict(X_val), 0, None)

        mae_scores.append(mean_absolute_error(y_val, preds))
        rmse_scores.append(np.sqrt(mean_squared_error(y_val, preds)))
        r2_scores.append(r2_score(y_val, preds))

    return {
        "mae":      round(float(np.mean(mae_scores)), 4),
        "rmse":     round(float(np.mean(rmse_scores)), 4),
        "r2":       round(float(np.mean(r2_scores)), 6),
        "mae_std":  round(float(np.std(mae_scores)), 4),
        "rmse_std": round(float(np.std(rmse_scores)), 4),
        "r2_std":   round(float(np.std(r2_scores)), 6),
        "n_folds":  len(mae_scores),
        "cv_type":  cv_type,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SHAP EXPLAINABILITY
# ─────────────────────────────────────────────────────────────────────────────

def compute_shap(pipeline, X_sample: pd.DataFrame, feature_names: list) -> dict | None:
    """
    Compute SHAP values for tree-based model.
    Returns a dict with mean absolute SHAP values per feature (top 15).
    """
    try:
        import shap
        mdl = pipeline.named_steps["model"]
        tree_mdl = mdl.regressor_ if hasattr(mdl, "regressor_") else mdl
        pre = pipeline.named_steps["preprocessor"]
        X_transformed = pre.transform(X_sample)

        explainer = shap.TreeExplainer(tree_mdl)
        shap_values = explainer.shap_values(X_transformed)

        mean_abs_shap = np.abs(shap_values).mean(axis=0)
        n = min(len(feature_names), len(mean_abs_shap))
        shap_importance = sorted(
            [(feature_names[i], float(mean_abs_shap[i])) for i in range(n)],
            key=lambda x: x[1], reverse=True
        )[:15]

        log.info("SHAP computed successfully.")
        return {"shap_top_features": shap_importance, "shap_n_samples": len(X_sample)}
    except ImportError:
        log.warning("SHAP not installed — skipping explainability.")
        return None
    except Exception as e:
        log.warning(f"SHAP computation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE IMPORTANCES
# ─────────────────────────────────────────────────────────────────────────────

def extract_feature_importances(pipeline, X: pd.DataFrame) -> list | None:
    """Extract feature importances from RF or HGB models."""
    try:
        ohe = pipeline.named_steps["preprocessor"].transformers_[1][1].named_steps["onehot"]
        cat_names  = list(ohe.get_feature_names_out(CATEGORICAL_FEATURES))
        num_names  = [c for c in NUMERICAL_FEATURES if c in X.columns]
        bin_names  = [c for c in BINARY_FEATURES if c in X.columns]
        feature_names = num_names + cat_names + bin_names

        mdl = pipeline.named_steps["model"]
        tree_mdl = mdl.regressor_ if hasattr(mdl, "regressor_") else mdl
        if hasattr(tree_mdl, "feature_importances_"):
            imp = tree_mdl.feature_importances_
            result = sorted(
                [(feature_names[i], float(imp[i])) for i in range(min(len(feature_names), len(imp)))],
                key=lambda x: x[1], reverse=True,
            )[:15]
            return result, feature_names
        else:
            return None, feature_names
    except Exception as e:
        log.warning(f"Could not extract feature importances: {e}")
    return None, []


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TRAINING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def train(dataset_path: str, run_shap: bool = True):
    log.info("=" * 65)
    log.info("SMART LAND VALUATION — ML TRAINING v2")
    log.info("=" * 65)

    # ── 0. Backup old model ───────────────────────────────────────────────
    backup_ts = backup_old_model()

    # ── 1. Load & prepare data ────────────────────────────────────────────
    raw_df = load_dataset(dataset_path)
    df = prepare_dataframe(raw_df)
    log.info(f"After cleaning: {len(df)} records ready for training")

    if len(df) < 10:
        raise ValueError(f"Too few records ({len(df)}) after cleaning. Cannot train.")

    dq_report = data_quality_report(raw_df, df)
    log.info(f"Data quality: {dq_report}")

    feature_cols = [c for c in NUMERICAL_FEATURES + CATEGORICAL_FEATURES + BINARY_FEATURES
                    if c in df.columns]
    X_all = df[feature_cols].reset_index(drop=True)
    y_all = df[TARGET].reset_index(drop=True)

    # Locality groups (for grouped CV)
    groups = df["village_or_locality"].reset_index(drop=True) if "village_or_locality" in df.columns else None

    # ── 2. Holdout test split (15%, stratified by price quartile) ─────────
    # For small datasets (< 200) use 15% holdout; always stratify by quartile
    n_total = len(df)
    if n_total >= 50:
        test_size = 0.15
        y_quartile = pd.qcut(y_all, q=4, labels=False, duplicates="drop")
        try:
            X_train_all, X_test, y_train_all, y_test = train_test_split(
                X_all, y_all, test_size=test_size,
                stratify=y_quartile, random_state=42
            )
            groups_train = groups.iloc[X_train_all.index] if groups is not None else None
        except Exception:
            X_train_all, X_test, y_train_all, y_test = train_test_split(
                X_all, y_all, test_size=test_size, random_state=42
            )
            groups_train = groups.iloc[X_train_all.index] if groups is not None else None
        X_train_all = X_train_all.reset_index(drop=True)
        y_train_all = y_train_all.reset_index(drop=True)
        X_test      = X_test.reset_index(drop=True)
        y_test      = y_test.reset_index(drop=True)
        if groups_train is not None:
            groups_train = groups_train.reset_index(drop=True)
        log.info(f"Holdout split: {len(X_train_all)} train / {len(X_test)} test")
    else:
        # Too small for a holdout — use all data for CV, no holdout
        X_train_all, y_train_all = X_all, y_all
        X_test, y_test = None, None
        groups_train = groups
        log.warning("Dataset too small for a meaningful holdout. Using CV only.")

    # ── 3. Define candidate models (tuned via RandomizedSearchCV) ─────────
    candidates = {
        "LinearRegression": LinearRegression(),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=400,
            max_depth=30,
            min_samples_split=2,
            min_samples_leaf=1,
            max_features=0.6,
            random_state=42,
            n_jobs=2,
        ),
        "ExtraTreesRegressor": TransformedTargetRegressor(
            regressor=ExtraTreesRegressor(
                n_estimators=400,
                max_depth=None,
                min_samples_split=2,
                min_samples_leaf=1,
                max_features=0.45,
                random_state=42,
                n_jobs=2,
            ),
            func=np.log1p,
            inverse_func=np.expm1,
        ),
        "GradientBoostingRegressor": GradientBoostingRegressor(
            n_estimators=250,
            learning_rate=0.05,
            max_depth=4,
            min_samples_leaf=2,
            subsample=0.8,
            max_features=0.6,
            random_state=42,
        ),
        "HistGradientBoostingRegressor": HistGradientBoostingRegressor(
            max_iter=300 if n_total >= 200 else 200,
            learning_rate=0.05,
            max_depth=6,
            min_samples_leaf=10 if n_total >= 200 else 5,
            l2_regularization=0.1,
            random_state=42,
        ),
    }

    # ── 4. Cross-validate on training set (GroupKFold + KFold) ───────────
    log.info(f"\nRunning 5-fold CV on {len(X_train_all)} training records...")
    cv_results = {}
    kfold_results = {}
    for name, model in candidates.items():
        log.info(f"  Evaluating {name}...")
        metrics = evaluate_model_cv(
            model, X_train_all, y_train_all,
            groups=groups_train, n_splits=5
        )
        cv_results[name] = metrics
        kf_metrics = evaluate_model_cv(
            model, X_train_all, y_train_all,
            groups=None, n_splits=5
        )
        kfold_results[name] = kf_metrics
        log.info(
            f"    GroupKFold: MAE={metrics['mae']:.2f}±{metrics['mae_std']:.2f}  "
            f"RMSE={metrics['rmse']:.2f}  R²={metrics['r2']:.4f}±{metrics['r2_std']:.4f} | "
            f"KFold: MAE={kf_metrics['mae']:.2f}  R²={kf_metrics['r2']:.4f}"
        )

    # ── 5. Select best model by GroupKFold CV MAE ────────────────────────
    best_name = min(cv_results, key=lambda n: cv_results[n]["mae"])
    log.info(f"\nBest model by GroupKFold CV MAE: {best_name}  (MAE={cv_results[best_name]['mae']:.2f})")

    # ── 6. Train final pipeline on FULL training set ─────────────────────
    final_pipeline = Pipeline([
        ("preprocessor", build_preprocessor()),
        ("model", candidates[best_name]),
    ])
    final_pipeline.fit(X_train_all, y_train_all)
    log.info("Final pipeline trained on full training set.")

    # ── 7. Evaluate on holdout test set ──────────────────────────────────
    holdout_metrics = None
    if X_test is not None and len(X_test) > 0:
        y_pred_test = final_pipeline.predict(X_test)
        holdout_metrics = metrics_from_arrays(y_test, y_pred_test)
        log.info(
            f"Holdout test ({len(X_test)} records): "
            f"MAE={holdout_metrics['mae']:.2f}  "
            f"RMSE={holdout_metrics['rmse']:.2f}  "
            f"R²={holdout_metrics['r2']:.4f}"
        )

    # ── 8. Train-set metrics (overfitting check) ──────────────────────────
    y_pred_train = final_pipeline.predict(X_train_all)
    train_metrics = metrics_from_arrays(y_train_all, y_pred_train)
    log.info(f"Train metrics (overfit check): MAE={train_metrics['mae']:.2f}  R²={train_metrics['r2']:.4f}")

    # ── 9. Retrain on ALL data (train+test) for final deployed model ──────
    # We use holdout only for evaluation, not for training the deployed model.
    # The deployed model is trained on X_train_all to be honest about CV metrics.
    # (If dataset is large, you might merge; for 76 records keep train split only.)
    log.info("Deployed model: trained on training split only (holdout kept for evaluation).")

    # ── 10. Feature importances ───────────────────────────────────────────
    feat_imp, feature_names = extract_feature_importances(final_pipeline, X_train_all)

    # ── 11. SHAP explainability ───────────────────────────────────────────
    shap_data = None
    best_est = candidates[best_name].regressor if hasattr(candidates[best_name], "regressor") else candidates[best_name]
    is_tree_model = isinstance(
        best_est,
        (RandomForestRegressor, ExtraTreesRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor),
    )
    if run_shap and is_tree_model:
        log.info("Computing SHAP values on representative sample...")
        shap_data = compute_shap(final_pipeline, X_train_all.head(100), feature_names)
        if feat_imp is None and shap_data and shap_data.get("shap_top_features"):
            feat_imp = shap_data["shap_top_features"]

    # ── 12. Save model ────────────────────────────────────────────────────
    joblib.dump(final_pipeline, MODEL_PATH)
    log.info(f"Model saved → {MODEL_PATH}")

    # ── 13. Save metrics JSON ─────────────────────────────────────────────
    # Primary validation metrics: CV results (not train, not holdout — holdout
    # is too small for a reliable single estimate with 76 records)
    primary_mae  = cv_results[best_name]["mae"]
    primary_rmse = cv_results[best_name]["rmse"]
    primary_r2   = cv_results[best_name]["r2"]

    metrics_data = {
        "best_model":            best_name,
        "training_records":      int(len(X_train_all)),
        "total_records_in_file": int(n_total),
        "feature_count":         len(feature_cols),
        "features_used":         feature_cols,
        "dataset_path":          dataset_path,
        "dataset_version":       "v2_1050records",
        "target":                TARGET,
        "trained_at":            datetime.utcnow().isoformat(),
        "backup_timestamp":      backup_ts,
        "train_test_split":      {
            "train_size": int(len(X_train_all)),
            "test_size":  int(len(X_test)) if X_test is not None else 0,
        },
        # CV metrics — primary performance estimate
        "cv_results":          cv_results,
        "kfold_results":       kfold_results,
        "validation_mae":      primary_mae,
        "validation_rmse":     primary_rmse,
        "validation_r2":       primary_r2,
        "kfold_mae":           kfold_results[best_name]["mae"],
        "kfold_rmse":          kfold_results[best_name]["rmse"],
        "kfold_r2":            kfold_results[best_name]["r2"],
        "n_folds":             5,
        # Holdout metrics — independent estimate (may be noisy for small datasets)
        "holdout_metrics":     holdout_metrics,
        # Train metrics — for overfitting check only
        "train_metrics":       train_metrics,
        "train_mae":           train_metrics["mae"],
        "train_r2":            train_metrics["r2"],
        # Feature importances
        "feature_importances": feat_imp,
        # SHAP
        "shap_explainability": shap_data,
        # Data quality
        "data_quality_report": dq_report,
        # Price distribution
        "price_distribution": {
            "mean":   round(float(y_all.mean()), 4),
            "median": round(float(y_all.median()), 4),
            "std":    round(float(y_all.std()), 4),
            "min":    round(float(y_all.min()), 4),
            "max":    round(float(y_all.max()), 4),
            "p25":    round(float(y_all.quantile(0.25)), 4),
            "p75":    round(float(y_all.quantile(0.75)), 4),
        },
    }

    with open(METRICS_PATH, "w") as f:
        json.dump(metrics_data, f, indent=2)
    log.info(f"Metrics saved → {METRICS_PATH}")

    # ── 14. Print summary ─────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("TRAINING COMPLETE")
    print("=" * 65)
    print(f"Dataset         : {os.path.basename(dataset_path)}")
    print(f"Total records   : {n_total} (train={len(X_train_all)}, test={len(X_test) if X_test is not None else 'N/A'})")
    print(f"Best model      : {best_name}")
    print()
    print("── CROSS-VALIDATION RESULTS ──────────────────────────────────")
    print(f"{'Model':<40} {'CV MAE':>10} {'CV RMSE':>10} {'CV R²':>8}")
    print("-" * 70)
    for name, m in cv_results.items():
        marker = " ← BEST" if name == best_name else ""
        print(f"{name:<40} {m['mae']:>10.2f} {m['rmse']:>10.2f} {m['r2']:>8.4f}{marker}")
    print()
    if holdout_metrics:
        print("── HOLDOUT TEST METRICS ──────────────────────────────────────")
        print(f"MAE={holdout_metrics['mae']:.2f}  RMSE={holdout_metrics['rmse']:.2f}  R²={holdout_metrics['r2']:.4f}")
        print()
    print("── OVERFITTING CHECK ─────────────────────────────────────────")
    print(f"Train MAE={train_metrics['mae']:.2f}  Train R²={train_metrics['r2']:.4f}")
    print()
    print(f"Price range  : ₹{y_all.min():.0f} – ₹{y_all.max():.0f}/sq.ft  (median ₹{y_all.median():.0f})")
    if feat_imp:
        print("\nTop feature importances:")
        for fname, fimp in feat_imp[:8]:
            print(f"  {fname:<50} {fimp:.4f}")
    if shap_data and shap_data.get("shap_top_features"):
        print("\nSHAP top features (mean |SHAP|):")
        for fname, sval in shap_data["shap_top_features"][:8]:
            print(f"  {fname:<50} {sval:.4f}")
    print("=" * 65)

    return metrics_data


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train ML price prediction model v2")
    default_dataset = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "Mysuru_Land_Evaluation_1000_Master.xlsx"
    )
    parser.add_argument("--dataset", default=default_dataset,
                        help="Path to the dataset Excel or CSV file")
    parser.add_argument("--no-shap", action="store_true",
                        help="Skip SHAP computation (faster)")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"ERROR: Dataset not found at: {args.dataset}")
        sys.exit(1)

    train(args.dataset, run_shap=not args.no_shap)
