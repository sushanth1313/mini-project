"""
Centralized Configuration for Smart Land Valuation System — Admin Portal.
Reads environment variables so that production deployments use live SQLite + runtime state.
"""
import os

MYSURU_TALUKS = [
    "Mysuru",
    "Nanjangud",
    "H.D. Kote",
    "Periyapatna",
    "Hunsur",
    "K.R. Nagar",
    "T. Narasipura",
]

PROPERTY_TYPES = [
    "Residential Plot",
    "Agricultural Land",
    "Commercial Land",
    "Industrial Plot",
    "Mixed-Use Parcel",
]

GIS_FACILITY_CATEGORIES = [
    "Schools",
    "Hospitals",
    "Clinics",
    "Markets",
    "Supermarkets",
    "Pharmacies",
    "Bus stops",
    "Railway stations",
    "Banks",
    "Police stations",
    "ATMs",
    "Parks",
    "Waterbodies",
    "Irrigation canals",
]

DOCUMENT_CATEGORIES = [
    "Sale Deed",
    "Mother Deed",
    "RTC / Pahani",
    "Mutation Records",
    "Encumbrance Certificate",
    "Khata",
    "Land Conversion Order",
    "Layout Approval",
    "Survey Sketch",
    "Court Documents",
    "RERA Documents",
]

REQUIRED_DATASET_COLUMNS = [
    "record_id",
    "district",
    "taluk",
    "locality",
    "property_type",
    "land_area_sqft",
    "latitude",
    "longitude",
    "price_per_sqft_inr",
    "total_price_inr",
]

# Geographic bounding box for Mysuru District, Karnataka, India
MYSURU_BOUNDS = {
    "lat_min": 11.72,
    "lat_max": 12.65,
    "lng_min": 75.85,
    "lng_max": 77.15,
}


class AdminConfig:
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", os.getenv("SECRET_KEY", "mysuru-land-eval-admin-jwt-secret-key"))
    JWT_EXPIRY_MINUTES = int(os.getenv("JWT_TOKEN_EXPIRY_MINUTES", "120"))
    MONGODB_URI = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "smart_land_valuation_mysuru")
    USE_MOCK_ADAPTERS = False

    RATE_LIMIT_LOGIN_PER_MINUTE = int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
    RATE_LIMIT_API_PER_MINUTE = int(os.getenv("RATE_LIMIT_API_PER_MINUTE", "180"))
