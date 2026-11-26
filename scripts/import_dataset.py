"""
Dataset import script.
Imports the Mysuru land dataset into the database and validates data quality.

Usage:
    python scripts/import_dataset.py --dataset "path/to/Mysuru_Land_Evaluation_Final (7).xlsx"

Must be run from the smart-land-eval directory.
"""
import os
import sys
import json
import argparse
import logging
from datetime import datetime

import pandas as pd
import numpy as np

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app import create_app
from models import db, DatasetRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REQUIRED_COLS = [
    "record_id", "district", "taluk", "village_or_locality",
    "land_area_sqft", "asking_price_inr", "price_per_sqft",
    "latitude", "longitude",
]


def load_dataset(path: str) -> pd.DataFrame:
    if path.endswith(".xlsx") or path.endswith(".xls"):
        df = pd.read_excel(path, engine="openpyxl")
    else:
        df = pd.read_csv(path)
    return df


def validate_dataset(df: pd.DataFrame) -> dict:
    report = {
        "total_rows": len(df),
        "columns": df.columns.tolist(),
        "missing_required": [],
        "missing_values": {},
        "duplicate_rows": 0,
        "invalid_coordinates": 0,
        "invalid_prices": 0,
        "warnings": [],
    }

    # Check required columns
    for col in REQUIRED_COLS:
        if col not in df.columns:
            report["missing_required"].append(col)

    if report["missing_required"]:
        report["warnings"].append(f"Missing required columns: {report['missing_required']}")

    # Missing values per column
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing > 0:
            report["missing_values"][col] = int(missing)

    # Duplicates
    if "record_id" in df.columns:
        report["duplicate_rows"] = int(df.duplicated(subset=["record_id"]).sum())

    # Invalid coordinates
    if "latitude" in df.columns and "longitude" in df.columns:
        bad_coords = df[
            (df["latitude"].notna() & ((df["latitude"] < 11.5) | (df["latitude"] > 13.5))) |
            (df["longitude"].notna() & ((df["longitude"] < 75.5) | (df["longitude"] > 77.5)))
        ]
        report["invalid_coordinates"] = len(bad_coords)
        if len(bad_coords) > 0:
            report["warnings"].append(f"{len(bad_coords)} records with coordinates outside Mysuru district bounds")

    # Invalid prices
    if "price_per_sqft" in df.columns:
        bad_prices = df[df["price_per_sqft"].notna() & (df["price_per_sqft"] <= 0)]
        report["invalid_prices"] = len(bad_prices)

    return report


def import_records(df: pd.DataFrame, app) -> dict:
    imported = 0
    skipped = 0
    errors = []

    def safe(val, typ=str, default=None):
        try:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return typ(val)
        except Exception:
            return default

    with app.app_context():
        for _, row in df.iterrows():
            record_id = safe(row.get("record_id"), str)
            if not record_id:
                skipped += 1
                continue

            # Skip if already imported
            existing = DatasetRecord.query.filter_by(record_id=record_id).first()
            if existing:
                skipped += 1
                continue

            try:
                rec = DatasetRecord(
                    record_id=record_id,
                    district=safe(row.get("district"), str, "Mysuru"),
                    taluk=safe(row.get("taluk"), str),
                    village_or_locality=safe(row.get("village_or_locality"), str),
                    region_type=safe(row.get("region_type"), str),
                    land_type=safe(row.get("land_type"), str),
                    listing_type=safe(row.get("listing_type"), str),
                    land_area_sqft=safe(row.get("land_area_sqft"), float),
                    asking_price_inr=safe(row.get("asking_price_inr"), float),
                    price_per_sqft=safe(row.get("price_per_sqft"), float),
                    price_per_acre=safe(row.get("price_per_acre"), float),
                    latitude=safe(row.get("latitude"), float),
                    longitude=safe(row.get("longitude"), float),
                    coordinate_status=safe(row.get("coordinate_status"), str),
                    nearest_school_km=safe(row.get("nearest_school_km"), float),
                    nearest_hospital_km=safe(row.get("nearest_hospital_km"), float),
                    nearest_market_km=safe(row.get("nearest_market_km"), float),
                    nearest_supermarket_km=safe(row.get("nearest_supermarket_km"), float),
                    nearest_bus_stop_km=safe(row.get("nearest_bus_stop_km"), float),
                    nearest_railway_station_km=safe(row.get("nearest_railway_station_km"), float),
                    nearest_bank_km=safe(row.get("nearest_bank_km"), float),
                    nearest_pharmacy_km=safe(row.get("nearest_pharmacy_km"), float),
                    school_count_3km=safe(row.get("school_count_3km"), int, 0),
                    hospital_count_3km=safe(row.get("hospital_count_3km"), int, 0),
                    bank_count_3km=safe(row.get("bank_count_3km"), int, 0),
                    bus_stop_count_3km=safe(row.get("bus_stop_count_3km"), int, 0),
                    distance_to_main_road_km=safe(row.get("distance_to_main_road_km"), float),
                    distance_to_highway_km=safe(row.get("distance_to_highway_km"), float),
                    distance_to_nearest_waterbody_km=safe(row.get("distance_to_nearest_waterbody_km"), float),
                    road_width_ft=safe(row.get("road_width_ft"), float),
                    road_quality=safe(row.get("road_quality"), str),
                    street_light_available=safe(row.get("street_light_available"), str),
                    public_transport_available=safe(row.get("public_transport_available"), str),
                    electricity_available=safe(row.get("electricity_available_locality"), str),
                    locality_water_supply=safe(row.get("locality_water_supply"), str),
                    water_source_type=safe(row.get("water_source_type"), str),
                    property_source=safe(row.get("property_source"), str),
                    property_source_url=safe(row.get("property_source_url"), str),
                    source_date=safe(row.get("source_date"), str),
                    price_score_100=safe(row.get("price_score_100"), float),
                    location_score_100=safe(row.get("location_score_100"), float),
                    facility_score_100=safe(row.get("facility_score_100"), float),
                    infrastructure_score_100=safe(row.get("infrastructure_score_100"), float),
                    utility_score_100=safe(row.get("utility_score_100"), float),
                    environment_score_100=safe(row.get("environment_score_100"), float),
                    overall_land_evaluation_score_100=safe(row.get("overall_land_evaluation_score_100"), float),
                    confidence_level=safe(row.get("confidence_level"), str),
                    data_status=safe(row.get("data_status"), str),
                )
                db.session.add(rec)
                imported += 1
            except Exception as e:
                errors.append(f"Row {record_id}: {str(e)}")
                skipped += 1

        db.session.commit()

    return {"imported": imported, "skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Import Mysuru dataset into Smart Land Evaluation DB")
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to dataset Excel/CSV file",
    )
    parser.add_argument(
        "--env",
        default="development",
        help="Flask environment (development/production)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"ERROR: Dataset not found: {args.dataset}")
        sys.exit(1)

    print(f"\nLoading dataset: {args.dataset}")
    df = load_dataset(args.dataset)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")

    # Validate
    print("\nValidating dataset...")
    report = validate_dataset(df)
    print(f"  Total rows      : {report['total_rows']}")
    print(f"  Missing required: {report['missing_required'] or 'None'}")
    print(f"  Duplicate rows  : {report['duplicate_rows']}")
    print(f"  Invalid coords  : {report['invalid_coordinates']}")
    print(f"  Invalid prices  : {report['invalid_prices']}")
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"  ⚠ WARNING: {w}")

    if report["missing_required"]:
        print("\nERROR: Missing required columns. Cannot import.")
        sys.exit(1)

    # Import
    print("\nImporting into database...")
    app = create_app(args.env)
    with app.app_context():
        db.create_all()
    result = import_records(df, app)

    print(f"\nImport complete:")
    print(f"  Imported : {result['imported']}")
    print(f"  Skipped  : {result['skipped']}")
    if result["errors"]:
        print(f"  Errors   :")
        for e in result["errors"][:10]:
            print(f"    {e}")

    # Save quality report
    quality_report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data_quality_report.json"
    )
    with open(quality_report_path, "w") as f:
        json.dump({**report, **result, "timestamp": datetime.utcnow().isoformat()}, f, indent=2)
    print(f"\nData quality report saved: {quality_report_path}")


if __name__ == "__main__":
    main()
