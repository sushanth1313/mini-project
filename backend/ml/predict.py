"""
ML Prediction module — loads trained pipeline and makes predictions.

Changes in v3:
  - prediction_reliability_indicator: stratum-based confidence (N comparable records)
  - locality_stats returned (median, count, price_range) for valuation context
  - holdout metrics used for validation_mae/r2 (not GroupKFold)
  - reload_model() correctly resets both pipeline and metrics cache
"""
import gc
import os
import json
import logging
import numpy as np
import pandas as pd
import joblib

log = logging.getLogger(__name__)

MODEL_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH   = os.path.join(MODEL_DIR, "model_pipeline.joblib")
METRICS_PATH = os.path.join(MODEL_DIR, "model_metrics.json")

_pipeline   = None
_metrics    = None
_train_df   = None   # lightweight copy for reliability lookups


def _load_pipeline():
    global _pipeline
    if _pipeline is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. "
                "Run: python backend/ml/train.py --dataset <path_to_dataset>"
            )
        _pipeline = joblib.load(MODEL_PATH)
        gc.collect()
        log.info("ML pipeline loaded.")
    return _pipeline


def _load_metrics():
    global _metrics
    if _metrics is None:
        if not os.path.exists(METRICS_PATH):
            return {}
        with open(METRICS_PATH) as f:
            _metrics = json.load(f)
    return _metrics


def _load_train_df():
    """
    Load a lightweight copy of the training dataset for reliability lookups.
    Only loads columns needed for stratum matching.
    """
    global _train_df
    if _train_df is not None:
        return _train_df
    metrics = _load_metrics()
    dataset_path = metrics.get("dataset_path", "")
    # Try a few common locations
    candidates = [
        dataset_path,
        os.path.join(MODEL_DIR, "Mysuru_Land_Evaluation_1000_Master.xlsx"),
        os.path.join(MODEL_DIR, "..", "..", "Mysuru_Land_Evaluation_1000_Master.xlsx"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            try:
                from ml.preprocess import derive_region_3class, NUMERICAL_FEATURES, _haversine_vec
                gis_ref_cols = [c for c in NUMERICAL_FEATURES if "nearest_" in c or "count_3km" in c or "waterbody" in c or "distance_to_" in c]
                cols = list(dict.fromkeys([
                    "taluk", "village_or_locality", "region_type",
                    "land_type", "listing_type", "price_per_sqft", "land_area_sqft",
                    "latitude", "longitude", *gis_ref_cols,
                ]))
                df_tmp = pd.read_excel(p, usecols=lambda c: c in cols)
                if "latitude" in df_tmp.columns and "longitude" in df_tmp.columns:
                    lat = pd.to_numeric(df_tmp["latitude"], errors="coerce")
                    lon = pd.to_numeric(df_tmp["longitude"], errors="coerce")
                    df_tmp["dist_mysuru_center_km"] = _haversine_vec(lat, lon, 12.3052, 76.6552)
                _train_df = derive_region_3class(df_tmp)
                del df_tmp
                gc.collect()
                log.info(f"Training reference dataset loaded: {len(_train_df)} rows from {p}")
                return _train_df
            except Exception as e:
                log.warning(f"Could not load training df from {p}: {e}")
    log.warning("Could not load training dataset for reliability analysis.")
    _train_df = pd.DataFrame()
    return _train_df


def _normalize_locality_name(name: str) -> str:
    from gis.geo_utils import normalize_locality
    return normalize_locality(name)


def _reliability_indicator(input_data: dict, pred_psf: float, metrics: dict) -> dict:
    """
    Compute a transparent reliability indicator distinguishing:
    1. Exact normalized locality records (case/whitespace normalized)
    2. Close spelling / nearby locality matches (e.g. 'kadkola' -> 'Kadakola')
    3. Comparable regional stratum records (same canonical taluk + land_type + region_type)
    4. Taluk & district-level training coverage (892 training / 1,050 total)

    Important safeguards:
      - Requires >= 3 comparable locality records to treat median/quartiles as statistically reliable.
      - Emphasizes Locality GroupKFold (R²=0.7559, MAE=₹566.74/sq.ft) for unseen localities.
      - Never calls R² "model accuracy".
    """
    import difflib
    from ml.preprocess import canonicalize_categorical, derive_region_3class, _haversine_vec

    taluk       = canonicalize_categorical("taluk", input_data.get("taluk", ""))
    locality    = str(input_data.get("village_or_locality", "")).strip()
    loc_norm    = _normalize_locality_name(locality)
    raw_region  = canonicalize_categorical("region_type", input_data.get("region_type", ""))
    land_type   = canonicalize_categorical("land_type", input_data.get("land_type", ""))
    lat_v = input_data.get("latitude")
    lon_v = input_data.get("longitude")
    dc_v = float(_haversine_vec(float(lat_v), float(lon_v), 12.3052, 76.6552)) if (lat_v is not None and lon_v is not None) else np.nan
    region_df   = derive_region_3class(pd.DataFrame([{
        "taluk": taluk,
        "village_or_locality": locality,
        "region_type": raw_region,
        "land_type": land_type,
        "dist_mysuru_center_km": dc_v,
        "nearest_hospital_km": input_data.get("nearest_hospital_km", np.nan),
        "amenity_count_3km_total": np.nan,
    }]))
    region_type = str(region_df["region_type"].iloc[0])

    df = _load_train_df()

    stratum_count   = 0
    taluk_count     = 0
    locality_count  = 0
    fuzzy_match_name  = None
    fuzzy_match_count = 0
    locality_median = None
    locality_p25    = None
    locality_p75    = None

    n_train_total = int(metrics.get("training_records", 892) or 892)
    n_file_total  = int(metrics.get("total_records_in_file", 1050) or 1050)

    if not df.empty:
        taluk_series  = df["taluk"].astype(str).str.strip()
        land_series   = df["land_type"].astype(str).str.strip()
        region_series = df["region_type"].astype(str).str.strip()
        loc_series    = df["village_or_locality"].astype(str).map(_normalize_locality_name)

        taluk_count = int((taluk_series == taluk).sum())

        mask_stratum = (
            (taluk_series == taluk) &
            (land_series == land_type) &
            (region_series == region_type)
        )
        stratum_df = df[mask_stratum]
        stratum_count = int(len(stratum_df))

        # 1. Exact normalized locality match
        loc_df = df[loc_series == loc_norm] if loc_norm else df.iloc[0:0]
        locality_count = int(len(loc_df))

        # 2. Close spelling match if exact match is 0
        if locality_count == 0 and loc_norm:
            taluk_df = df[taluk_series == taluk]
            pool = taluk_df if not taluk_df.empty else df
            unique_norms = {n: orig for orig, n in zip(pool["village_or_locality"].astype(str), pool["village_or_locality"].astype(str).map(_normalize_locality_name)) if n}
            matches = difflib.get_close_matches(loc_norm, list(unique_norms.keys()), n=1, cutoff=0.78)
            if matches:
                matched_norm = matches[0]
                fuzzy_match_name = unique_norms[matched_norm]
                fuzzy_df = pool[pool["village_or_locality"].astype(str).map(_normalize_locality_name) == matched_norm]
                fuzzy_match_count = int(len(fuzzy_df))
                fuzzy_same_type = fuzzy_df[fuzzy_df["land_type"].astype(str).str.strip() == land_type]
                stat_df = fuzzy_same_type if not fuzzy_same_type.empty else fuzzy_df
                locality_median = float(stat_df["price_per_sqft"].median())
                locality_p25    = float(stat_df["price_per_sqft"].quantile(0.25))
                locality_p75    = float(stat_df["price_per_sqft"].quantile(0.75))
        elif locality_count > 0:
            loc_same_type = loc_df[loc_df["land_type"].astype(str).str.strip() == land_type]
            stat_df = loc_same_type if not loc_same_type.empty else loc_df
            locality_median = float(stat_df["price_per_sqft"].median())
            locality_p25    = float(stat_df["price_per_sqft"].quantile(0.25))
            locality_p75    = float(stat_df["price_per_sqft"].quantile(0.75))

    effective_loc_count = locality_count if locality_count > 0 else fuzzy_match_count
    statistically_reliable_median = effective_loc_count >= 3

    kfold_r2 = float(metrics.get("kfold_r2", 0.8573) or 0.8573)
    gkf_r2   = float(metrics.get("validation_r2", 0.7559) or 0.7559)
    gkf_mae  = float(metrics.get("validation_mae", 566.74) or 566.74)
    holdout_r2  = float((metrics.get("holdout_metrics") or {}).get("r2", 0.8695))
    holdout_mae = float((metrics.get("holdout_metrics") or {}).get("mae", 365.21))

    loc_clause = (
        f"{locality_count} exact record(s) for '{locality}'"
        if locality_count > 0
        else (
            f"0 exact records for '{locality}' (close spelling match '{fuzzy_match_name}' has {fuzzy_match_count} record(s))"
            if fuzzy_match_name
            else f"0 exact records for '{locality}' (unseen locality)"
        )
    )
    if effective_loc_count == 1:
        sample_clause = "Single locality record only — insufficient for a statistically reliable locality median."
    elif effective_loc_count == 2:
        sample_clause = "Limited 2-record locality sample — treat comparable reference with caution."
    elif effective_loc_count >= 3:
        sample_clause = f"Comparable locality sample: {effective_loc_count} records."
    else:
        sample_clause = f"Unseen locality: Locality GroupKFold validation indicates R²={gkf_r2:.4f}, MAE=₹{gkf_mae:,.2f}/sq.ft."

    regional_clause = (
        f"{stratum_count} comparable ({taluk}, {land_type}, {region_type}) stratum records, "
        f"{taluk_count} {taluk} taluk records, and {n_train_total:,} training / {n_file_total:,} total district records."
    )

    if locality_count >= 3 and kfold_r2 >= 0.80:
        tier = "High"
        tier_color = "green"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Holdout R²={holdout_r2:.4f} (variance explained; not % accuracy)."
    elif effective_loc_count >= 2 or (effective_loc_count == 0 and stratum_count >= 25 and gkf_r2 >= 0.70):
        tier = "Moderate"
        tier_color = "orange"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Indicative benchmark only (not guaranteed market value)."
    elif effective_loc_count == 1 or (taluk_count >= 10 and gkf_r2 >= 0.65):
        tier = "Low"
        tier_color = "darkorange"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Single-record or sparse local coverage — treat estimate strictly as a coarse regional benchmark and verify locally."
    else:
        tier = "Very Low"
        tier_color = "red"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Independent registered valuation strongly recommended."

    deviation_note = None
    if locality_median and locality_median > 0 and pred_psf > 0:
        ratio = pred_psf / locality_median
        ref_label = fuzzy_match_name or locality
        comp_desc = (
            f"comparable median (₹{locality_median:,.0f}/sq.ft from {effective_loc_count} records)"
            if statistically_reliable_median
            else f"single-record / small-sample reference (₹{locality_median:,.0f}/sq.ft from {effective_loc_count} record(s); not a statistically reliable median)"
        )
        if ratio > 1.3:
            deviation_note = (
                f"Prediction (₹{pred_psf:,.0f}/sq.ft) is {(ratio-1)*100:.0f}% above the "
                f"'{ref_label}' {comp_desc}. This reflects model generalisation from broader {taluk} "
                f"stratum listings; independent local market verification is advised."
            )
        elif ratio < 0.7:
            deviation_note = (
                f"Prediction (₹{pred_psf:,.0f}/sq.ft) is {(1-ratio)*100:.0f}% below the "
                f"'{ref_label}' {comp_desc}. Independent verification advised."
            )

    return {
        "tier": tier,
        "tier_color": tier_color,
        "locality_count": locality_count,
        "fuzzy_match_name": fuzzy_match_name,
        "fuzzy_match_count": fuzzy_match_count,
        "statistically_reliable_median": statistically_reliable_median,
        "stratum_count": stratum_count,
        "taluk_count": taluk_count,
        "district_training_count": n_train_total,
        "locality_median_psf": round(locality_median, 2) if locality_median else None,
        "locality_p25_psf": round(locality_p25, 2) if (locality_p25 and statistically_reliable_median) else None,
        "locality_p75_psf": round(locality_p75, 2) if (locality_p75 and statistically_reliable_median) else None,
        "model_r2": round(gkf_r2 if locality_count == 0 else holdout_r2, 4),
        "holdout_r2": round(holdout_r2, 4),
        "holdout_mae": round(holdout_mae, 2),
        "kfold_r2": round(kfold_r2, 4),
        "groupkfold_r2": round(gkf_r2, 4),
        "groupkfold_mae": round(gkf_mae, 2),
        "explanation": explanation,
        "deviation_note": deviation_note,
    }


def impute_missing_gis_features(ml_input_dict: dict) -> dict:
    """
    Fill ONLY missing (None / '' / NaN) GIS distance & count features using the
    matching (taluk, region_type) stratum median from the training dataset, instead of
    letting SimpleImputer fall back to district-wide rural medians when GIS is unavailable.
    Never overwrites retrieved GIS or user-supplied values and never alters model weights.
    """
    from ml.preprocess import canonicalize_categorical, derive_region_3class, NUMERICAL_FEATURES, _haversine_vec

    out = dict(ml_input_dict)
    gis_cols = [c for c in NUMERICAL_FEATURES if "nearest_" in c or "count_3km" in c or "waterbody" in c]
    missing_cols = [
        c for c in gis_cols
        if out.get(c) in (None, "", "nan") or (isinstance(out.get(c), float) and np.isnan(out.get(c)))
    ]
    if not missing_cols:
        return out

    df = _load_train_df()
    if df is None or df.empty:
        return out

    taluk = canonicalize_categorical("taluk", out.get("taluk", ""))
    raw_reg = canonicalize_categorical("region_type", out.get("region_type", ""))
    lt = canonicalize_categorical("land_type", out.get("land_type", ""))
    lat_v = out.get("latitude")
    lon_v = out.get("longitude")
    dc_v = float(_haversine_vec(float(lat_v), float(lon_v), 12.3052, 76.6552)) if (lat_v not in (None, "") and lon_v not in (None, "")) else np.nan
    reg_df = derive_region_3class(pd.DataFrame([{
        "taluk": taluk,
        "village_or_locality": str(out.get("village_or_locality", "")),
        "region_type": raw_reg,
        "land_type": lt,
        "dist_mysuru_center_km": dc_v,
        "nearest_hospital_km": out.get("nearest_hospital_km", np.nan),
        "amenity_count_3km_total": np.nan,
    }]))
    region_type = str(reg_df["region_type"].iloc[0])

    taluk_s = df["taluk"].astype(str).str.strip()
    reg_s = df["region_type"].astype(str).str.strip()
    pool = df[(taluk_s == taluk) & (reg_s == region_type)]
    if len(pool) < 5:
        pool = df[reg_s == region_type]
    if pool.empty:
        return out

    for col in missing_cols:
        if col in pool.columns:
            med = pd.to_numeric(pool[col], errors="coerce").median()
            if pd.notna(med):
                out[col] = round(float(med), 3) if "nearest_" in col or "distance_" in col else int(round(float(med)))
    return out


def predict_price_per_sqft(input_df, input_data: dict = None, explain: bool = False) -> dict:
    """
    Predict price per sqft from a prepared DataFrame (single row).
    Returns a dict with prediction and metadata.

    Args:
        input_df: Prepared DataFrame from prepare_single_input()
        input_data: Original raw dict (for reliability indicator lookups)
        explain: Whether to include SHAP explanation
    """
    pipeline = _load_pipeline()
    metrics  = _load_metrics()

    pred = float(pipeline.predict(input_df)[0])
    pred = max(pred, 0)  # prices can't be negative

    # Reliability indicator FIRST so uncertainty uses the context-appropriate error metric
    reliability = None
    if input_data:
        try:
            reliability = _reliability_indicator(input_data, pred, metrics)
        except Exception as e:
            log.warning(f"Reliability indicator failed: {e}")
            reliability = {"tier": "Unknown", "explanation": str(e)}

    holdout_m = metrics.get("holdout_metrics", {})
    holdout_mae  = holdout_m.get("mae")
    holdout_r2   = holdout_m.get("r2")
    holdout_rmse = holdout_m.get("rmse")
    gkf_mae      = metrics.get("validation_mae")
    gkf_r2       = metrics.get("validation_r2")
    gkf_rmse     = metrics.get("validation_rmse")

    loc_cnt = (reliability or {}).get("locality_count", 0)
    is_unseen_or_sparse = loc_cnt < 3

    # Priority 3D: For unseen/sparse localities (<3 training records), use GroupKFold validation error;
    # for well-represented localities (N >= 3), use independent Holdout Test error.
    if is_unseen_or_sparse and gkf_mae:
        mae_for_interval = float(gkf_mae)
        report_mae = float(gkf_mae)
        report_r2 = float(gkf_r2 or 0)
        report_rmse = float(gkf_rmse or 0)
        mult = 1.75 if loc_cnt == 0 else 1.5
        half_width = mult * mae_for_interval
        uncertainty_basis = "Locality GroupKFold MAE"
        if loc_cnt == 0:
            uncertainty_explanation = (
                f"Unseen locality (0 exact training records — exact-locality accuracy cannot be claimed): "
                f"widened indicative spread uses ±{mult:.2f}× Locality GroupKFold MAE (±₹{half_width:,.0f}/sq.ft; "
                f"GroupKFold MAE=₹{gkf_mae:,.2f}/sq.ft). Verify locally before transacting."
            )
        else:
            uncertainty_explanation = (
                f"Sparse locality ({loc_cnt} exact training record(s) < 3): indicative spread uses "
                f"±1.5× Locality GroupKFold MAE (±₹{half_width:,.0f}/sq.ft; GroupKFold MAE=₹{gkf_mae:,.2f}/sq.ft). "
                "Not a statistically calibrated confidence interval."
            )
    else:
        mae_for_interval = float(holdout_mae or gkf_mae or pred * 0.20)
        report_mae = float(holdout_mae or metrics.get("kfold_mae") or gkf_mae or 0)
        report_r2 = float(holdout_r2 or metrics.get("kfold_r2") or gkf_r2 or 0)
        report_rmse = float(holdout_rmse or gkf_rmse or 0)
        half_width = 1.5 * mae_for_interval
        uncertainty_basis = "Independent Holdout MAE"
        uncertainty_explanation = (
            f"Represented locality ({loc_cnt} training records >= 3): indicative spread uses "
            f"±1.5× Independent Holdout Test MAE (±₹{half_width:,.0f}/sq.ft; Holdout MAE=₹{report_mae:,.2f}/sq.ft). "
            "Not a statistically calibrated confidence interval."
        )

    low  = max(pred - half_width, pred * (0.55 if loc_cnt == 0 else 0.65))
    high = pred + half_width

    # Data quality label
    n_records = metrics.get("training_records", 0)
    if n_records < 100 or report_r2 < 0.5:
        quality = "Low"
    elif n_records < 300 or report_r2 < 0.65:
        quality = "Moderate"
    else:
        quality = "Good"

    result = {
        "predicted_price_per_sqft": round(pred, 2),
        "range_low_per_sqft":       round(low,  2),
        "range_high_per_sqft":      round(high, 2),
        "uncertainty_mae_used":     round(mae_for_interval, 2),
        "uncertainty_basis":        uncertainty_basis,
        "uncertainty_explanation":  uncertainty_explanation,
        "model_used":               metrics.get("best_model", "ExtraTreesRegressor"),
        "total_dataset_records":    metrics.get("total_records_in_file", 1050),
        "training_records":         n_records,
        "holdout_records":          (metrics.get("train_test_split") or {}).get("test_size", 158),
        "holdout_mae":              round(float(holdout_mae), 2) if holdout_mae else None,
        "holdout_r2":               round(float(holdout_r2), 4) if holdout_r2 else None,
        "validation_mae":           round(report_mae,  2) if report_mae else 0,
        "validation_rmse":          round(report_rmse, 2) if report_rmse else 0,
        "validation_r2":            round(report_r2,   4) if report_r2  else 0,
        "kfold_mae":                round(metrics.get("kfold_mae", 0), 2),
        "kfold_r2":                 round(metrics.get("kfold_r2", 0), 4),
        "groupkfold_mae":           round(metrics.get("validation_mae", 0), 2),
        "groupkfold_r2":            round(metrics.get("validation_r2", 0), 4),
        "data_quality":             quality,
        "trained_at":               metrics.get("trained_at", "Unknown"),
        "note": (
            "Indicative estimate based on available comparable/historical data. "
            "This is NOT a certified valuation and the spread is NOT a statistically calibrated CI. "
            "Consult a registered valuer for legal purposes."
        ),
    }

    if reliability:
        result["reliability_indicator"] = reliability
        result["comparable_records_count"] = reliability.get("locality_count", 0)
        result["stratum_records_count"]    = reliability.get("stratum_count", 0)
        result["locality_median_psf"]      = reliability.get("locality_median_psf")
        result["locality_p25_psf"]         = reliability.get("locality_p25_psf")
        result["locality_p75_psf"]         = reliability.get("locality_p75_psf")

    # Include SHAP top features if available
    shap_info = metrics.get("shap_explainability")
    if shap_info and shap_info.get("shap_top_features"):
        result["shap_top_features"] = shap_info["shap_top_features"][:5]

    # Individual prediction explanation if requested
    if explain:
        try:
            from ml.explain import explain_prediction
            result["explanation"] = explain_prediction(pipeline, input_df)
        except Exception as e:
            log.warning(f"Failed to explain prediction: {e}")
            result["explanation"] = {"shap_available": False, "error": str(e)}

    return result


def get_model_metrics() -> dict:
    """Return model metrics for the /api/model/metrics endpoint."""
    try:
        metrics     = _load_metrics()
        model_ready = os.path.exists(MODEL_PATH)
        return {"model_ready": model_ready, **metrics}
    except Exception as e:
        return {"model_ready": False, "error": str(e)}


def reload_model():
    """Force reload of model and metrics (called after retraining via API)."""
    global _pipeline, _metrics, _train_df
    _pipeline = None
    _metrics  = None
    _train_df = None
    _load_pipeline()
    _load_metrics()
    log.info("Model and metrics cache refreshed.")
