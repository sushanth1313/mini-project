"""Security utilities: PII-safe logging, filename sanitization, RBAC check, and AI consent guard."""
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from modules.land_document_analyzer.backend.config.settings import Settings

_PII_PATTERNS = [
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[REDACTED_AADHAAR]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[REDACTED_PAN]"),
    (re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
]


class SafePIIFilter(logging.Filter):
    """Redacts Aadhaar, PAN, phone numbers, and emails from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, replacement in _PII_PATTERNS:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
        return True


def get_safe_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        handler.addFilter(SafePIIFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def sanitize_filename(filename: str) -> str:
    """Strips path traversal characters and normalizes filename safely."""
    base = Path(filename or "document").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    cleaned = cleaned.lstrip(".") or "document"
    return cleaned[:160]


def verify_auth_header(headers: Dict[str, str], required_roles: Optional[Tuple[str, ...]] = None) -> Tuple[bool, str, str]:
    """
    Validates Bearer token and enforces backend role permissions (never trusts X-User-Role alone).
    When running inside the integrated Flask app, verifies signed PlatformUser/Admin JWT tokens
    (or optional static API_BEARER_TOKEN). Returns (is_authorized, role, message).
    """
    from flask import has_app_context

    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    token = auth_header.split(" ", 1)[1].strip() if auth_header.startswith("Bearer ") else ""

    if has_app_context():
        if Settings.API_BEARER_TOKEN and token == Settings.API_BEARER_TOKEN:
            role = "analyst"
            if required_roles and role not in required_roles:
                return False, role, f"Role '{role}' is not authorized for this endpoint."
            return True, role, "Authorized"

        if not token:
            return False, "anonymous", "Authentication required. Sign in to access Document Analyzer endpoints."

        try:
            from modules.admin_portal.auth_users import verify_portal_bearer_token
            ok, resolved_role, reason, _claims = verify_portal_bearer_token(token)
        except Exception as exc:
            return False, "anonymous", f"Token verification failed: {exc}"

        if not ok:
            return False, resolved_role, reason

        normalized_allowed = tuple(r.lower() for r in required_roles) if required_roles else None
        if normalized_allowed and resolved_role.lower() not in normalized_allowed:
            return False, resolved_role, f"Role '{resolved_role}' is not authorized for this endpoint."
        return True, resolved_role, "Authorized"

    # Standalone microservice execution mode
    role = (headers.get("X-User-Role") or "analyst").lower()
    if not Settings.API_AUTH_REQUIRED:
        return True, role, "Auth disabled in standalone local mode"
    if not token:
        return False, role, "Missing Bearer authorization token."
    if not Settings.API_BEARER_TOKEN or token != Settings.API_BEARER_TOKEN:
        return False, role, "Invalid authorization token."
    if required_roles and role not in tuple(r.lower() for r in required_roles):
        return False, role, f"Role '{role}' is not authorized for this endpoint."
    return True, role, "Authorized"


def check_external_ai_consent(consent_flag: bool, provider: str) -> Tuple[bool, str]:
    """Prevents transmitting property documents to third-party AI providers without explicit consent."""
    if provider == "local_heuristic":
        return True, "Local on-premise extraction selected (no third-party data transfer)."
    if not consent_flag:
        return (
            False,
            f"External AI provider '{provider}' requires explicit user consent before document transmission.",
        )
    return True, f"User consented to processing with '{provider}'."
