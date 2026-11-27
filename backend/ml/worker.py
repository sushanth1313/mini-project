"""
Isolated short-lived subprocess worker for ML price prediction and SHAP explanation.
Invoked by ml.lightweight.run_ml_worker via `python -m ml.worker`.
"""
import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr,
)


def _sanitize_json(obj):
    import math
    if isinstance(obj, dict):
        return {str(k): _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            val = obj.item()
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return None
            return val
        if isinstance(obj, np.ndarray):
            return _sanitize_json(obj.tolist())
    except Exception:
        pass
    return obj


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"ok": False, "error": "Empty stdin payload"}))
        return 1

    try:
        req = json.loads(raw)
        mode = req.get("mode", "evaluate")
        explain = bool(req.get("explain", True))
        raw_input = dict(req.get("input_data") or {})

        from ml.preprocess import prepare_single_input
        from ml.predict import impute_missing_gis_features, predict_price_per_sqft

        if mode == "evaluate":
            from services.classification_service import map_land_type_for_ml
            ml_input_dict = dict(raw_input)
            if ml_input_dict.get("village_or_locality") in (
                "Locality Requires Verification",
                "Locality could not be confidently resolved",
            ):
                ml_input_dict["village_or_locality"] = "Unknown"
            ml_input_dict["land_type"] = map_land_type_for_ml(ml_input_dict.get("land_type"))
            ml_input_dict = impute_missing_gis_features(ml_input_dict)
            input_df = prepare_single_input(ml_input_dict)
            res = predict_price_per_sqft(input_df, input_data=ml_input_dict, explain=explain)
        else:
            input_df = prepare_single_input(raw_input)
            res = predict_price_per_sqft(input_df, explain=explain)

        print(json.dumps({"ok": True, "result": _sanitize_json(res)}, allow_nan=False))
        return 0
    except FileNotFoundError as fnf:
        print(json.dumps({"ok": False, "error_type": "FileNotFoundError", "error": str(fnf)}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
