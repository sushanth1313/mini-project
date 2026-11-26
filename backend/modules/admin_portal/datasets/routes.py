"""
Dataset Management Module (Mysuru 7 Taluks):
- GET  /api/admin/datasets
- GET  /api/admin/datasets/<dataset_id>
- POST /api/admin/datasets/upload
- POST /api/admin/datasets/<dataset_id>/validate
- POST /api/admin/datasets/<dataset_id>/clean
- GET  /api/admin/datasets/<dataset_id>/download
Validates required columns, missing values, duplicates, invalid data types,
price outliers, coordinates within Mysuru District bounding box, and taluk consistency.
Never mutates raw records in place; creates a new versioned cleaned dataset.
"""
import csv
import io
import uuid
from collections import Counter
from datetime import datetime, timezone

from ..compat_flask import Blueprint, request, jsonify, g, Response
from ..config import MYSURU_TALUKS, REQUIRED_DATASET_COLUMNS, MYSURU_BOUNDS
from ..database import db_instance
from ..auth.security import require_permission
from ..audit.service import record_audit_log

datasets_bp = Blueprint("admin_datasets", __name__, url_prefix="/api/admin/datasets")

def analyze_csv_rows(rows: list, fieldnames: list) -> dict:
    missing_cols = [c for c in REQUIRED_DATASET_COLUMNS if c not in fieldnames]
    missing_values_count = 0
    duplicate_records_count = 0
    invalid_data_types_count = 0
    suspicious_price_outliers_count = 0
    invalid_coordinates_count = 0
    district_taluk_inconsistencies_count = 0
    validation_errors = []
    seen_ids = set()
    taluk_counter = Counter()
    clean_rows = []

    if missing_cols:
        validation_errors.append(f"Missing required columns: {', '.join(missing_cols)}")

    for idx, row in enumerate(rows, start=1):
        row_has_issue = False
        # Check missing values
        if any(str(row.get(col, "")).strip() == "" for col in fieldnames):
            missing_values_count += 1
            row_has_issue = True
            if len(validation_errors) < 25:
                validation_errors.append(f"Row {idx}: Contains empty/missing field values.")

        rec_id = str(row.get("record_id", "")).strip()
        if rec_id in seen_ids:
            duplicate_records_count += 1
            row_has_issue = True
            if len(validation_errors) < 25:
                validation_errors.append(f"Row {idx}: Duplicate record_id '{rec_id}'.")
        elif rec_id:
            seen_ids.add(rec_id)

        district = str(row.get("district", "")).strip()
        taluk = str(row.get("taluk", "")).strip()
        if district != "Mysuru" or taluk not in MYSURU_TALUKS:
            district_taluk_inconsistencies_count += 1
            row_has_issue = True
            if len(validation_errors) < 25:
                validation_errors.append(
                    f"Row {idx}: District/Taluk inconsistency ('{district}' / '{taluk}'). Must be Mysuru District and one of the 7 official taluks."
                )
        else:
            taluk_counter[taluk] += 1

        try:
            area = float(row.get("land_area_sqft", 0))
            lat = float(row.get("latitude", 0))
            lng = float(row.get("longitude", 0))
            pps = float(row.get("price_per_sqft_inr", 0))
            tot = float(row.get("total_price_inr", 0))

            if area <= 0 or pps <= 0 or tot <= 0:
                invalid_data_types_count += 1
                row_has_issue = True

            # Check Mysuru District coordinate bounding box
            if not (MYSURU_BOUNDS["lat_min"] <= lat <= MYSURU_BOUNDS["lat_max"] and
                    MYSURU_BOUNDS["lng_min"] <= lng <= MYSURU_BOUNDS["lng_max"]):
                invalid_coordinates_count += 1
                row_has_issue = True
                if len(validation_errors) < 25:
                    validation_errors.append(f"Row {idx}: Coordinates ({lat}, {lng}) fall outside Mysuru District bounds.")

            # Suspicious price outlier check (< 50 INR/sqft or > 45,000 INR/sqft)
            if pps < 50 or pps > 45000:
                suspicious_price_outliers_count += 1
                row_has_issue = True
                if len(validation_errors) < 25:
                    validation_errors.append(f"Row {idx}: Suspicious price outlier ({pps} INR/sqft).")

        except (ValueError, TypeError):
            invalid_data_types_count += 1
            row_has_issue = True
            if len(validation_errors) < 25:
                validation_errors.append(f"Row {idx}: Non-numeric value in area, coordinate, or price columns.")

        if not row_has_issue and not missing_cols:
            clean_rows.append(row)

    total_issues = (
        len(missing_cols)
        + missing_values_count
        + duplicate_records_count
        + invalid_data_types_count
        + suspicious_price_outliers_count
        + invalid_coordinates_count
        + district_taluk_inconsistencies_count
    )

    return {
        "missing_columns": missing_cols,
        "quality_summary": {
            "missing_values_count": missing_values_count,
            "duplicate_records_count": duplicate_records_count,
            "invalid_data_types_count": invalid_data_types_count,
            "suspicious_price_outliers_count": suspicious_price_outliers_count,
            "invalid_coordinates_count": invalid_coordinates_count,
            "district_taluk_inconsistencies_count": district_taluk_inconsistencies_count,
            "taluk_distribution": {t: taluk_counter.get(t, 0) for t in MYSURU_TALUKS}
        },
        "validation_errors": validation_errors,
        "is_valid": total_issues == 0 and len(rows) > 0,
        "clean_rows": clean_rows
    }

@datasets_bp.route("", methods=["GET"])
@require_permission("datasets:view")
def list_datasets():
    datasets = db_instance["datasets"].find({}, {"_id": 0, "raw_rows": 0})
    datasets.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
    return jsonify({
        "datasets": datasets,
        "supported_taluks": MYSURU_TALUKS,
        "required_columns": REQUIRED_DATASET_COLUMNS
    }), 200

@datasets_bp.route("/<dataset_id>", methods=["GET"])
@require_permission("datasets:view")
def get_dataset(dataset_id):
    ds = db_instance["datasets"].find_one({"dataset_id": dataset_id}, {"_id": 0, "raw_rows": 0})
    if not ds:
        return jsonify({"error": "Dataset version not found.", "code": "NOT_FOUND"}), 404
    return jsonify({"dataset": ds}), 200

@datasets_bp.route("/upload", methods=["POST"])
@require_permission("datasets:upload")
def upload_dataset():
    data = request.get_json(silent=True) or {}
    filename = (data.get("filename") or "mysuru_uploaded_dataset.csv").strip()
    version_tag = (data.get("version_tag") or f"v{datetime.now(timezone.utc).strftime('%Y%m%d.%H%M')}-raw").strip()
    csv_content = data.get("csv_content") or ""

    if not filename.lower().endswith(".csv") or not csv_content.strip():
        return jsonify({"error": "A valid .csv filename and non-empty csv_content are required.", "code": "VALIDATION_ERROR"}), 400

    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    fieldnames = reader.fieldnames or []
    rows = list(reader)

    if not rows:
        return jsonify({"error": "Uploaded CSV contains 0 data rows.", "code": "EMPTY_DATASET"}), 400

    analysis = analyze_csv_rows(rows, fieldnames)
    dataset_id = f"DS-MYS-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ds_doc = {
        "dataset_id": dataset_id,
        "version_tag": version_tag,
        "filename": filename,
        "uploaded_by": g.current_admin["admin_id"],
        "uploaded_at": now_iso,
        "row_count": len(rows),
        "column_count": len(fieldnames),
        "columns": fieldnames,
        "parent_dataset_id": None,
        "is_cleaned_version": False,
        "validation_status": "VALIDATED" if analysis["is_valid"] else "ISSUES_DETECTED",
        "ready_for_training": analysis["is_valid"],
        "quality_summary": analysis["quality_summary"],
        "validation_errors": analysis["validation_errors"],
        "sample_rows": rows[:10],
        "raw_rows": rows
    }
    db_instance["datasets"].insert_one(ds_doc)

    record_audit_log(
        action="DATASET_UPLOADED",
        resource=f"datasets/{dataset_id}",
        result="SUCCESS",
        details=f"Uploaded dataset '{filename}' ({len(rows)} rows, status={ds_doc['validation_status']})."
    )
    safe_doc = {k: v for k, v in ds_doc.items() if k not in ("_id", "raw_rows")}
    return jsonify({"dataset": safe_doc}), 201

@datasets_bp.route("/<dataset_id>/validate", methods=["POST"])
@require_permission("datasets:validate")
def revalidate_dataset(dataset_id):
    ds = db_instance["datasets"].find_one({"dataset_id": dataset_id})
    if not ds:
        return jsonify({"error": "Dataset not found.", "code": "NOT_FOUND"}), 404

    if ds.get("raw_rows"):
        analysis = analyze_csv_rows(ds["raw_rows"], ds.get("columns", []))
        status = "VALIDATED" if analysis["is_valid"] else "ISSUES_DETECTED"
        ready = analysis["is_valid"]
        db_instance["datasets"].update_one(
            {"dataset_id": dataset_id},
            {"$set": {
                "validation_status": status,
                "ready_for_training": ready,
                "quality_summary": analysis["quality_summary"],
                "validation_errors": analysis["validation_errors"]
            }}
        )
    updated = db_instance["datasets"].find_one({"dataset_id": dataset_id}, {"_id": 0, "raw_rows": 0})
    record_audit_log(
        action="DATASET_VALIDATED",
        resource=f"datasets/{dataset_id}",
        result="SUCCESS",
        details=f"Validated dataset {dataset_id}: status={updated.get('validation_status')}."
    )
    return jsonify({"dataset": updated}), 200

@datasets_bp.route("/<dataset_id>/clean", methods=["POST"])
@require_permission("datasets:clean")
def create_cleaned_dataset_version(dataset_id):
    """
    Never modifies or deletes original dataset records.
    Creates a separate cleaned dataset version linked via parent_dataset_id.
    """
    orig = db_instance["datasets"].find_one({"dataset_id": dataset_id})
    if not orig:
        return jsonify({"error": "Source dataset not found.", "code": "NOT_FOUND"}), 404

    if orig.get("missing_columns"):
        return jsonify({"error": "Cannot auto-clean dataset missing required schema columns.", "code": "SCHEMA_ERROR"}), 400

    new_id = f"{dataset_id}-CLN-{uuid.uuid4().hex[:4].upper()}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if orig.get("raw_rows"):
        analysis = analyze_csv_rows(orig["raw_rows"], orig.get("columns", []))
        clean_rows = analysis["clean_rows"]
        if not clean_rows:
            return jsonify({"error": "No valid rows remained after filtering invalid records.", "code": "EMPTY_AFTER_CLEAN"}), 400
        clean_analysis = analyze_csv_rows(clean_rows, orig.get("columns", []))
        new_row_count = len(clean_rows)
        new_quality = clean_analysis["quality_summary"]
        sample_rows = clean_rows[:10]
    else:
        # Derived from seeded metadata when raw_rows are external
        q = orig.get("quality_summary", {})
        removed = (
            q.get("missing_values_count", 0)
            + q.get("duplicate_records_count", 0)
            + q.get("invalid_data_types_count", 0)
            + q.get("suspicious_price_outliers_count", 0)
            + q.get("invalid_coordinates_count", 0)
            + q.get("district_taluk_inconsistencies_count", 0)
        )
        new_row_count = max(1, orig.get("row_count", 100) - removed)
        new_quality = {
            "missing_values_count": 0,
            "duplicate_records_count": 0,
            "invalid_data_types_count": 0,
            "suspicious_price_outliers_count": 0,
            "invalid_coordinates_count": 0,
            "district_taluk_inconsistencies_count": 0,
            "taluk_distribution": q.get("taluk_distribution", {})
        }
        clean_rows = []
        sample_rows = orig.get("sample_rows", [])

    cleaned_doc = {
        "dataset_id": new_id,
        "version_tag": f"{orig.get('version_tag', 'v1')}-cleaned",
        "filename": orig.get("filename", "dataset.csv").replace(".csv", "_cleaned.csv"),
        "uploaded_by": g.current_admin["admin_id"],
        "uploaded_at": now_iso,
        "row_count": new_row_count,
        "column_count": orig.get("column_count", 10),
        "columns": orig.get("columns", REQUIRED_DATASET_COLUMNS),
        "parent_dataset_id": dataset_id,
        "is_cleaned_version": True,
        "validation_status": "VALIDATED",
        "ready_for_training": True,
        "quality_summary": new_quality,
        "validation_errors": [],
        "sample_rows": sample_rows,
        "raw_rows": clean_rows
    }
    db_instance["datasets"].insert_one(cleaned_doc)

    record_audit_log(
        action="DATASET_CLEANED_VERSION_CREATED",
        resource=f"datasets/{new_id}",
        result="SUCCESS",
        details=f"Created cleaned dataset version {new_id} ({new_row_count} rows) from parent {dataset_id} without altering original records."
    )
    safe_doc = {k: v for k, v in cleaned_doc.items() if k not in ("_id", "raw_rows")}
    return jsonify({
        "cleaned_dataset": safe_doc,
        "original_dataset_preserved": True
    }), 201

@datasets_bp.route("/<dataset_id>/download", methods=["GET"])
@require_permission("datasets:download")
def download_dataset(dataset_id):
    ds = db_instance["datasets"].find_one({"dataset_id": dataset_id})
    if not ds:
        return jsonify({"error": "Dataset not found.", "code": "NOT_FOUND"}), 404

    output = io.StringIO()
    cols = ds.get("columns", REQUIRED_DATASET_COLUMNS)
    writer = csv.DictWriter(output, fieldnames=cols)
    writer.writeheader()
    rows_to_write = ds.get("raw_rows") or ds.get("sample_rows") or []
    for r in rows_to_write:
        writer.writerow({k: r.get(k, "") for k in cols})

    record_audit_log(
        action="DATASET_DOWNLOADED",
        resource=f"datasets/{dataset_id}",
        result="SUCCESS",
        details=f"Downloaded CSV export for dataset {dataset_id} ({ds.get('version_tag')})."
    )
    return Response(
        output.getvalue(),
        status=200,
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f"attachment; filename={ds.get('filename', 'dataset.csv')}"
        },
        mimetype="text/csv"
    )
