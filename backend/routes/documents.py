"""
Document upload and extraction routes.
POST /api/documents/upload
GET  /api/properties/:id/documents
"""
import os
import uuid
import logging
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app, send_file
from models import db, Property, Document, DocumentExtraction, VerificationItem
from documents.extractor import extract_from_document

log = logging.getLogger(__name__)
documents_bp = Blueprint("documents", __name__, url_prefix="/api/documents")

ALLOWED = {"pdf", "jpg", "jpeg", "png"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


@documents_bp.route("/upload", methods=["POST"])
def upload_document():
    """Upload a document and run extraction."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    prop_id = request.form.get("property_id")

    if not prop_id:
        return jsonify({"error": "property_id is required"}), 400
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not _allowed(file.filename):
        return jsonify({"error": f"File type not allowed. Allowed: {', '.join(ALLOWED)}"}), 400

    prop = Property.query.get(prop_id)
    if not prop:
        return jsonify({"error": f"Property {prop_id} not found"}), 404

    # Check size (10MB limit enforced by Flask but also explicit check)
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > 10 * 1024 * 1024:
        return jsonify({"error": "File size exceeds 10MB limit"}), 400

    # Save file securely
    original_filename = file.filename
    ext = original_filename.rsplit(".", 1)[1].lower()
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, safe_name)
    file.save(file_path)

    # Create DB record
    doc = Document(
        property_id=int(prop_id),
        filename=safe_name,
        original_filename=secure_filename(original_filename),
        file_type=ext,
        file_size_bytes=file_size,
        upload_path=file_path,
        extraction_status="PROCESSING",
    )
    db.session.add(doc)
    db.session.flush()

    # Run extraction
    try:
        extraction_result = extract_from_document(file_path, ext)
        fields = extraction_result.get("fields", {})

        doc_type = fields.get("document_type")
        if not fields.get("is_property_document", True):
            doc_type = fields.get("relevance_note", "Not a property document")
            
        extraction = DocumentExtraction(
            document_id=doc.id,
            raw_text=extraction_result.get("text", "")[:50000],  # cap
            owner_name=fields.get("owner_name"),
            survey_number=fields.get("survey_number"),
            document_type=doc_type,
            village=fields.get("village"),
            taluk=fields.get("taluk"),
            district=fields.get("district"),
            area_mentioned=fields.get("area_mentioned"),
            dates_mentioned=str(fields.get("dates_mentioned", [])),
            registration_ref=fields.get("registration_ref"),
            extraction_method=extraction_result.get("method", "none"),
        )
        db.session.add(extraction)
        doc.extraction_status = "DONE"

        # Update verification items if fields found
        if fields.get("is_property_document", True):
            _update_verification_from_extraction(int(prop_id), fields)

    except Exception as e:
        log.error(f"Extraction error: {e}", exc_info=True)
        doc.extraction_status = "FAILED"
        db.session.add(DocumentExtraction(
            document_id=doc.id,
            raw_text="",
            extraction_method=f"error: {str(e)[:100]}",
        ))

    db.session.commit()

    result = doc.to_dict()
    if doc.extraction:
        result["extraction"] = doc.extraction.to_dict()
        result["extraction_warnings"] = extraction_result.get("warnings", []) if "extraction_result" in dir() else []

    return jsonify({"document": result, "message": "Document uploaded and processed"}), 201


@documents_bp.route("/<int:doc_id>", methods=["GET"])
def get_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    result = doc.to_dict()
    if doc.extraction:
        result["extraction"] = doc.extraction.to_dict()
    return jsonify(result)


@documents_bp.route("/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    # Delete file
    if os.path.exists(doc.upload_path or ""):
        try:
            os.remove(doc.upload_path)
        except Exception as e:
            log.warning(f"Could not delete file: {e}")
    db.session.delete(doc)
    db.session.commit()
    return jsonify({"message": "Document deleted"})


def _update_verification_from_extraction(property_id: int, fields: dict):
    """Mark verification items as EXTRACTED if document provided relevant info."""
    if not fields.get("is_property_document", True):
        return  # Do not extract property data from a CV/Resume

    if fields.get("survey_number"):
        _update_vi(property_id, "survey_number", "EXTRACTED",
                   f"Extracted: {fields['survey_number']}")
    if fields.get("document_type"):
        _update_vi(property_id, "registration_details", "EXTRACTED",
                   f"Document type found: {fields['document_type']}")
    if fields.get("owner_name"):
        _update_vi(property_id, "seller_identity", "EXTRACTED",
                   f"Name extracted: {fields['owner_name']} — verify with official ID")


def _update_vi(property_id: int, key: str, status: str, notes: str):
    vi = VerificationItem.query.filter_by(property_id=property_id, item_key=key).first()
    if vi and vi.status == "NEEDS_VERIFICATION":
        vi.status = status
        vi.notes = notes
