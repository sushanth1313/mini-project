"""
AI Land Document Analyzer Management Module:
- GET   /api/admin/documents
- GET   /api/admin/documents/<job_id>
- PATCH /api/admin/documents/<job_id>/verification-status
- POST  /api/admin/documents/<job_id>/process-deletion
Supports all 11 Karnataka land document categories.
Strictly prohibits converting an unverified legal finding into a government-certified
result without independent official verification proof.
Records every administrative access to private document jobs in the audit log.
"""
from datetime import datetime, timezone
from ..compat_flask import Blueprint, request, jsonify, g
from ..config import DOCUMENT_CATEGORIES
from ..database import db_instance
from ..auth.security import ROLE_PERMISSIONS, require_permission
from ..audit.service import record_audit_log

documents_bp = Blueprint("admin_documents", __name__, url_prefix="/api/admin/documents")


def _can_inspect_sensitive() -> bool:
    admin = getattr(g, "current_admin", None) or {}
    role = admin.get("role")
    return "documents:inspect_sensitive" in ROLE_PERMISSIONS.get(role, set())


def _mask_sensitive_fields(job: dict) -> dict:
    """Strip sensitive OCR/extracted PII fields unless role holds documents:inspect_sensitive."""
    if _can_inspect_sensitive():
        return job
    masked = dict(job)
    for k in ("raw_text", "raw_text_preview", "extracted_fields", "owner_name", "extracted_evidence", "document_ocr_snippets", "files"):
        if k in masked:
            masked[k] = "[REDACTED — requires documents:inspect_sensitive permission]" if k != "files" else []
    masked["sensitive_redacted"] = True
    return masked


@documents_bp.route("", methods=["GET"])
@require_permission("documents:view")
def list_document_jobs():
    category_q = (request.args.get("category") or "").strip()
    status_q = (request.args.get("status") or "").strip().upper()

    jobs = db_instance["document_analyses"].find({}, {"_id": 0})
    filtered = []
    for j in jobs:
        if category_q and j.get("document_category") != category_q:
            continue
        if status_q and j.get("processing_status") != status_q:
            continue
        filtered.append(_mask_sensitive_fields(j))

    total = len(jobs)
    ocr_success = sum(1 for j in jobs if j.get("ocr_status") == "SUCCESS")
    mismatch_count = sum(1 for j in jobs if j.get("cross_document_mismatch_detected"))
    avg_ocr_conf = round(sum(j.get("ocr_confidence_pct", 0) for j in jobs) / total, 2) if total else 0.0

    return jsonify({
        "jobs": filtered,
        "supported_categories": DOCUMENT_CATEGORIES,
        "sensitive_access_granted": _can_inspect_sensitive(),
        "statistics": {
            "total_jobs": total,
            "ocr_success_count": ocr_success,
            "ocr_failure_count": total - ocr_success,
            "avg_ocr_confidence_pct": avg_ocr_conf,
            "cross_document_mismatch_count": mismatch_count,
            "pending_deletion_requests": sum(1 for j in jobs if j.get("deletion_requested"))
        }
    }), 200


@documents_bp.route("/<job_id>", methods=["GET"])
@require_permission("documents:view")
def inspect_document_job(job_id):
    job = db_instance["document_analyses"].find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        return jsonify({"error": "Document analysis job not found.", "code": "NOT_FOUND"}), 404

    sensitive_granted = _can_inspect_sensitive()
    safe_job = _mask_sensitive_fields(job)

    # Mandatory audit record for every administrative access to document analysis
    record_audit_log(
        action="PRIVATE_DOCUMENT_ANALYSIS_ACCESSED" if sensitive_granted else "DOCUMENT_METADATA_ACCESSED_REDACTED",
        resource=f"document_analyses/{job_id}",
        result="SUCCESS",
        details=f"Accessed document job {job_id} (sensitive_granted={sensitive_granted}, category={job.get('document_category')})."
    )
    return jsonify({"job": safe_job, "sensitive_access_granted": sensitive_granted}), 200

@documents_bp.route("/<job_id>/verification-status", methods=["PATCH"])
@require_permission("documents:inspect_sensitive")
def update_verification_status(job_id):
    """
    Enforces strict provenance policy:
    1. Never allows declaring a property automatically 'LEGALLY_SAFE' or 'GOVERNMENT_CERTIFIED'.
    2. Never allows promoting UNVERIFIED findings to INDEPENDENTLY_VERIFIED_OFFICIAL
       without supplying an official external verification reference (e.g., Bhoomi/Kaveri checksum).
    """
    data = request.get_json(silent=True) or {}
    requested_status = (data.get("official_verification_status") or "").strip().upper()
    official_proof_ref = (data.get("official_verification_reference") or "").strip()

    job = db_instance["document_analyses"].find_one({"job_id": job_id})
    if not job:
        return jsonify({"error": "Document analysis job not found.", "code": "NOT_FOUND"}), 404

    if requested_status in ("GOVERNMENT_CERTIFIED", "LEGALLY_SAFE", "CERTIFIED_CLEAR_TITLE"):
        record_audit_log(
            action="ILLEGAL_DOCUMENT_CERTIFICATION_BLOCKED",
            resource=f"document_analyses/{job_id}",
            result="DENIED",
            details=f"Blocked attempt to set status to '{requested_status}'. Admin portal cannot issue government legal title certification."
        )
        return jsonify({
            "error": "Administrators cannot convert an AI or unverified finding into a government-certified or legally safe title declaration.",
            "code": "PROHIBITED_LEGAL_CERTIFICATION"
        }), 400

    if requested_status == "INDEPENDENTLY_VERIFIED_OFFICIAL" and not official_proof_ref:
        return jsonify({
            "error": "Cannot mark as INDEPENDENTLY_VERIFIED_OFFICIAL without an official_verification_reference digest.",
            "code": "MISSING_OFFICIAL_PROOF"
        }), 400

    if requested_status not in ("UNVERIFIED", "INDEPENDENTLY_VERIFIED_OFFICIAL", "VERIFICATION_FAILED"):
        return jsonify({"error": "Invalid verification status tier.", "code": "VALIDATION_ERROR"}), 400

    provenance = job.get("provenance_layers", {})
    if requested_status == "INDEPENDENTLY_VERIFIED_OFFICIAL":
        provenance["independently_verified_official_info"] = {
            "verification_source": official_proof_ref,
            "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }

    db_instance["document_analyses"].update_one(
        {"job_id": job_id},
        {"$set": {
            "official_verification_status": requested_status,
            "provenance_layers": provenance
        }}
    )
    record_audit_log(
        action="DOCUMENT_VERIFICATION_STATUS_UPDATED",
        resource=f"document_analyses/{job_id}",
        result="SUCCESS",
        details=f"Updated verification tier for {job_id} to {requested_status}."
    )
    updated = db_instance["document_analyses"].find_one({"job_id": job_id}, {"_id": 0})
    return jsonify({"job": updated}), 200

@documents_bp.route("/<job_id>/process-deletion", methods=["POST"])
@require_permission("documents:delete_requests")
def process_document_deletion(job_id):
    job = db_instance["document_analyses"].find_one({"job_id": job_id})
    if not job:
        return jsonify({"error": "Document analysis job not found.", "code": "NOT_FOUND"}), 404

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_instance["document_analyses"].update_one(
        {"job_id": job_id},
        {"$set": {
            "processing_status": "PURGED_BY_RETENTION_POLICY",
            "deletion_requested": False,
            "purged_at": now_iso,
            "provenance_layers": {
                "ai_extracted_info": "[PURGED_PER_USER_REQUEST]",
                "user_provided_info": "[PURGED_PER_USER_REQUEST]",
                "independently_verified_official_info": None,
                "unverified_info": None
            }
        }}
    )
    record_audit_log(
        action="PRIVATE_DOCUMENT_RECORD_PURGED",
        resource=f"document_analyses/{job_id}",
        result="SUCCESS",
        details=f"Processed document deletion request and purged extracted payload for {job_id}."
    )
    updated = db_instance["document_analyses"].find_one({"job_id": job_id}, {"_id": 0})
    return jsonify({"job": updated}), 200


@documents_bp.route("/<job_id>/files/<doc_id>", methods=["GET"])
@require_permission("documents:inspect_sensitive")
def download_uploaded_document_file(job_id, doc_id):
    """Stream an uploaded document file exclusively to authorized administrators with audit logging."""
    import os
    from flask import send_file
    job = db_instance["document_analyses"].find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        return jsonify({"error": "Document analysis job not found.", "code": "NOT_FOUND"}), 404
    match = next((f for f in (job.get("files") or []) if f.get("document_id") == doc_id), None)
    if not match or not match.get("stored_path") or not os.path.isfile(match["stored_path"]):
        return jsonify({"error": "Uploaded document file not found on disk.", "code": "FILE_NOT_FOUND"}), 404

    record_audit_log(
        action="SENSITIVE_UPLOADED_DOCUMENT_VIEWED",
        resource=f"document_analyses/{job_id}/files/{doc_id}",
        result="SUCCESS",
        details=f"Authorized download/view of '{match.get('original_filename')}'."
    )
    return send_file(
        match["stored_path"],
        as_attachment=False,
        download_name=match.get("original_filename") or f"{doc_id}.pdf",
    )
