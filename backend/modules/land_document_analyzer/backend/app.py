"""Production Flask REST API for AI Land Document Analyzer (ready for integration into existing Flask apps)."""
import json
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, Flask, has_app_context, jsonify, request, send_file
from flask_cors import CORS

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.models.schemas import DOCUMENT_TYPES, MANDATORY_LEGAL_DISCLAIMER
from modules.land_document_analyzer.backend.pipeline import DueDiligencePipeline
from modules.land_document_analyzer.backend.services.document_upload_service import DocumentUploadError
from modules.land_document_analyzer.backend.services.ocr_service import CV2_AVAILABLE, PYMUPDF_AVAILABLE
from modules.land_document_analyzer.backend.utils.security import get_safe_logger, verify_auth_header

logger = get_safe_logger(__name__)

# Modular Flask Blueprint for drop-in registration in the main Smart Land Valuation Flask app
document_analysis_bp = Blueprint("document_analysis", __name__, url_prefix="/api/document-analysis")
_pipeline = DueDiligencePipeline()


def _extract_field_value(fields: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        item = fields.get(key)
        if isinstance(item, dict):
            val = item.get("effective_value")
            if val is None:
                val = item.get("value")
            if val not in (None, "", "Not found", "Unable to extract from uploaded document"):
                return str(val).strip()
        elif item not in (None, "", "Not found", "Unable to extract from uploaded document"):
            return str(item).strip()
    return None


def _sync_analysis_to_sqlite(analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Synchronizes analyzed document metadata into SQLite Document/Verification tables conservatively."""
    summary = {"synced": False, "property_id": None, "documents_synced": 0}
    if not analysis or not has_app_context():
        return summary

    prop_raw = (analysis.get("property_info") or {}).get("property_id")
    try:
        prop_id = int(str(prop_raw).strip())
    except (TypeError, ValueError):
        return summary

    try:
        from models import Document, DocumentExtraction, Property, VerificationItem, db
    except Exception:
        return summary

    prop = Property.query.get(prop_id)
    if not prop:
        return summary

    docs = analysis.get("documents", []) or []
    synced_count = 0
    for doc in docs:
        doc_uid = doc.get("document_id") or "doc"
        stored_name = f"doc_analyzer_{doc_uid}"
        existing = Document.query.filter_by(property_id=prop_id, filename=stored_name).first()
        orig_name = doc.get("original_filename") or "document.pdf"
        ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else "pdf"
        extraction_obj = doc.get("extraction") or {}
        fields = extraction_obj.get("fields") or {}
        ocr_obj = doc.get("ocr") or {}

        if not existing:
            existing = Document(
                property_id=prop_id,
                filename=stored_name,
                original_filename=orig_name,
                file_type=ext,
                file_size_bytes=int(doc.get("size_bytes") or 0),
                upload_path=doc.get("stored_path") or "",
                extraction_status="DONE",
            )
            db.session.add(existing)
            db.session.flush()
        else:
            existing.upload_path = doc.get("stored_path") or existing.upload_path
            existing.extraction_status = "DONE"

        if existing.extraction:
            ext_rec = existing.extraction
        else:
            ext_rec = DocumentExtraction(document_id=existing.id)
            db.session.add(ext_rec)

        ext_rec.raw_text = (ocr_obj.get("raw_text") or "")[:10000]
        ext_rec.owner_name = _extract_field_value(fields, "owner_names", "buyer_names", "seller_names", "new_owner", "applicant")
        ext_rec.survey_number = _extract_field_value(fields, "survey_number")
        ext_rec.document_type = doc.get("document_type")
        ext_rec.village = _extract_field_value(fields, "village")
        ext_rec.taluk = _extract_field_value(fields, "taluk")
        ext_rec.district = _extract_field_value(fields, "district")
        ext_rec.area_mentioned = _extract_field_value(fields, "property_extent", "total_land_extent", "converted_extent", "total_layout_extent")
        ext_rec.registration_ref = _extract_field_value(fields, "registration_number", "document_number", "conversion_order_number", "approval_number")
        ext_rec.extraction_method = ocr_obj.get("engine_used") or "doc_analyzer"
        synced_count += 1

    # Conservative verification status sync — NEVER label AI output as officially verified
    has_owner = any(_extract_field_value((d.get("extraction") or {}).get("fields") or {}, "owner_names", "buyer_names", "seller_names", "new_owner") for d in docs)
    has_survey = any(_extract_field_value((d.get("extraction") or {}).get("fields") or {}, "survey_number") for d in docs)
    has_village = any(_extract_field_value((d.get("extraction") or {}).get("fields") or {}, "village") for d in docs)
    risk = analysis.get("risk_assessment") or {}
    overall_lbl = risk.get("overall_assessment") or "Pending official review"
    sev_counts = risk.get("severity_counts") or {}

    sync_items = [
        (
            "owner_name",
            "Owner / Claimant Name (Document Extracted — Unverified)",
            "EXTRACTED" if has_owner else "NEEDS_VERIFICATION",
            "Extracted from uploaded documents by Document Analyzer. Official Sub-Registrar/Bhoomi cross-check still required.",
        ),
        (
            "survey_number",
            "Survey / Khata Reference (Document Extracted — Unverified)",
            "EXTRACTED" if has_survey else "NEEDS_VERIFICATION",
            "Extracted from uploaded documents. Must be confirmed against official Bhoomi RTC.",
        ),
        (
            "village_match",
            "Village / Taluk Consistency Check",
            "EXTRACTED" if has_village else "NEEDS_VERIFICATION",
            f"Preliminary Document Analyzer status: {overall_lbl} (Critical: {sev_counts.get('Critical', 0)}, High: {sev_counts.get('High', 0)}). Not legal title certification.",
        ),
    ]
    for item_key, label, status, notes in sync_items:
        item = VerificationItem.query.filter_by(property_id=prop_id, item_key=item_key).first()
        if not item:
            db.session.add(VerificationItem(property_id=prop_id, item_key=item_key, item_label=label, status=status, notes=notes))
        elif item.status != "USER_CONFIRMED":
            item.status = status
            item.notes = notes

    db.session.commit()
    return {"synced": True, "property_id": prop_id, "documents_synced": synced_count}


_PORTAL_ROLES = (
    "user",
    "standard_user",
    "authorized_surveyor",
    "valuation_analyst",
    "student",
    "analyst",
    "buyer",
    "lawyer",
    "admin",
    "super_admin",
    "data_admin",
    "ml_admin",
    "system_admin",
    "support_admin",
)


def require_auth(roles: Optional[Tuple[str, ...]] = None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            ok, role, msg = verify_auth_header(dict(request.headers), required_roles=roles)
            if not ok:
                status_code = 401 if role == "anonymous" or "Authentication required" in msg or "Missing" in msg or "Invalid" in msg else 403
                code = "AUTH_REQUIRED" if status_code == 401 else "FORBIDDEN"
                return jsonify({"error": msg, "code": code}), status_code
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@document_analysis_bp.route("", methods=["GET"])
@require_auth(roles=_PORTAL_ROLES)
def list_analyses():
    property_id = (request.args.get("property_id") or "").strip()
    all_records = _pipeline.db.collection("analyses").find()
    if property_id:
        all_records = [
            rec for rec in all_records
            if str((rec.get("property_info") or {}).get("property_id", "")).strip() == property_id
        ]
    all_records.sort(key=lambda r: str(r.get("generated_at", "")), reverse=True)
    summaries = []
    for rec in all_records:
        risk = rec.get("risk_assessment") or {}
        summaries.append({
            "analysis_id": rec.get("analysis_id"),
            "report_id": rec.get("report_id"),
            "generated_at": rec.get("generated_at"),
            "property_info": rec.get("property_info") or {},
            "document_count": len(rec.get("documents") or []),
            "overall_assessment": rec.get("overall_assessment") or risk.get("overall_assessment"),
            "severity_counts": risk.get("severity_counts") or {},
            "total_findings": risk.get("total_findings") or len(rec.get("risk_findings") or []),
            "has_pdf": bool(rec.get("report_pdf_path")),
        })
    return jsonify({"count": len(summaries), "analyses": summaries}), 200


@document_analysis_bp.route("/by-property/<int:property_id>", methods=["GET"])
@require_auth(roles=_PORTAL_ROLES)
def get_analysis_by_property(property_id: int):
    if not has_app_context():
        return jsonify({"error": "SQLite property lookup unavailable outside main app."}), 400
    from models import Document, Property

    prop = Property.query.get(property_id)
    if not prop:
        return jsonify({"error": "Property not found."}), 404

    loc_val = prop.village_or_locality or ""
    prefill = {
        "property_id": str(prop.id),
        "property_label": prop.name or loc_val or f"Property #{prop.id}",
        "district": prop.district or "Mysuru",
        "taluk": prop.taluk or "",
        "locality": loc_val,
        "village": loc_val,
        "latitude": str(prop.latitude) if prop.latitude is not None else "",
        "longitude": str(prop.longitude) if prop.longitude is not None else "",
        "survey_number": "",
        "hissa_number": "",
        "plot_number": "",
        "property_type": (prop.land_type or "residential_plot").lower().replace(" ", "_"),
        "land_area": f"{int(round(prop.land_area_sqft))} sq.ft." if prop.land_area_sqft else "",
    }
    matches = [
        rec for rec in _pipeline.db.collection("analyses").find()
        if str((rec.get("property_info") or {}).get("property_id", "")).strip() == str(property_id)
    ]
    matches.sort(key=lambda r: str(r.get("generated_at", "")), reverse=True)
    sqlite_docs_count = Document.query.filter_by(property_id=property_id).count()
    return jsonify({
        "property_info": prefill,
        "sqlite_documents_count": sqlite_docs_count,
        "latest_analysis": matches[0] if matches else None,
        "analysis_count": len(matches),
    }), 200


@document_analysis_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify(
        {
            "status": "ok",
            "service": Settings.APP_NAME,
            "version": Settings.APP_VERSION,
            "storage_mode": _pipeline.db.backend_mode,
            "supported_document_types": DOCUMENT_TYPES,
            "max_file_size_mb": Settings.MAX_FILE_SIZE_MB,
            "ocr_capabilities": {
                "digital_pdf_pymupdf": PYMUPDF_AVAILABLE,
                "tesseract_installed": _pipeline.ocr_service.tesseract_available,
                "opencv_installed": CV2_AVAILABLE,
                "active_language": _pipeline.ocr_service.active_language,
            },
        }
    )


@document_analysis_bp.route("/analyze", methods=["POST"])
@require_auth(roles=_PORTAL_ROLES)
def analyze_documents():
    """
    Accepts multipart/form-data containing property metadata + uploaded_documents files.
    Never puts binary files inside ordinary JSON.
    """
    property_info: Dict[str, Any] = {
        "property_id": request.form.get("property_id", ""),
        "property_label": request.form.get("property_label", ""),
        "district": request.form.get("district", "Mysuru"),
        "taluk": request.form.get("taluk", ""),
        "locality": request.form.get("locality", ""),
        "village": request.form.get("village") or request.form.get("locality", ""),
        "latitude": request.form.get("latitude", ""),
        "longitude": request.form.get("longitude", ""),
        "survey_number": request.form.get("survey_number", ""),
        "hissa_number": request.form.get("hissa_number", ""),
        "plot_number": request.form.get("plot_number", ""),
        "property_type": request.form.get("property_type", "residential_plot"),
        "land_area": request.form.get("land_area", ""),
    }

    manual_cases_raw = request.form.get("manual_cases", "[]")
    try:
        manual_cases = json.loads(manual_cases_raw) if manual_cases_raw else []
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON in manual_cases field."}), 400

    declared_types_raw = request.form.get("declared_types", "{}")
    try:
        declared_types = json.loads(declared_types_raw) if declared_types_raw else {}
    except json.JSONDecodeError:
        declared_types = {}

    external_ai_consent = request.form.get("external_ai_consent", "false").lower() == "true"
    ai_provider = request.form.get("ai_provider", Settings.AI_PROVIDER)

    files = request.files.getlist("uploaded_documents")
    if not files:
        return jsonify({"error": "No files uploaded under 'uploaded_documents'."}), 400
    if len(files) > Settings.MAX_FILES_PER_ANALYSIS:
        return jsonify({"error": f"Maximum {Settings.MAX_FILES_PER_ANALYSIS} files allowed per analysis."}), 400

    uploaded_payload: List[Tuple[str, bytes, Optional[str]]] = []
    for f in files:
        content = f.read()
        uploaded_payload.append((f.filename or "document.pdf", content, declared_types.get(f.filename)))

    try:
        result = _pipeline.run_analysis(
            property_info=property_info,
            uploaded_files=uploaded_payload,
            manual_cases=manual_cases,
            external_ai_consent=external_ai_consent,
            ai_provider=ai_provider,
            generate_pdf=True,
        )
        result["sqlite_sync"] = _sync_analysis_to_sqlite(result)
        return jsonify(result), 200
    except DocumentUploadError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Analysis failed: %s", type(exc).__name__)
        return jsonify({"error": "Document analysis failed due to an internal processing error."}), 500


@document_analysis_bp.route("/<analysis_id>", methods=["GET"])
@require_auth(roles=_PORTAL_ROLES)
def get_analysis(analysis_id: str):
    record = _pipeline.get_analysis(analysis_id)
    if not record:
        return jsonify({"error": "Analysis not found."}), 404
    return jsonify(record), 200


@document_analysis_bp.route("/<analysis_id>/documents/<document_id>/classification", methods=["PATCH"])
@require_auth(roles=_PORTAL_ROLES)
def reclassify_document(analysis_id: str, document_id: str):
    payload = request.get_json(silent=True) or {}
    new_type = str(payload.get("document_type") or "").strip()
    if new_type not in DOCUMENT_TYPES:
        return jsonify({"error": f"Unsupported document_type '{new_type}'."}), 400
    updated = _pipeline.reclassify_document(
        analysis_id=analysis_id,
        document_id=document_id,
        new_document_type=new_type,
        reclassified_by=request.headers.get("X-User-Role", "user"),
    )
    if not updated:
        return jsonify({"error": "Analysis or document not found."}), 404
    updated["sqlite_sync"] = _sync_analysis_to_sqlite(updated)
    return jsonify(updated), 200


@document_analysis_bp.route("/<analysis_id>/documents/<document_id>/corrections", methods=["PATCH"])
@require_auth(roles=_PORTAL_ROLES)
def correct_document_fields(analysis_id: str, document_id: str):
    payload = request.get_json(silent=True) or {}
    corrections = payload.get("corrections", {})
    if not isinstance(corrections, dict) or not corrections:
        return jsonify({"error": "Provide a non-empty 'corrections' dictionary."}), 400
    updated = _pipeline.apply_manual_correction(
        analysis_id=analysis_id,
        document_id=document_id,
        corrections={k: str(v) for k, v in corrections.items()},
        corrected_by=request.headers.get("X-User-Role", "user"),
    )
    if not updated:
        return jsonify({"error": "Analysis or document not found."}), 404
    updated["sqlite_sync"] = _sync_analysis_to_sqlite(updated)
    return jsonify(updated), 200


@document_analysis_bp.route("/<analysis_id>/documents/<document_id>", methods=["DELETE"])
@require_auth(roles=_PORTAL_ROLES)
def delete_document(analysis_id: str, document_id: str):
    updated = _pipeline.delete_document(analysis_id, document_id)
    if not updated:
        return jsonify({"error": "Analysis or document not found."}), 404
    updated["sqlite_sync"] = _sync_analysis_to_sqlite(updated)
    return jsonify(updated), 200


@document_analysis_bp.route("/<analysis_id>/report/pdf", methods=["GET"])
@require_auth(roles=_PORTAL_ROLES)
def download_pdf_report(analysis_id: str):
    pdf_path = _pipeline.get_report_path(analysis_id)
    if not pdf_path or not pdf_path.exists():
        return jsonify({"error": "PDF report not found."}), 404
    return send_file(
        str(pdf_path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"AI_Land_Due_Diligence_Report_{analysis_id}.pdf",
    )


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Settings.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = Settings.MAX_FILE_SIZE_BYTES * Settings.MAX_FILES_PER_ANALYSIS
    CORS(app, origins=Settings.ALLOWED_ORIGINS)
    app.register_blueprint(document_analysis_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({"service": Settings.APP_NAME, "disclaimer": MANDATORY_LEGAL_DISCLAIMER})

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host=Settings.HOST, port=Settings.PORT, debug=Settings.DEBUG)
