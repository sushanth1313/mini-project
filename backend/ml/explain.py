"""
Explainability module using SHAP for tree-based models (HistGradientBoosting / RandomForest).
Provides:
  - explain_prediction(input_df): Top positive/negative factors influencing a specific valuation.
  - get_feature_names(preprocessor, X): All feature names after preprocessing.
"""
import copy
import os
import json
import logging
import numpy as np
import pandas as pd
import joblib

log = logging.getLogger(__name__)

MODEL_DIR  = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(MODEL_DIR, "model_pipeline.joblib")

_explainer = None
_cached_pipeline = None


def get_feature_names_from_preprocessor(preprocessor, X_cols=None) -> list:
    """Extract transformed feature names (numerical, one-hot categorical, binary)."""
    try:
        from ml.preprocess import NUMERICAL_FEATURES, CATEGORICAL_FEATURES, BINARY_FEATURES
        num_names = [c for c in NUMERICAL_FEATURES if X_cols is None or c in X_cols]
        ohe = preprocessor.transformers_[1][1].named_steps["onehot"]
        cat_names = list(ohe.get_feature_names_out(CATEGORICAL_FEATURES))
        bin_names = [c for c in BINARY_FEATURES if X_cols is None or c in X_cols]
        return num_names + cat_names + bin_names
    except Exception as e:
        log.warning(f"Could not build feature names: {e}")
        return []


def _compute_tree_shap(base_mdl, X_trans):
    """
    Compute exact TreeSHAP values and expected value for tree ensembles.
    Evaluates large forests (e.g., 400-tree ExtraTrees) in 50-tree chunks and
    averages linearly so C++/NumPy TreeEnsemble peak stays ~50 MB lower while
    producing mathematically identical SHAP contributions.
    """
    import shap
    from ml.lightweight import release_os_memory

    estimators = getattr(base_mdl, "estimators_", None)
    if estimators and len(estimators) > 50:
        n_total = len(estimators)
        sv_sum = None
        ev_sum = 0.0
        for i in range(0, n_total, 50):
            chunk = estimators[i:i + 50]
            sub = copy.copy(base_mdl)
            sub.estimators_ = chunk
            sub.n_estimators = len(chunk)
            expl = shap.TreeExplainer(sub)
            sv = np.asarray(expl.shap_values(X_trans)[0], dtype=float) * len(chunk)
            ev = expl.expected_value
            if isinstance(ev, (list, np.ndarray)):
                ev_scalar = float(np.asarray(ev).ravel()[0])
            else:
                ev_scalar = float(ev)
            sv_sum = sv if sv_sum is None else (sv_sum + sv)
            ev_sum += ev_scalar * len(chunk)
            del expl, sub, sv
            release_os_memory()
        return sv_sum / n_total, ev_sum / n_total

    expl = shap.TreeExplainer(base_mdl)
    try:
        sv = np.asarray(expl.shap_values(X_trans)[0], dtype=float)
        ev = expl.expected_value
        if isinstance(ev, (list, np.ndarray)):
            ev_scalar = float(np.asarray(ev).ravel()[0])
        else:
            ev_scalar = float(ev)
        return sv, ev_scalar
    finally:
        del expl
        release_os_memory()


def explain_prediction(pipeline, input_df: pd.DataFrame, top_k: int = 6) -> dict:
    """
    Explain a single prediction using SHAP values.
    Returns:
      {
        'base_value': float,
        'prediction': float,
        'top_positive_factors': [(feature_name, contribution_inr), ...],
        'top_negative_factors': [(feature_name, contribution_inr), ...],
        'all_top_factors': [{'feature': name, 'impact': inr, 'direction': 'increases_price'/'decreases_price'}, ...]
      }
    """
    X_trans = None
    shap_vals = None
    try:
        pre = pipeline.named_steps["preprocessor"]
        mdl = pipeline.named_steps["model"]
        base_mdl = mdl.regressor_ if hasattr(mdl, "regressor_") else mdl

        X_trans = pre.transform(input_df)
        feature_names = get_feature_names_from_preprocessor(pre, list(input_df.columns))

        shap_vals, base_val = _compute_tree_shap(base_mdl, X_trans)

        pred_val = float(mdl.predict(X_trans)[0])
        is_log_target = hasattr(mdl, "regressor_")
        if is_log_target:
            base_price = float(np.expm1(base_val))
            total_log_shap = float(np.sum(shap_vals))
            delta_inr = pred_val - base_price
            scale = (delta_inr / total_log_shap) if abs(total_log_shap) > 1e-6 else 0.0
            shap_inr = shap_vals * scale
        else:
            base_price = base_val
            shap_inr = shap_vals

        impacts = []
        for name, val in zip(feature_names, shap_inr):
            val_f = float(val)
            if abs(val_f) >= 1.0:
                impacts.append({
                    "feature": name,
                    "impact_inr_per_sqft": round(val_f, 2),
                    "direction": "increases_price" if val_f > 0 else "decreases_price",
                    "abs_impact": abs(val_f),
                })

        impacts.sort(key=lambda x: x["abs_impact"], reverse=True)
        top_factors = impacts[:top_k]

        pos = [f for f in impacts if f["direction"] == "increases_price"][:top_k]
        neg = [f for f in impacts if f["direction"] == "decreases_price"][:top_k]

        return {
            "base_price_per_sqft": round(base_price, 2),
            "predicted_price_per_sqft": round(pred_val, 2),
            "top_factors": top_factors,
            "top_positive_factors": pos,
            "top_negative_factors": neg,
            "shap_available": True,
        }
    except Exception as e:
        log.warning(f"explain_prediction failed: {e}")
        return {"shap_available": False, "error": str(e)}
    finally:
        del X_trans, shap_vals
        try:
            from ml.lightweight import release_os_memory
            release_os_memory()
        except Exception:
            pass

