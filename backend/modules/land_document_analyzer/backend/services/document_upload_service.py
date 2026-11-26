"""Secure document upload, magic-byte content validation, storage, replacement, and deletion."""
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modules.land_document_analyzer.backend.config.settings import Settings
from modules.land_document_analyzer.backend.utils.security import get_safe_logger, sanitize_filename

logger = get_safe_logger(__name__)

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

# Known executable / dangerous magic signatures
DANGEROUS_SIGNATURES = (
    b"MZ",                # Windows PE/EXE/DLL
    b"\x7fELF",           # Linux ELF binary
    b"\xca\xfe\xba\xbe",  # Mach-O / Java class
    b"#!/",               # Shell / script shebang
    b"#! ",               # Shebang with space
    b"<!DOCTYPE html",    # HTML script payload
    b"<html",
    b"<script",
    b"<?php",
)

VALID_MAGIC_PREFIXES = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


class DocumentUploadError(ValueError):
    """Raised when an uploaded file fails security, size, or content validation."""


class DocumentUploadService:
    """Handles secure validation, persistence, replacement, and deletion of property documents."""

    def __init__(self, upload_dir: Optional[Path] = None):
        Settings.ensure_directories()
        self.upload_dir = Path(upload_dir) if upload_dir else Settings.UPLOAD_DIR
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def validate_file_content(self, filename: str, content: bytes) -> Tuple[str, str]:
        """
        Validates extension, file size, and true binary magic bytes (not just filename extension).
        Returns (sanitized_filename, detected_mime_type).
        """
        if not content:
            raise DocumentUploadError("Uploaded file is empty.")

        if len(content) > Settings.MAX_FILE_SIZE_BYTES:
            raise DocumentUploadError(
                f"File exceeds maximum size limit of {Settings.MAX_FILE_SIZE_MB} MB."
            )

        safe_name = sanitize_filename(filename)
        ext = Path(safe_name).suffix.lower()

        if ext in Settings.BLOCKED_EXTENSIONS:
            raise DocumentUploadError(f"Executable or script files ('{ext}') are strictly prohibited.")

        if ext not in Settings.ALLOWED_EXTENSIONS:
            raise DocumentUploadError(
                f"Unsupported file extension '{ext}'. Allowed: PDF, JPG, JPEG, PNG."
            )

        header = content[:64]
        header_lower = header.lstrip().lower()
        for sig in DANGEROUS_SIGNATURES:
            if header.startswith(sig) or header_lower.startswith(sig.lower()):
                raise DocumentUploadError("Executable or unsafe binary content detected and blocked.")

        # Detect MIME from content
        detected_mime = self._detect_mime(content)
        if detected_mime not in Settings.ALLOWED_MIME_TYPES:
            raise DocumentUploadError(
                f"File content type '{detected_mime}' does not match an allowed PDF/JPEG/PNG document."
            )

        # Ensure extension aligns with content type
        if ext == ".pdf" and detected_mime != "application/pdf":
            raise DocumentUploadError("File has .pdf extension but content is not a valid PDF.")
        if ext in {".jpg", ".jpeg"} and detected_mime != "image/jpeg":
            raise DocumentUploadError("File has JPEG extension but content is not a valid JPEG image.")
        if ext == ".png" and detected_mime != "image/png":
            raise DocumentUploadError("File has .png extension but content is not a valid PNG image.")

        return safe_name, detected_mime

    @staticmethod
    def _detect_mime(content: bytes) -> str:
        for mime, prefixes in VALID_MAGIC_PREFIXES.items():
            if any(content.startswith(p) for p in prefixes):
                return mime
        if MAGIC_AVAILABLE:
            try:
                return magic.from_buffer(content[:2048], mime=True) or "application/octet-stream"
            except Exception:
                pass
        return "application/octet-stream"

    def save_document(
        self,
        analysis_id: str,
        filename: str,
        content: bytes,
        user_declared_type: Optional[str] = None,
        is_official_portal_upload: bool = False,
        source_portal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validates and stores an uploaded document securely under an isolated analysis folder."""
        safe_name, mime_type = self.validate_file_content(filename, content)
        document_id = f"doc_{uuid.uuid4().hex[:12]}"
        sha256_hash = hashlib.sha256(content).hexdigest()

        analysis_dir = self.upload_dir / sanitize_filename(analysis_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        stored_path = analysis_dir / f"{document_id}_{safe_name}"
        stored_path.write_bytes(content)

        logger.info("Stored validated document %s (%s, %d bytes)", document_id, mime_type, len(content))

        return {
            "document_id": document_id,
            "analysis_id": analysis_id,
            "original_filename": safe_name,
            "stored_path": str(stored_path),
            "mime_type": mime_type,
            "file_size_bytes": len(content),
            "sha256": sha256_hash,
            "user_declared_type": user_declared_type,
            "is_official_portal_upload": is_official_portal_upload,
            "source_portal": source_portal,
            "upload_status": "uploaded",
            "processing_status": "pending",
            "extraction_status": "pending",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

    def replace_document(
        self, existing_record: Dict[str, Any], new_filename: str, new_content: bytes
    ) -> Dict[str, Any]:
        """Replaces an existing stored document after validating the new file."""
        self.delete_document_file(existing_record.get("stored_path"))
        updated = self.save_document(
            analysis_id=existing_record["analysis_id"],
            filename=new_filename,
            content=new_content,
            user_declared_type=existing_record.get("user_declared_type"),
            is_official_portal_upload=existing_record.get("is_official_portal_upload", False),
            source_portal=existing_record.get("source_portal"),
        )
        updated["replaced_document_id"] = existing_record.get("document_id")
        return updated

    @staticmethod
    def delete_document_file(stored_path: Optional[str]) -> bool:
        """Securely deletes a stored document file on user request."""
        if not stored_path:
            return False
        path = Path(stored_path)
        if path.exists() and path.is_file():
            path.unlink()
            return True
        return False
