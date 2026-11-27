"""
Lightweight ML metadata, OS heap reclamation, and isolated ML subprocess runner.
Intentionally avoids importing numpy, pandas, scikit-learn, joblib, or shap
so the long-lived Gunicorn web worker maintains a minimal baseline memory footprint.
"""
import ctypes
import gc
import json
import logging
import os
import subprocess
import sys
import threading
from typing import Any, Dict, List

log = logging.getLogger(__name__)

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(MODEL_DIR)
MODEL_PATH = os.path.join(MODEL_DIR, "model_pipeline.joblib")
METRICS_PATH = os.path.join(MODEL_DIR, "model_metrics.json")

_metrics_cache: dict | None = None
_comp_rows_cache: List[Dict[str, Any]] | None = None
_COMP_ROWS_LOCK = threading.Lock()

_LAND_TYPE_ALIASES = {
    "residential": "Residential",
    "residential plot": "Residential",
    "plot": "Residential",
    "agricultural": "Agricultural/Farm",
    "agricultural/farm": "Agricultural/Farm",
    "farm": "Agricultural/Farm",
    "commercial": "Commercial",
    "industrial": "Industrial",
}


_GENERAL_URBAN_TOKENS = (
    "stage", "block", "layout", "nagar", "nagara", "puram",
    "mohalla", "colony", "enclave", "habitat", "palya",
)
_NON_URBAN_TOKENS = (
    "satellite", "peri-urban", "fringe", "corridor", "farm",
    "hobli", "village", "grama", "extension",
)
_REGION_ALIASES_BASIC = {
    "auto": "Auto",
    "urban": "Urban",
    "suburban": "Peri-urban", "peri-urban": "Peri-urban", "periurban": "Peri-urban",
    "semi-urban": "Peri-urban", "town": "Peri-urban",
    "urban/peri-urban": "Urban/Peri-urban",
    "rural": "Rural", "agricultural": "Rural", "rural/agricultural": "Rural",
}


def _derive_region_3class_row(rec: Dict[str, Any]) -> str:
    """Pure-Python equivalent of ml.preprocess.derive_region_3class for a single dict."""
    from gis.geo_utils import haversine_km

    t = canonicalize_basic("taluk", rec.get("taluk", ""))
    lt = str(rec.get("land_type", "") or "").strip()
    reg_raw = str(rec.get("region_type", "") or "").strip()
    reg = _REGION_ALIASES_BASIC.get(reg_raw.lower(), reg_raw or "Unknown")
    loc_low = str(rec.get("village_or_locality", "") or "").lower()

    dc = None
    try:
        la, lo = rec.get("latitude"), rec.get("longitude")
        if la not in (None, "") and lo not in (None, ""):
            dc = haversine_km(float(la), float(lo), 12.3052, 76.6552)
    except Exception:
        dc = None

    hosp = None
    try:
        hv = rec.get("nearest_hospital_km")
        if hv not in (None, ""):
            hosp = float(hv)
    except Exception:
        hosp = None

    if "agri" in lt.lower() or reg.lower() in ("rural", "rural/agricultural", "agricultural"):
        return "Rural"
    if reg.lower() == "urban":
        return "Urban"
    if reg.lower() in ("peri-urban", "periurban", "suburban", "semi-urban", "town"):
        return "Peri-urban"
    if t == "Mysuru":
        has_u_tok = any(tok in loc_low for tok in _GENERAL_URBAN_TOKENS)
        has_non_u = any(tok in loc_low for tok in _NON_URBAN_TOKENS)
        close_core = (dc is not None) and dc <= 6.5
        if (has_u_tok and not has_non_u) or close_core:
            return "Urban"
        if (dc is not None) and dc > 16.0:
            return "Rural"
        return "Peri-urban"
    return "Peri-urban"


def canonicalize_basic(feat: str, val: Any) -> str:
    """Zero-dependency canonicalization matching ml.preprocess.canonicalize_categorical."""
    if val in (None, ""):
        return "Unknown"
    s = str(val).strip()
    if not s:
        return "Unknown"
    if feat == "taluk":
        from gis.geo_utils import normalize_taluk
        return normalize_taluk(s)
    if feat == "land_type":
        return _LAND_TYPE_ALIASES.get(s.lower(), s)
    return s


def load_dataset_comparables_rows() -> List[Dict[str, Any]]:
    """
    Stream only comparable-lookup columns from the dataset into compact Python dicts
    without importing numpy or pandas into the long-lived web worker.
    """
    global _comp_rows_cache
    if _comp_rows_cache is not None:
        return _comp_rows_cache
    with _COMP_ROWS_LOCK:
        if _comp_rows_cache is not None:
            return _comp_rows_cache
        metrics = _load_metrics()
        dataset_path = metrics.get("dataset_path", "")
        candidates = [
            dataset_path,
            os.path.join(MODEL_DIR, "Mysuru_Land_Evaluation_1000_Master.xlsx"),
            os.path.join(MODEL_DIR, "..", "..", "Mysuru_Land_Evaluation_1000_Master.xlsx"),
        ]
        wanted = (
            "taluk",
            "village_or_locality",
            "region_type",
            "land_type",
            "listing_type",
            "price_per_sqft",
            "land_area_sqft",
            "nearest_hospital_km",
            "latitude",
            "longitude",
        )
        wanted_set = set(wanted)
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                    rows_out: List[Dict[str, Any]] = []
                    try:
                        ws = wb.active
                        it = ws.iter_rows(values_only=True)
                        header = next(it, None) or ()
                        col_map = [(idx, str(col)) for idx, col in enumerate(header) if col in wanted_set]
                        for r in it:
                            if not r or all(v is None for v in r):
                                continue
                            rlen = len(r)
                            rec = {name: (r[idx] if idx < rlen else None) for idx, name in col_map}
                            rec["region_type"] = _derive_region_3class_row(rec)
                            rec.pop("nearest_hospital_km", None)
                            rows_out.append(rec)
                    finally:
                        wb.close()
                        del wb
                    release_os_memory()
                    _comp_rows_cache = rows_out
                    return _comp_rows_cache
                except Exception as exc:
                    log.warning("Lightweight dataset read failed from %s: %s", p, exc)
        _comp_rows_cache = []
        return _comp_rows_cache


def release_os_memory() -> None:
    """Reclaim Python objects and ask glibc (Linux) to trim freed heap arenas."""
    gc.collect()
    if sys.platform.startswith("linux"):
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass


def _load_metrics() -> dict:
    global _metrics_cache
    if _metrics_cache is None:
        if not os.path.exists(METRICS_PATH):
            return {}
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            _metrics_cache = json.load(f)
    return _metrics_cache


def invalidate_metrics_cache() -> None:
    global _metrics_cache
    _metrics_cache = None


def get_model_metrics() -> dict:
    """Return model metrics for /api/model/metrics without importing ML libraries."""
    try:
        metrics = _load_metrics()
        model_ready = os.path.exists(MODEL_PATH)
        return {"model_ready": model_ready, **metrics}
    except Exception as e:
        return {"model_ready": False, "error": str(e)}


def _linear_quantile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac)


def compute_reliability_lightweight(input_data: Dict[str, Any], pred_psf: float, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pure-Python zero-pandas equivalent of ml.predict._reliability_indicator for GET/PDF routes
    so report generation and property views never import numpy/pandas into the web worker.
    """
    import difflib
    from gis.geo_utils import normalize_locality

    taluk = canonicalize_basic("taluk", input_data.get("taluk", ""))
    locality = str(input_data.get("village_or_locality", "") or "").strip()
    loc_norm = normalize_locality(locality)
    land_type = canonicalize_basic("land_type", input_data.get("land_type", ""))
    region_type = _derive_region_3class_row({
        "taluk": taluk,
        "village_or_locality": locality,
        "region_type": input_data.get("region_type", ""),
        "land_type": land_type,
        "latitude": input_data.get("latitude"),
        "longitude": input_data.get("longitude"),
        "nearest_hospital_km": input_data.get("nearest_hospital_km"),
    })

    rows = load_dataset_comparables_rows()
    stratum_count = 0
    taluk_count = 0
    locality_count = 0
    fuzzy_match_name = None
    fuzzy_match_count = 0
    locality_median = None
    locality_p25 = None
    locality_p75 = None

    n_train_total = int(metrics.get("training_records", 892) or 892)
    n_file_total = int(metrics.get("total_records_in_file", 1050) or 1050)

    def _psf_list(r_list: List[Dict[str, Any]]) -> List[float]:
        vals = []
        for r in r_list:
            try:
                v = float(r.get("price_per_sqft"))
                if v > 0:
                    vals.append(v)
            except Exception:
                pass
        vals.sort()
        return vals

    if rows:
        taluk_rows = [r for r in rows if canonicalize_basic("taluk", r.get("taluk")) == taluk or str(r.get("taluk") or "").strip() == taluk]
        taluk_count = len(taluk_rows)
        stratum_count = sum(
            1 for r in taluk_rows
            if (canonicalize_basic("land_type", r.get("land_type")) == land_type or str(r.get("land_type") or "").strip() == land_type)
            and (str(r.get("region_type") or "").strip() == region_type)
        )

        loc_rows = [r for r in rows if loc_norm and normalize_locality(str(r.get("village_or_locality") or "")) == loc_norm]
        locality_count = len(loc_rows)

        if locality_count == 0 and loc_norm:
            pool = taluk_rows if taluk_rows else rows
            unique_norms = {
                normalize_locality(str(r.get("village_or_locality") or "")): str(r.get("village_or_locality") or "")
                for r in pool
                if normalize_locality(str(r.get("village_or_locality") or ""))
            }
            matches = difflib.get_close_matches(loc_norm, list(unique_norms.keys()), n=1, cutoff=0.78)
            if matches:
                matched_norm = matches[0]
                fuzzy_match_name = unique_norms[matched_norm]
                fuzzy_rows = [r for r in pool if normalize_locality(str(r.get("village_or_locality") or "")) == matched_norm]
                fuzzy_match_count = len(fuzzy_rows)
                fuzzy_same = [r for r in fuzzy_rows if (canonicalize_basic("land_type", r.get("land_type")) == land_type or str(r.get("land_type") or "").strip() == land_type)]
                psfs = _psf_list(fuzzy_same if fuzzy_same else fuzzy_rows)
                if psfs:
                    locality_median = _linear_quantile(psfs, 0.50)
                    locality_p25 = _linear_quantile(psfs, 0.25)
                    locality_p75 = _linear_quantile(psfs, 0.75)
        elif locality_count > 0:
            loc_same = [r for r in loc_rows if (canonicalize_basic("land_type", r.get("land_type")) == land_type or str(r.get("land_type") or "").strip() == land_type)]
            psfs = _psf_list(loc_same if loc_same else loc_rows)
            if psfs:
                locality_median = _linear_quantile(psfs, 0.50)
                locality_p25 = _linear_quantile(psfs, 0.25)
                locality_p75 = _linear_quantile(psfs, 0.75)

    effective_loc_count = locality_count if locality_count > 0 else fuzzy_match_count
    statistically_reliable_median = effective_loc_count >= 3

    kfold_r2 = float(metrics.get("kfold_r2", 0.8573) or 0.8573)
    gkf_r2 = float(metrics.get("validation_r2", 0.7559) or 0.7559)
    gkf_mae = float(metrics.get("validation_mae", 566.74) or 566.74)
    holdout_r2 = float((metrics.get("holdout_metrics") or {}).get("r2", 0.8695))
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
        tier, tier_color = "High", "green"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Holdout R²={holdout_r2:.4f} (variance explained; not % accuracy)."
    elif effective_loc_count >= 2 or (effective_loc_count == 0 and stratum_count >= 25 and gkf_r2 >= 0.70):
        tier, tier_color = "Moderate", "orange"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Indicative benchmark only (not guaranteed market value)."
    elif effective_loc_count == 1 or (taluk_count >= 10 and gkf_r2 >= 0.65):
        tier, tier_color = "Low", "darkorange"
        explanation = f"{loc_clause}. {sample_clause} {regional_clause} Single-record or sparse local coverage — treat estimate strictly as a coarse regional benchmark and verify locally."
    else:
        tier, tier_color = "Very Low", "red"
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


def run_ml_worker(
    payload_data: Dict[str, Any],
    mode: str = "evaluate",
    explain: bool = True,
    timeout_s: int = 120,
) -> Dict[str, Any]:
    """
    Execute ML preprocessing, ExtraTreesRegressor prediction, reliability stats,
    and SHAP TreeExplainer inside a short-lived isolated Python subprocess so
    scikit-learn/SHAP memory (~300 MB peak) is guaranteed returned to the OS on exit.
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. "
            "Run: python backend/ml/train.py --dataset <path_to_dataset>"
        )

    release_os_memory()

    env = os.environ.copy()
    env.setdefault("MALLOC_ARENA_MAX", "2")
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_NUM_THREADS", "1")
    env["ML_ISOLATED_WORKER"] = "1"

    req_json = json.dumps({
        "mode": mode,
        "explain": bool(explain),
        "input_data": payload_data,
    })

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ml.worker"],
            input=req_json,
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR,
            env=env,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"ML worker timed out after {timeout_s}s") from exc

    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        if "FileNotFoundError" in err_tail:
            raise FileNotFoundError(err_tail)
        raise RuntimeError(f"ML worker failed (code {proc.returncode}): {err_tail}")

    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("ML worker returned empty output")

    parsed = json.loads(lines[-1])
    if not parsed.get("ok"):
        err_msg = parsed.get("error", "Unknown ML worker error")
        if parsed.get("error_type") == "FileNotFoundError":
            raise FileNotFoundError(err_msg)
        raise RuntimeError(err_msg)

    return parsed["result"]
