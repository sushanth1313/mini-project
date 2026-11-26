"""
SQLAlchemy database models for Smart Land Evaluation Platform.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Property(db.Model):
    __tablename__ = "properties"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("platform_users.id"), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=True)  # user-given label
    district = db.Column(db.String(100), default="Mysuru")
    taluk = db.Column(db.String(100), nullable=False)
    village_or_locality = db.Column(db.String(200), nullable=False)
    entered_locality = db.Column(db.String(200), nullable=True)
    entered_taluk = db.Column(db.String(100), nullable=True)
    region_type = db.Column(db.String(50), nullable=True)
    land_type = db.Column(db.String(50), nullable=True)
    listing_type = db.Column(db.String(50), nullable=True)
    land_area_sqft = db.Column(db.Float, nullable=False)
    asking_price_inr = db.Column(db.Float, nullable=True)

    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    coordinate_status = db.Column(db.String(50), default="LOCALITY_CENTROID")
    coordinate_source = db.Column(db.String(100), nullable=True)

    road_width_ft = db.Column(db.Float, nullable=True)
    road_quality = db.Column(db.String(50), nullable=True)
    road_access = db.Column(db.String(50), nullable=True)
    street_light_available = db.Column(db.String(10), nullable=True)
    public_transport_available = db.Column(db.String(10), nullable=True)
    electricity_available = db.Column(db.String(10), nullable=True)
    water_supply = db.Column(db.String(10), nullable=True)
    water_source_type = db.Column(db.String(50), nullable=True)

    dataset_record_id = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    evaluations = db.relationship("PropertyEvaluation", backref="property", lazy=True, cascade="all, delete-orphan")
    documents = db.relationship("Document", backref="property", lazy=True, cascade="all, delete-orphan")
    reports = db.relationship("Report", backref="property", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name or f"{self.village_or_locality} ({self.land_area_sqft:.0f} sqft)",
            "district": self.district,
            "taluk": self.taluk,
            "village_or_locality": self.village_or_locality,
            "entered_locality": self.entered_locality,
            "entered_taluk": self.entered_taluk,
            "region_type": self.region_type,
            "land_type": self.land_type,
            "listing_type": self.listing_type,
            "land_area_sqft": self.land_area_sqft,
            "asking_price_inr": self.asking_price_inr,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "coordinate_status": self.coordinate_status,
            "coordinate_source": self.coordinate_source,
            "road_width_ft": self.road_width_ft,
            "road_quality": self.road_quality,
            "road_access": self.road_access,
            "street_light_available": self.street_light_available,
            "public_transport_available": self.public_transport_available,
            "electricity_available": self.electricity_available,
            "water_supply": self.water_supply,
            "water_source_type": self.water_source_type,
            "dataset_record_id": self.dataset_record_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PropertyEvaluation(db.Model):
    __tablename__ = "property_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False)

    # Price prediction
    predicted_price_per_sqft = db.Column(db.Float, nullable=True)
    predicted_total_price = db.Column(db.Float, nullable=True)
    price_range_low = db.Column(db.Float, nullable=True)
    price_range_high = db.Column(db.Float, nullable=True)
    model_used = db.Column(db.String(100), nullable=True)
    model_version = db.Column(db.String(50), nullable=True)
    training_records = db.Column(db.Integer, nullable=True)
    validation_mae = db.Column(db.Float, nullable=True)
    validation_rmse = db.Column(db.Float, nullable=True)
    validation_r2 = db.Column(db.Float, nullable=True)
    confidence_level = db.Column(db.String(20), nullable=True)

    # Scores (0–100)
    price_score = db.Column(db.Float, nullable=True)
    location_score = db.Column(db.Float, nullable=True)
    facility_score = db.Column(db.Float, nullable=True)
    environment_score = db.Column(db.Float, nullable=True)
    infrastructure_score = db.Column(db.Float, nullable=True)
    utility_score = db.Column(db.Float, nullable=True)
    overall_score = db.Column(db.Float, nullable=True)

    # Weightage tracking for this evaluation
    weightage_version_id = db.Column(db.Integer, db.ForeignKey("weightage_versions.id"), nullable=True)
    price_weight = db.Column(db.Float, nullable=True)
    location_weight = db.Column(db.Float, nullable=True)
    facility_weight = db.Column(db.Float, nullable=True)
    environment_weight = db.Column(db.Float, nullable=True)
    infrastructure_weight = db.Column(db.Float, nullable=True)
    utility_weight = db.Column(db.Float, nullable=True)

    # Score breakdowns (JSON stored as text)
    location_breakdown = db.Column(db.Text, nullable=True)
    facility_breakdown = db.Column(db.Text, nullable=True)
    infrastructure_breakdown = db.Column(db.Text, nullable=True)
    utility_breakdown = db.Column(db.Text, nullable=True)
    environment_breakdown = db.Column(db.Text, nullable=True)

    # Warnings & location resolution audit & market comparison
    warnings = db.Column(db.Text, nullable=True)
    location_audit = db.Column(db.Text, nullable=True)
    market_comparison = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    gis_analysis = db.relationship("GISAnalysis", backref="evaluation", uselist=False, cascade="all, delete-orphan")
    facilities = db.relationship("FacilityRecord", backref="evaluation", lazy=True, cascade="all, delete-orphan")
    price_prediction = db.relationship("PricePrediction", backref="evaluation", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        import json
        mkt_cmp = json.loads(self.market_comparison) if getattr(self, "market_comparison", None) else None
        return {
            "id": self.id,
            "property_id": self.property_id,
            "predicted_price_per_sqft": self.predicted_price_per_sqft,
            "predicted_total_price": self.predicted_total_price,
            "price_range_low": self.price_range_low,
            "price_range_high": self.price_range_high,
            "model_used": self.model_used,
            "model_version": self.model_version,
            "training_records": self.training_records,
            "validation_mae": self.validation_mae,
            "validation_rmse": self.validation_rmse,
            "validation_r2": self.validation_r2,
            "confidence_level": self.confidence_level,
            "price_score": self.price_score,
            "location_score": self.location_score,
            "facility_score": self.facility_score,
            "environment_score": self.environment_score,
            "infrastructure_score": self.infrastructure_score,
            "utility_score": self.utility_score,
            "overall_score": self.overall_score,
            "price_weight": self.price_weight,
            "location_weight": self.location_weight,
            "facility_weight": self.facility_weight,
            "environment_weight": self.environment_weight,
            "infrastructure_weight": self.infrastructure_weight,
            "utility_weight": self.utility_weight,
            "location_breakdown": json.loads(self.location_breakdown) if self.location_breakdown else {},
            "facility_breakdown": json.loads(self.facility_breakdown) if self.facility_breakdown else {},
            "infrastructure_breakdown": json.loads(self.infrastructure_breakdown) if self.infrastructure_breakdown else {},
            "utility_breakdown": json.loads(self.utility_breakdown) if self.utility_breakdown else {},
            "environment_breakdown": json.loads(self.environment_breakdown) if self.environment_breakdown else {},
            "warnings": json.loads(self.warnings) if self.warnings else [],
            "location_audit": json.loads(self.location_audit) if getattr(self, "location_audit", None) else None,
            "market_comparison": mkt_cmp,
            "valuation_summary": mkt_cmp.get("valuation_summary") if isinstance(mkt_cmp, dict) else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            # Facilities from DB (used by MapAnalysis when loading from /properties/:id)
            "facilities_detail": {
                f.facility_type: {
                    "nearest": {"name": f.name, "lat": f.latitude, "lon": f.longitude, "distance_km": f.distance_km} if (f.name or f.latitude is not None or f.distance_km is not None) else None,
                    "nearest_distance_km": f.distance_km,
                    "count_within_1km": getattr(f, "count_within_1km", None),
                    "count_within_3km": f.count_within_3km,
                    "count_within_5km": getattr(f, "count_within_5km", None),
                    "source": f.source,
                    "status": f.status,
                    "retrieved_at": f.retrieved_at.isoformat() if f.retrieved_at else None,
                    "distance_type": "straight_line_haversine",
                }
                for f in self.facilities
            } if self.facilities else {},
        }


class PricePrediction(db.Model):
    __tablename__ = "price_predictions"

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("property_evaluations.id"), nullable=False)
    model_name = db.Column(db.String(100))
    predicted_price_per_sqft = db.Column(db.Float)
    mae = db.Column(db.Float)
    rmse = db.Column(db.Float)
    r2 = db.Column(db.Float)
    feature_importances = db.Column(db.Text)  # JSON
    input_features = db.Column(db.Text)  # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GISAnalysis(db.Model):
    __tablename__ = "gis_analysis"

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("property_evaluations.id"), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    coordinate_status = db.Column(db.String(50))
    distance_to_main_road_km = db.Column(db.Float, nullable=True)
    distance_to_highway_km = db.Column(db.Float, nullable=True)
    distance_to_waterbody_km = db.Column(db.Float, nullable=True)
    waterbody_count_3km = db.Column(db.Integer, nullable=True)
    source = db.Column(db.String(100), default="OSM/Overpass API")
    retrieved_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="GIS_DERIVED")

    def to_dict(self):
        return {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "coordinate_status": self.coordinate_status,
            "distance_to_main_road_km": self.distance_to_main_road_km,
            "distance_to_highway_km": self.distance_to_highway_km,
            "distance_to_waterbody_km": self.distance_to_waterbody_km,
            "waterbody_count_3km": self.waterbody_count_3km,
            "source": self.source,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "status": self.status,
        }


class FacilityRecord(db.Model):
    __tablename__ = "facilities"

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("property_evaluations.id"), nullable=False)
    facility_type = db.Column(db.String(50))   # school, hospital, bus_stop, etc.
    name = db.Column(db.String(200), nullable=True)
    distance_km = db.Column(db.Float)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    count_within_1km = db.Column(db.Integer, nullable=True)
    count_within_3km = db.Column(db.Integer, nullable=True)
    count_within_5km = db.Column(db.Integer, nullable=True)
    source = db.Column(db.String(100), default="OSM/Overpass API")
    status = db.Column(db.String(50), default="SUCCESS")
    retrieved_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "facility_type": self.facility_type,
            "name": self.name,
            "distance_km": self.distance_km,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "count_within_1km": self.count_within_1km,
            "count_within_3km": self.count_within_3km,
            "count_within_5km": self.count_within_5km,
            "source": self.source,
            "status": self.status,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
        }


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    file_type = db.Column(db.String(20))  # pdf, jpg, png
    file_size_bytes = db.Column(db.Integer)
    upload_path = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    extraction_status = db.Column(db.String(30), default="PENDING")  # PENDING, DONE, FAILED

    extraction = db.relationship("DocumentExtraction", backref="document", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size_bytes": self.file_size_bytes,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "extraction_status": self.extraction_status,
        }


class DocumentExtraction(db.Model):
    __tablename__ = "document_extractions"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False)
    raw_text = db.Column(db.Text, nullable=True)
    owner_name = db.Column(db.String(200), nullable=True)
    survey_number = db.Column(db.String(100), nullable=True)
    document_type = db.Column(db.String(100), nullable=True)
    village = db.Column(db.String(100), nullable=True)
    taluk = db.Column(db.String(100), nullable=True)
    district = db.Column(db.String(100), nullable=True)
    area_mentioned = db.Column(db.String(100), nullable=True)
    dates_mentioned = db.Column(db.Text, nullable=True)  # JSON list
    registration_ref = db.Column(db.String(200), nullable=True)
    extraction_method = db.Column(db.String(50))  # pdfplumber, pymupdf, tesseract
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "document_id": self.document_id,
            "raw_text_preview": (self.raw_text or "")[:500],
            "owner_name": self.owner_name,
            "survey_number": self.survey_number,
            "document_type": self.document_type,
            "village": self.village,
            "taluk": self.taluk,
            "district": self.district,
            "area_mentioned": self.area_mentioned,
            "dates_mentioned": json.loads(self.dates_mentioned) if self.dates_mentioned else [],
            "registration_ref": self.registration_ref,
            "extraction_method": self.extraction_method,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }


class VerificationItem(db.Model):
    __tablename__ = "verification_items"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False)
    item_key = db.Column(db.String(100), nullable=False)
    item_label = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default="NEEDS_VERIFICATION")  # EXTRACTED, USER_CONFIRMED, NEEDS_VERIFICATION, NOT_FOUND
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "item_key": self.item_key,
            "item_label": self.item_label,
            "status": self.status,
            "notes": self.notes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("property_evaluations.id"), nullable=True)
    filename = db.Column(db.String(300), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_size_bytes = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "evaluation_id": self.evaluation_id,
            "filename": self.filename,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "file_size_bytes": self.file_size_bytes,
        }


class DataSource(db.Model):
    __tablename__ = "data_sources"

    id = db.Column(db.Integer, primary_key=True)
    source_name = db.Column(db.String(200), nullable=False)
    source_type = db.Column(db.String(50))  # dataset, GIS, API, government
    source_url = db.Column(db.String(500), nullable=True)
    data_date = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    confidence = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "data_date": self.data_date,
            "description": self.description,
            "confidence": self.confidence,
            "status": self.status,
        }


class DatasetRecord(db.Model):
    """Stores the raw imported dataset records for reference and comparison."""
    __tablename__ = "dataset_records"

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.String(20), unique=True, nullable=False)
    district = db.Column(db.String(100))
    taluk = db.Column(db.String(100))
    village_or_locality = db.Column(db.String(200))
    region_type = db.Column(db.String(50))
    land_type = db.Column(db.String(50))
    listing_type = db.Column(db.String(50))
    land_area_sqft = db.Column(db.Float)
    asking_price_inr = db.Column(db.Float)
    price_per_sqft = db.Column(db.Float)
    price_per_acre = db.Column(db.Float)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    coordinate_status = db.Column(db.String(50))
    nearest_school_km = db.Column(db.Float)
    nearest_hospital_km = db.Column(db.Float)
    nearest_market_km = db.Column(db.Float)
    nearest_supermarket_km = db.Column(db.Float)
    nearest_bus_stop_km = db.Column(db.Float)
    nearest_railway_station_km = db.Column(db.Float)
    nearest_bank_km = db.Column(db.Float)
    nearest_pharmacy_km = db.Column(db.Float)
    school_count_3km = db.Column(db.Integer)
    hospital_count_3km = db.Column(db.Integer)
    bank_count_3km = db.Column(db.Integer)
    bus_stop_count_3km = db.Column(db.Integer)
    distance_to_main_road_km = db.Column(db.Float)
    distance_to_highway_km = db.Column(db.Float)
    distance_to_nearest_waterbody_km = db.Column(db.Float)
    road_width_ft = db.Column(db.Float)
    road_quality = db.Column(db.String(50))
    street_light_available = db.Column(db.String(10))
    public_transport_available = db.Column(db.String(10))
    electricity_available = db.Column(db.String(10))
    locality_water_supply = db.Column(db.String(10))
    water_source_type = db.Column(db.String(50))
    property_source = db.Column(db.String(100))
    property_source_url = db.Column(db.String(500))
    source_date = db.Column(db.String(50))
    price_score_100 = db.Column(db.Float)
    location_score_100 = db.Column(db.Float)
    facility_score_100 = db.Column(db.Float)
    infrastructure_score_100 = db.Column(db.Float)
    utility_score_100 = db.Column(db.Float)
    environment_score_100 = db.Column(db.Float)
    overall_land_evaluation_score_100 = db.Column(db.Float)
    confidence_level = db.Column(db.String(30))
    data_status = db.Column(db.String(30))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "record_id": self.record_id,
            "district": self.district,
            "taluk": self.taluk,
            "village_or_locality": self.village_or_locality,
            "entered_locality": getattr(self, "entered_locality", self.village_or_locality),
            "entered_taluk": getattr(self, "entered_taluk", self.taluk),
            "region_type": self.region_type,
            "land_type": self.land_type,
            "listing_type": self.listing_type,
            "land_area_sqft": self.land_area_sqft,
            "asking_price_inr": self.asking_price_inr,
            "price_per_sqft": self.price_per_sqft,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "coordinate_status": self.coordinate_status,
            "nearest_school_km": self.nearest_school_km,
            "nearest_hospital_km": self.nearest_hospital_km,
            "nearest_bus_stop_km": self.nearest_bus_stop_km,
            "distance_to_main_road_km": self.distance_to_main_road_km,
            "road_width_ft": self.road_width_ft,
            "road_quality": self.road_quality,
            "price_score_100": self.price_score_100,
            "location_score_100": self.location_score_100,
            "facility_score_100": self.facility_score_100,
            "infrastructure_score_100": self.infrastructure_score_100,
            "utility_score_100": self.utility_score_100,
            "environment_score_100": self.environment_score_100,
            "overall_land_evaluation_score_100": self.overall_land_evaluation_score_100,
            "confidence_level": self.confidence_level,
            "property_source": self.property_source,
            "source_date": self.source_date,
        }

class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WeightageVersion(db.Model):
    __tablename__ = "weightage_versions"
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False)
    price_weight = db.Column(db.Float, nullable=False, default=30.0)
    location_weight = db.Column(db.Float, nullable=False, default=20.0)
    facility_weight = db.Column(db.Float, nullable=False, default=15.0)
    environment_weight = db.Column(db.Float, nullable=False, default=15.0)
    infrastructure_weight = db.Column(db.Float, nullable=False, default=10.0)
    utility_weight = db.Column(db.Float, nullable=False, default=10.0)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "version": self.version,
            "price_weight": self.price_weight,
            "location_weight": self.location_weight,
            "facility_weight": self.facility_weight,
            "environment_weight": self.environment_weight,
            "infrastructure_weight": self.infrastructure_weight,
            "utility_weight": self.utility_weight,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }


class PlatformUser(db.Model):
    """Registered platform users (students/buyers/analysts) managed by Admin RBAC."""
    __tablename__ = "platform_users"

    id = db.Column(db.Integer, primary_key=True)
    user_uid = db.Column(db.String(64), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    role = db.Column(db.String(50), default="user")  # user | buyer | student | analyst | legal_reviewer
    status = db.Column(db.String(40), default="active")  # active | suspended | pending
    password_hash = db.Column(db.String(255), nullable=False)
    preferred_taluk = db.Column(db.String(100), default="Mysuru")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_uid,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "status": self.status,
            "preferred_taluk": self.preferred_taluk,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


class AdminAccount(db.Model):
    """Persistent RBAC Admin accounts (5 roles)."""
    __tablename__ = "admin_accounts"

    id = db.Column(db.Integer, primary_key=True)
    admin_uid = db.Column(db.String(64), unique=True, nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(60), nullable=False, default="SUPPORT_ADMIN")
    status = db.Column(db.String(30), nullable=False, default="ACTIVE")
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    failed_attempts = db.Column(db.Integer, default=0)
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        st = (self.status or ("ACTIVE" if self.is_active else "SUSPENDED")).upper()
        return {
            "id": self.admin_uid,
            "admin_id": self.admin_uid,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "status": st,
            "is_active": bool(self.is_active and st == "ACTIVE"),
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "last_login_ip": self.last_login_ip,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SupportTicket(db.Model):
    """Persistent User-to-Admin Support Center tickets with threaded conversation history."""
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    user_uid = db.Column(db.String(64), nullable=True)
    user_name = db.Column(db.String(150), nullable=False)
    user_email = db.Column(db.String(150), nullable=False)
    property_id = db.Column(db.Integer, nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(60), nullable=False, default="Other")
    priority = db.Column(db.String(30), nullable=False, default="MEDIUM")
    status = db.Column(db.String(30), nullable=False, default="OPEN")  # OPEN | IN_PROGRESS | AWAITING_USER | RESOLVED | CLOSED
    assigned_admin_id = db.Column(db.String(64), nullable=True)
    assigned_admin_name = db.Column(db.String(150), nullable=True)
    attachment_name = db.Column(db.String(260), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)
    messages_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        import json
        msgs = []
        if self.messages_json:
            try:
                msgs = json.loads(self.messages_json)
            except Exception:
                msgs = []
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "user_id": self.user_id,
            "user_uid": self.user_uid,
            "user_name": self.user_name,
            "user_email": self.user_email,
            "property_id": self.property_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "assigned_admin_id": self.assigned_admin_id,
            "assigned_admin_name": self.assigned_admin_name,
            "attachment_name": self.attachment_name,
            "has_attachment": bool(self.attachment_path),
            "messages": msgs,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PortalNotification(db.Model):
    """Persistent notifications for Admin RBAC roles/accounts and Platform Users."""
    __tablename__ = "portal_notifications"

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    recipient_type = db.Column(db.String(20), nullable=False, index=True)  # ADMIN_ROLE | ADMIN_ID | USER_ID
    recipient_target = db.Column(db.String(80), nullable=False, index=True)  # SUPPORT_ADMIN | SUPER_ADMIN | ADM-0001 | user.id
    ticket_id = db.Column(db.String(32), nullable=True, index=True)
    category = db.Column(db.String(60), nullable=False, default="SUPPORT_TICKET")
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(300), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    read_by_json = db.Column(db.Text, nullable=True)  # list of admin_ids/user_ids who read role-wide notification
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_read_for(self, viewer_id: str | None = None) -> bool:
        if self.recipient_type != "ADMIN_ROLE":
            return bool(self.is_read)
        if self.is_read:
            return True
        if not viewer_id or not self.read_by_json:
            return False
        import json
        try:
            readers = json.loads(self.read_by_json)
            return str(viewer_id) in [str(x) for x in readers]
        except Exception:
            return False

    def to_dict(self, viewer_id: str | None = None):
        return {
            "notification_id": self.notification_id,
            "recipient_type": self.recipient_type,
            "recipient_target": self.recipient_target,
            "ticket_id": self.ticket_id,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "link": self.link,
            "is_read": self.is_read_for(viewer_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AdminAuditLog(db.Model):
    """Append-only immutable audit trail for admin actions & security checks."""
    __tablename__ = "admin_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(80), unique=True, nullable=False)
    actor_id = db.Column(db.String(80), nullable=False)
    actor_username = db.Column(db.String(100), nullable=True)
    actor_role = db.Column(db.String(60), nullable=False)
    action = db.Column(db.String(120), nullable=False)
    resource_type = db.Column(db.String(80), nullable=False)
    resource_id = db.Column(db.String(120), nullable=True)
    before_json = db.Column(db.Text, nullable=True)
    after_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(30), default="SUCCESS")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AdminKvRecord(db.Model):
    """Persistent SQLite storage for admin governance metadata, versions, settings, and flags."""
    __tablename__ = "admin_kv_collections"

    id = db.Column(db.Integer, primary_key=True)
    collection_name = db.Column(db.String(80), index=True, nullable=False)
    doc_uid = db.Column(db.String(100), index=True, nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerEnquiry(db.Model):
    """Persisted customer consultation / support / help enquiries."""
    __tablename__ = "customer_enquiries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    property_id = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    taluk = db.Column(db.String(80), default="Mysuru")
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="OPEN")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "property_id": self.property_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "taluk": self.taluk,
            "subject": self.subject,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SavedProperty(db.Model):
    """Customer bookmarked properties for shortlist & comparison."""
    __tablename__ = "saved_properties"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False)
    note = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "property_id": self.property_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
