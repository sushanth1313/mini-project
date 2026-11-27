"""
ML Pipeline: Preprocessing & Feature Engineering for Smart Land Evaluation.

Target: price_per_sqft (₹/sq.ft)

Features used:
- Categorical: taluk, village_or_locality, region_type, land_type, listing_type,
               road_quality, water_source_type
- Numerical: land_area_sqft, road_width_ft, facility distances & 3km counts,
             latitude, longitude, and engineered spatial/infrastructure features
- Binary flags (YES/NO → 1/0): street_light_available, public_transport_available,
                               electricity_available, locality_water_supply
"""
import numpy as np
import pandas as pd

CATEGORICAL_FEATURES = [
    "taluk",
    "village_or_locality",
    "region_type",
    "land_type",
    "listing_type",
    "road_quality",
    "water_source_type",
]

NUMERICAL_FEATURES = [
    "land_area_sqft",
    "log_land_area",
    "road_width_ft",
    "nearest_school_km",
    "nearest_hospital_km",
    "nearest_market_km",
    "nearest_supermarket_km",
    "nearest_pharmacy_km",
    "nearest_police_station_km",
    "nearest_bank_km",
    "nearest_bus_stop_km",
    "nearest_railway_station_km",
    "distance_to_main_road_km",
    "distance_to_highway_km",
    "distance_to_nearest_waterbody_km",
    "school_count_3km",
    "hospital_count_3km",
    "market_count_3km",
    "supermarket_count_3km",
    "bank_count_3km",
    "bus_stop_count_3km",
    "pharmacy_count_3km",
    "police_station_count_3km",
    "railway_station_count_3km",
    "waterbody_count_3km",
    "latitude",
    "longitude",
    "dist_mysuru_center_km",
    "dlat_mysuru",
    "dlon_mysuru",
    "dist_taluk_hq_km",
    "amenity_count_3km_total",
    "avg_essential_dist_km",
    "min_essential_dist_km",
    "infra_composite",
    "urban_layout_indicator",
]

BINARY_FEATURES = [
    "street_light_available",
    "public_transport_available",
    "electricity_available",
    "locality_water_supply",
]

TARGET = "price_per_sqft"

# Taluk headquarters coordinates (Mysuru district) for spatial distance features
TALUK_HQS = {
    "Mysuru": (12.3052, 76.6552),
    "Nanjangud": (12.1197, 76.6805),
    "Hunsur": (12.3045, 76.2869),
    "HD Kote": (12.0867, 76.3338),
    "T. Narasipura": (12.2121, 76.9006),
    "Periyapatna": (12.3372, 76.0987),
    "K. R. Nagar": (12.4384, 76.3827),
}


def _haversine_vec(lat1, lon1, lat2, lon2):
    """Vectorized Haversine distance in kilometres."""
    R = 6371.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return R * 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))


def encode_binary(df: pd.DataFrame) -> pd.DataFrame:
    """Convert YES/NO/TRUE/FALSE binary columns to 1/0."""
    df = df.copy()
    for col in BINARY_FEATURES:
        if col in df.columns:
            df[col] = df[col].map(
                lambda v: 1.0 if str(v).strip().upper() in ("YES", "1", "TRUE")
                else (0.0 if str(v).strip().upper() in ("NO", "0", "FALSE") else np.nan)
            )
    return df


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute prediction-safe spatial and infrastructure features from raw inputs.
    All derived features depend only on inputs available at prediction time.
    """
    df = df.copy()

    if "land_area_sqft" in df.columns:
        area = pd.to_numeric(df["land_area_sqft"], errors="coerce").clip(lower=0)
        df["log_land_area"] = np.log1p(area)
    else:
        df["log_land_area"] = np.nan

    # Spatial features from latitude/longitude
    lat = pd.to_numeric(df["latitude"], errors="coerce") if "latitude" in df.columns else pd.Series(np.nan, index=df.index)
    lon = pd.to_numeric(df["longitude"], errors="coerce") if "longitude" in df.columns else pd.Series(np.nan, index=df.index)

    df["dist_mysuru_center_km"] = _haversine_vec(lat, lon, 12.3052, 76.6552)
    df["dlat_mysuru"] = lat - 12.3052
    df["dlon_mysuru"] = lon - 76.6552

    if "taluk" in df.columns:
        hq_lats = df["taluk"].map(lambda t: TALUK_HQS.get(str(t).strip(), (12.3052, 76.6552))[0]).astype(float)
        hq_lons = df["taluk"].map(lambda t: TALUK_HQS.get(str(t).strip(), (12.3052, 76.6552))[1]).astype(float)
        df["dist_taluk_hq_km"] = _haversine_vec(lat, lon, hq_lats, hq_lons)
    else:
        df["dist_taluk_hq_km"] = np.nan

    # 3km amenity density & essential facility distance summaries
    count_cols = [
        "school_count_3km", "hospital_count_3km", "market_count_3km",
        "supermarket_count_3km", "bank_count_3km", "bus_stop_count_3km",
        "pharmacy_count_3km", "police_station_count_3km",
    ]
    avail_counts = [c for c in count_cols if c in df.columns]
    if avail_counts:
        df["amenity_count_3km_total"] = df[avail_counts].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    else:
        df["amenity_count_3km_total"] = np.nan

    dist_cols = [
        "nearest_school_km", "nearest_hospital_km", "nearest_market_km",
        "nearest_supermarket_km", "nearest_bus_stop_km", "nearest_bank_km",
        "nearest_pharmacy_km", "nearest_police_station_km",
    ]
    avail_dists = [c for c in dist_cols if c in df.columns]
    if avail_dists:
        dist_df = df[avail_dists].apply(pd.to_numeric, errors="coerce")
        df["avg_essential_dist_km"] = dist_df.mean(axis=1)
        df["min_essential_dist_km"] = dist_df.min(axis=1)
    else:
        df["avg_essential_dist_km"] = np.nan
        df["min_essential_dist_km"] = np.nan

    # Composite infrastructure score from road width and utility flags
    rw = pd.to_numeric(df["road_width_ft"], errors="coerce") if "road_width_ft" in df.columns else pd.Series(np.nan, index=df.index)
    bin_sum = sum(
        pd.to_numeric(df[c], errors="coerce").fillna(0.0) if c in df.columns else 0.0
        for c in BINARY_FEATURES
    )
    df["infra_composite"] = rw * (1.0 + 0.25 * bin_sum)

    df = derive_region_3class(df)
    return df


_GENERAL_URBAN_TOKENS = (
    "stage", "block", "layout", "nagar", "nagara", "puram",
    "mohalla", "colony", "enclave", "habitat", "palya",
)
_NON_URBAN_TOKENS = (
    "satellite", "peri-urban", "fringe", "corridor", "farm",
    "hobli", "village", "grama", "extension",
)


def derive_region_3class(df: pd.DataFrame) -> pd.DataFrame:
    """
    Separate the historical dataset's collapsed 'Urban/Peri-urban' label cleanly
    into 3 interpretable settlement tiers ('Urban', 'Peri-urban', 'Rural') alongside
    a continuous-free binary morphological/proximity feature 'urban_layout_indicator'.
    Uses zero hardcoded locality names and identical rules at training and inference.
    """
    out = df.copy()
    tiers, urban_flags = [], []
    for _, r in out.iterrows():
        t = str(r.get("taluk", "")).strip()
        lt = str(r.get("land_type", "")).strip()
        reg = str(r.get("region_type", "")).strip()
        loc_low = str(r.get("village_or_locality", "")).lower()
        dc = r.get("dist_mysuru_center_km", np.nan)
        hosp = r.get("nearest_hospital_km", np.nan)
        amen = r.get("amenity_count_3km_total", np.nan)

        if "agri" in lt.lower() or reg.lower() in ("rural", "rural/agricultural", "agricultural"):
            r3, ul = "Rural", 0.0
        elif reg.lower() == "urban":
            r3, ul = "Urban", 1.0
        elif reg.lower() in ("peri-urban", "periurban", "suburban", "semi-urban", "town"):
            r3, ul = "Peri-urban", 0.0
        elif t == "Mysuru":
            has_u_tok = any(tok in loc_low for tok in _GENERAL_URBAN_TOKENS)
            has_non_u = any(tok in loc_low for tok in _NON_URBAN_TOKENS)
            close_core = pd.notna(dc) and dc <= 6.5
            dense_urban = pd.notna(amen) and amen >= 8 and (pd.isna(hosp) or hosp <= 4.0) and not has_non_u
            if (has_u_tok and not has_non_u) or close_core or dense_urban:
                r3, ul = "Urban", 1.0
            elif pd.notna(dc) and dc > 16.0:
                r3, ul = "Rural", 0.0
            else:
                r3, ul = "Peri-urban", 0.0
        else:
            r3, ul = "Peri-urban", 0.0
        tiers.append(r3)
        urban_flags.append(ul)

    out["region_type"] = tiers
    out["urban_layout_indicator"] = urban_flags
    return out


def build_preprocessor():
    """Build sklearn ColumnTransformer for the full feature set."""
    from sklearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.impute import SimpleImputer

    numerical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    binary_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numerical_pipeline, NUMERICAL_FEATURES),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
            ("bin", binary_pipeline, BINARY_FEATURES),
        ],
        remainder="drop",
    )
    return preprocessor


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare the raw dataset dataframe for ML:
    - Rename columns if needed
    - Encode binary flags
    - Drop rows without valid target or area
    - Add engineered spatial & infrastructure features
    """
    df = df.copy()

    rename_map = {
        "electricity_available_locality": "electricity_available",
    }
    df.rename(columns=rename_map, inplace=True)

    df = encode_binary(df)
    df = df.dropna(subset=[TARGET])
    df = df[df[TARGET] > 0]
    df = df[df["land_area_sqft"] > 0]
    df = df.drop_duplicates()

    # Ensure all expected raw numerical columns exist before feature engineering
    raw_num_cols = [
        "land_area_sqft", "road_width_ft", "nearest_school_km", "nearest_hospital_km",
        "nearest_market_km", "nearest_supermarket_km", "nearest_pharmacy_km",
        "nearest_police_station_km", "nearest_bank_km", "nearest_bus_stop_km",
        "nearest_railway_station_km", "distance_to_main_road_km", "distance_to_highway_km",
        "distance_to_nearest_waterbody_km", "school_count_3km", "hospital_count_3km",
        "market_count_3km", "supermarket_count_3km", "bank_count_3km", "bus_stop_count_3km",
        "pharmacy_count_3km", "police_station_count_3km", "railway_station_count_3km",
        "waterbody_count_3km", "latitude", "longitude",
    ]
    for col in raw_num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = add_engineered_features(df)
    return df


# Canonical category aliases mapping frontend/user variants to training schema
_TALUK_ALIASES = {
    "hd kote": "HD Kote", "h.d. kote": "HD Kote", "h d kote": "HD Kote", "heggadadevanakote": "HD Kote",
    "hunsur": "Hunsur", "hunasuru": "Hunsur",
    "kr nagar": "K. R. Nagar", "k.r. nagar": "K. R. Nagar", "k. r. nagar": "K. R. Nagar", "krishnarajanagara": "K. R. Nagar",
    "mysuru": "Mysuru", "mysore": "Mysuru",
    "nanjangud": "Nanjangud", "nanjanagudu": "Nanjangud",
    "periyapatna": "Periyapatna", "piriyapattana": "Periyapatna",
    "t narsipura": "T. Narasipura", "t. narsipura": "T. Narasipura", "t narasipura": "T. Narasipura",
    "t. narasipura": "T. Narasipura", "tirumakudalu narasipura": "T. Narasipura",
}
_REGION_ALIASES = {
    "auto": "Auto",
    "urban": "Urban",
    "suburban": "Peri-urban", "peri-urban": "Peri-urban", "periurban": "Peri-urban",
    "semi-urban": "Peri-urban", "town": "Peri-urban",
    "urban/peri-urban": "Urban/Peri-urban",
    "rural": "Rural", "agricultural": "Rural", "rural/agricultural": "Rural",
}
_LAND_ALIASES = {
    "residential": "Residential", "residential plot": "Residential", "plot": "Residential",
    "agricultural": "Agricultural/Farm", "agricultural/farm": "Agricultural/Farm", "farm": "Agricultural/Farm",
    "commercial": "Commercial", "industrial": "Industrial",
}
_LISTING_ALIASES = {
    "new plot": "New Booking", "new booking": "New Booking", "builder layout": "New Booking",
    "resale": "Resale",
}
_ROAD_QUALITY_ALIASES = {
    "asphalt": "Macadam/Asphalt", "tar": "Macadam/Asphalt", "macadam/asphalt": "Macadam/Asphalt",
    "concrete": "Paved/Concrete", "paved/concrete": "Paved/Concrete",
    "gravel": "Gravel/WBM", "gravel/wbm": "Gravel/WBM", "wbm": "Gravel/WBM",
}
_WATER_SOURCE_ALIASES = {
    "piped": "Piped/Borewell", "piped/borewell": "Piped/Borewell",
    "borewell": "Borewell",
    "canal/river": "Canal/River", "canal": "Canal/River", "river": "Canal/River",
}


def canonicalize_categorical(feat: str, val) -> str:
    """Normalize known UI/API categorical variants to match the trained schema."""
    from gis.geo_utils import normalize_taluk
    if val in (None, ""):
        return "Unknown"
    s = str(val).strip()
    if not s:
        return "Unknown"
    low = s.lower()
    if feat == "taluk":
        return normalize_taluk(s)
    if feat == "region_type":
        return _REGION_ALIASES.get(low, s)
    if feat == "land_type":
        return _LAND_ALIASES.get(low, s)
    if feat == "listing_type":
        return _LISTING_ALIASES.get(low, s)
    if feat == "road_quality":
        return _ROAD_QUALITY_ALIASES.get(low, s)
    if feat == "water_source_type":
        return _WATER_SOURCE_ALIASES.get(low, s)
    return s


def prepare_single_input(data: dict) -> pd.DataFrame:
    """
    Prepare a single user input dict into a DataFrame for prediction.
    Applies the exact same feature engineering used in training.
    """
    row = {}

    raw_num_cols = [
        "land_area_sqft", "road_width_ft", "nearest_school_km", "nearest_hospital_km",
        "nearest_market_km", "nearest_supermarket_km", "nearest_pharmacy_km",
        "nearest_police_station_km", "nearest_bank_km", "nearest_bus_stop_km",
        "nearest_railway_station_km", "distance_to_main_road_km", "distance_to_highway_km",
        "distance_to_nearest_waterbody_km", "school_count_3km", "hospital_count_3km",
        "market_count_3km", "supermarket_count_3km", "bank_count_3km", "bus_stop_count_3km",
        "pharmacy_count_3km", "police_station_count_3km", "railway_station_count_3km",
        "waterbody_count_3km", "latitude", "longitude",
    ]
    for feat in raw_num_cols:
        val = data.get(feat, np.nan)
        row[feat] = float(val) if val not in (None, "", "nan") else np.nan

    for feat in CATEGORICAL_FEATURES:
        row[feat] = canonicalize_categorical(feat, data.get(feat, "Unknown"))

    for feat in BINARY_FEATURES:
        val = data.get(feat, None)
        if val is None and feat == "locality_water_supply":
            val = data.get("water_supply", None)
        if val is None:
            row[feat] = np.nan
        elif str(val).strip().upper() in ("YES", "1", "TRUE"):
            row[feat] = 1.0
        elif str(val).strip().upper() in ("NO", "0", "FALSE"):
            row[feat] = 0.0
        else:
            row[feat] = np.nan

    df_single = pd.DataFrame([row])
    df_single = add_engineered_features(df_single)
    return df_single
