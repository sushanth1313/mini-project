"""Normal platform user authentication routes (/api/auth/*) backed by SQLite PlatformUser."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Optional, Tuple
from flask import Blueprint, jsonify, request

from models import PlatformUser, db
from .config import AdminConfig
from .database import hash_password, verify_password

user_auth_bp = Blueprint("user_auth", __name__, url_prefix="/api/auth")


def generate_user_token(user: PlatformUser, expiry_minutes: int = 1440) -> str:
    """Create an HMAC-SHA256 bearer token bound cleanly to a verified PlatformUser record."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.user_uid,
        "user_id": user.id,
        "email": user.email,
        "role": (user.role or "user").lower(),
        "token_type": "user",
        "iat": now,
        "exp": now + expiry_minutes * 60,
        "jti": uuid.uuid4().hex,
    }
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(AdminConfig.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"


def verify_portal_bearer_token(token: str) -> Tuple[bool, str, str, Optional[dict]]:
    """
    Verify either a signed PlatformUser JWT token or an active AdminAccount JWT token.
    Returns (is_valid, resolved_role, reason, claims).
    Never accepts unverified client headers for privilege elevation.
    """
    if not token:
        return False, "anonymous", "Missing bearer token.", None
    try:
        from .auth.security import decode_admin_token
        claims = decode_admin_token(token)
    except Exception as exc:
        return False, "anonymous", f"Invalid or expired token: {exc}", None

    token_type = claims.get("token_type")
    if token_type == "user":
        uid = claims.get("sub")
        user = PlatformUser.query.filter_by(user_uid=uid).first()
        if not user:
            return False, "anonymous", "User account no longer exists.", None
        if (user.status or "").upper() != "ACTIVE":
            return False, (user.role or "user").lower(), f"User account is '{user.status}'.", None
        return True, (user.role or "user").lower(), "Authorized platform user", claims

    # Admin token fallback check against database
    from .database import db_instance
    admin_doc = db_instance["admin_accounts"].find_one({"admin_id": claims.get("sub")})
    if not admin_doc or (admin_doc.get("status") or "").upper() != "ACTIVE":
        return False, "anonymous", "Administrator session invalid or inactive.", None
    return True, (admin_doc.get("role") or "admin").lower(), "Authorized administrator", claims


@user_auth_bp.route("/login", methods=["POST"])
def user_login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("email") or data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"error": "Email/username and password are required."}), 400

    # Normal login explicitly resolves ONLY non-admin PlatformUser accounts.
    # Administrators must authenticate via /api/admin/auth/login.
    user = PlatformUser.query.filter(
        (PlatformUser.email == identifier) | (PlatformUser.full_name == identifier)
    ).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"error": "Invalid platform user credentials. Admins must use the protected /admin/login portal."}), 401

    if (user.status or "").upper() != "ACTIVE":
        return jsonify({"error": f"Account is currently '{user.status}'. Contact an administrator."}), 403

    user.last_login_at = datetime.utcnow()
    db.session.commit()
    token = generate_user_token(user)

    return jsonify({
        "token": token,
        "user": user.to_dict(),
        "role": user.role,
        "message": "Signed in to Mysuru Smart Land Valuation Customer Workspace",
    }), 200


@user_auth_bp.route("/register", methods=["POST"])
def user_register():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    taluk = (data.get("preferred_taluk") or "Mysuru").strip()

    if not full_name or not email or len(password) < 6:
        return jsonify({"error": "Provide full_name, valid email, and password (min 6 chars)."}), 400

    if PlatformUser.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409

    user = PlatformUser(
        user_uid=f"USR-{uuid.uuid4().hex[:6].upper()}",
        full_name=full_name,
        email=email,
        phone=(data.get("phone") or "").strip() or None,
        role="STANDARD_USER",
        status="ACTIVE",
        password_hash=hash_password(password),
        preferred_taluk=taluk,
    )
    db.session.add(user)
    db.session.commit()
    token = generate_user_token(user)
    return jsonify({"token": token, "user": user.to_dict(), "role": user.role}), 201


@user_auth_bp.route("/change-password", methods=["POST"])
def user_change_password():
    """Change signed-in customer's password after verifying current password."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Authentication required."}), 401
    token = auth.split(" ", 1)[1].strip()
    ok, _role, msg, claims = verify_portal_bearer_token(token)
    if not ok or not claims or claims.get("token_type") != "user":
        return jsonify({"error": msg or "Valid customer token required."}), 401

    user = PlatformUser.query.filter_by(user_uid=claims.get("sub")).first()
    if not user:
        return jsonify({"error": "User account not found."}), 404

    data = request.get_json(silent=True) or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    if not verify_password(current_pw, user.password_hash):
        return jsonify({"error": "Current password is incorrect."}), 400
    if len(new_pw) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400

    user.password_hash = hash_password(new_pw)
    db.session.commit()
    return jsonify({"message": "Password updated cleanly."}), 200
