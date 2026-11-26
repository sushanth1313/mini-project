"""
Customer Workspace & Account API routes (/api/customer/*):
- Scoped live SQLite dashboard summary (newly registered user sees clean 0 counts, never broken errors)
- Saved properties shortlist
- Customer profile & password management (authenticated via Bearer token)
- Help / support enquiries persisted to SQLite
(Plans & Billing removed per product simplification)
"""
from flask import Blueprint, jsonify, request

from models import (
    CustomerEnquiry,
    Document,
    PlatformUser,
    Property,
    PropertyEvaluation,
    Report,
    SavedProperty,
    db,
)
from modules.admin_portal.auth.security import require_permission
from modules.admin_portal.auth_users import verify_portal_bearer_token

customer_bp = Blueprint("customer", __name__, url_prefix="/api/customer")


def _extract_current_user():
    """Return authenticated PlatformUser (or None for anonymous guest)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    ok, _role, _msg, claims = verify_portal_bearer_token(token)
    if not ok or not claims or claims.get("token_type") != "user":
        return None
    uid = claims.get("user_id")
    if uid is None:
        return PlatformUser.query.filter_by(user_uid=claims.get("sub")).first()
    return PlatformUser.query.get(int(uid))


@customer_bp.route("/dashboard-summary", methods=["GET"])
def dashboard_summary():
    """
    Return real SQLite counts scoped strictly to the signed-in customer when authenticated.
    Newly registered customers see clean 0 counts without broken errors or global data bleed.
    Guest browsers see unowned guest-session counts (user_id IS NULL).
    """
    user = _extract_current_user()
    if user:
        user_props = Property.query.filter_by(user_id=user.id).all()
        prop_ids = [p.id for p in user_props]
        props_count = len(user_props)
        evals_count = PropertyEvaluation.query.filter(PropertyEvaluation.property_id.in_(prop_ids)).count() if prop_ids else 0
        reports_count = Report.query.filter(Report.property_id.in_(prop_ids)).count() if prop_ids else 0
        sqlite_docs_count = Document.query.filter(Document.property_id.in_(prop_ids)).count() if prop_ids else 0
        saved_count = SavedProperty.query.filter_by(user_id=user.id).count()
        enquiries_count = CustomerEnquiry.query.filter_by(user_id=user.id).count()
    else:
        guest_props = Property.query.filter(Property.user_id.is_(None)).all()
        prop_ids = [p.id for p in guest_props]
        props_count = len(guest_props)
        evals_count = PropertyEvaluation.query.filter(PropertyEvaluation.property_id.in_(prop_ids)).count() if prop_ids else 0
        reports_count = Report.query.filter(Report.property_id.in_(prop_ids)).count() if prop_ids else 0
        sqlite_docs_count = Document.query.filter(Document.property_id.in_(prop_ids)).count() if prop_ids else 0
        saved_count = SavedProperty.query.filter(SavedProperty.user_id.is_(None)).count()
        enquiries_count = 0

    analyzer_docs_count = 0
    analyzer_analyses_count = 0
    try:
        from modules.land_document_analyzer.backend.app import _pipeline
        prop_id_strs = {str(pid) for pid in prop_ids}
        analyses = [
            a for a in _pipeline.db.collection("analyses").find()
            if str((a.get("property_info") or {}).get("property_id", "")).strip() in prop_id_strs
        ]
        analyzer_analyses_count = len(analyses)
        analyzer_docs_count = sum(len(a.get("documents") or []) for a in analyses)
    except Exception:
        pass

    return jsonify({
        "scoped_to_user": bool(user),
        "counts": {
            "properties": props_count,
            "evaluations": evals_count,
            "reports": reports_count,
            "saved_properties": saved_count,
            "documents_uploaded": sqlite_docs_count,
            "document_analyses": analyzer_analyses_count,
            "documents_analyzed_total": max(sqlite_docs_count, analyzer_docs_count),
            "enquiries": enquiries_count,
        },
        "user": user.to_dict() if user else None,
    }), 200


@customer_bp.route("/profile", methods=["GET", "PUT"])
def manage_profile():
    user = _extract_current_user()
    if not user:
        return jsonify({"error": "Sign in required to view or update account profile.", "code": "AUTH_REQUIRED"}), 401

    if request.method == "GET":
        return jsonify({"user": user.to_dict()}), 200

    data = request.get_json(silent=True) or {}
    if data.get("full_name"):
        user.full_name = str(data["full_name"]).strip()[:150]
    if "phone" in data:
        user.phone = (str(data["phone"]).strip() or None) if data["phone"] is not None else None
    if data.get("preferred_taluk"):
        user.preferred_taluk = str(data["preferred_taluk"]).strip()[:100]
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": "Account profile updated."}), 200


@customer_bp.route("/saved-properties", methods=["GET", "POST"])
def saved_properties():
    user = _extract_current_user()
    uid = user.id if user else None

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        prop_id = data.get("property_id")
        if not prop_id or not Property.query.get(int(prop_id)):
            return jsonify({"error": "Valid property_id is required."}), 400
        prop_id = int(prop_id)
        existing = SavedProperty.query.filter_by(user_id=uid, property_id=prop_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return jsonify({"saved": False, "property_id": prop_id}), 200
        sp = SavedProperty(user_id=uid, property_id=prop_id, note=(data.get("note") or "").strip()[:300] or None)
        db.session.add(sp)
        db.session.commit()
        return jsonify({"saved": True, "item": sp.to_dict()}), 201

    rows = SavedProperty.query.filter_by(user_id=uid).order_by(SavedProperty.id.desc()).all()
    items = []
    for sp in rows:
        prop = Property.query.get(sp.property_id)
        if not prop:
            continue
        d = prop.to_dict()
        latest_ev = sorted(prop.evaluations, key=lambda e: e.id, reverse=True)
        d["latest_evaluation"] = latest_ev[0].to_dict() if latest_ev else None
        d["saved_note"] = sp.note
        d["saved_at"] = sp.created_at.isoformat() if sp.created_at else None
        items.append(d)
    return jsonify({"saved_properties": items, "count": len(items)}), 200


@customer_bp.route("/enquiries", methods=["GET", "POST"])
def enquiries():
    user = _extract_current_user()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or (user.full_name if user else "")).strip()
        email = (data.get("email") or (user.email if user else "")).strip()
        subject = (data.get("subject") or "").strip()
        message = (data.get("message") or "").strip()
        if not name or not email or not subject or not message:
            return jsonify({"error": "name, email, subject, and message are required."}), 400
        enq = CustomerEnquiry(
            user_id=user.id if user else None,
            property_id=int(data["property_id"]) if data.get("property_id") else None,
            name=name[:120],
            email=email[:150],
            phone=(data.get("phone") or "").strip()[:40] or None,
            taluk=(data.get("taluk") or "Mysuru").strip()[:80],
            subject=subject[:200],
            message=message[:2000],
            status="OPEN",
        )
        db.session.add(enq)
        db.session.commit()
        return jsonify({"enquiry": enq.to_dict(), "message": "Help request submitted cleanly."}), 201

    if user:
        rows = CustomerEnquiry.query.filter_by(user_id=user.id).order_by(CustomerEnquiry.id.desc()).limit(50).all()
    else:
        rows = []
    return jsonify({"enquiries": [r.to_dict() for r in rows]}), 200


@customer_bp.route("/admin/enquiries", methods=["GET"])
@require_permission("users:view")
def admin_list_enquiries():
    rows = CustomerEnquiry.query.order_by(CustomerEnquiry.id.desc()).limit(100).all()
    return jsonify({"enquiries": [r.to_dict() for r in rows]}), 200


# ── USER SUPPORT TICKETS & PERSISTENT NOTIFICATIONS ───────────────────────────

@customer_bp.route("/support/tickets", methods=["GET", "POST"])
def user_support_tickets():
    import uuid
    from models import SupportTicket
    from modules.admin_portal.support.service import (
        TICKET_CATEGORIES,
        TICKET_PRIORITIES,
        append_ticket_message,
        notify_roles_for_new_ticket,
        save_ticket_attachment,
    )

    user = _extract_current_user()
    if not user:
        return jsonify({"error": "Please sign in to submit and track support tickets.", "code": "AUTH_REQUIRED"}), 401

    if request.method == "POST":
        if request.content_type and "multipart/form-data" in request.content_type:
            title = (request.form.get("title") or "").strip()
            description = (request.form.get("description") or "").strip()
            category = (request.form.get("category") or "Other").strip()
            priority = (request.form.get("priority") or "MEDIUM").strip().upper()
            prop_id = request.form.get("property_id")
            attachment = request.files.get("attachment")
        else:
            data = request.get_json(silent=True) or {}
            title = (data.get("title") or "").strip()
            description = (data.get("description") or "").strip()
            category = (data.get("category") or "Other").strip()
            priority = (data.get("priority") or "MEDIUM").strip().upper()
            prop_id = data.get("property_id")
            attachment = None

        if not title or not description:
            return jsonify({"error": "Issue title and description are required."}), 400
        if category not in TICKET_CATEGORIES:
            category = "Other"
        if priority not in TICKET_PRIORITIES:
            priority = "MEDIUM"

        ticket_id = f"TKT-{uuid.uuid4().hex[:6].upper()}"
        att_name, att_path = None, None
        if attachment:
            try:
                att_name, att_path = save_ticket_attachment(attachment, ticket_id)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

        t = SupportTicket(
            ticket_id=ticket_id,
            user_id=user.id,
            user_uid=user.user_uid,
            user_name=user.full_name,
            user_email=user.email,
            property_id=int(prop_id) if prop_id else None,
            title=title[:200],
            description=description[:4000],
            category=category,
            priority=priority,
            status="OPEN",
            attachment_name=att_name,
            attachment_path=att_path,
        )
        append_ticket_message(
            t,
            sender_type="USER",
            sender_id=user.user_uid,
            sender_name=user.full_name,
            sender_role=user.role or "STANDARD_USER",
            body=description,
        )
        db.session.add(t)
        db.session.flush()
        notify_roles_for_new_ticket(t)
        db.session.commit()
        return jsonify({"ticket": t.to_dict(), "message": f"Support ticket {ticket_id} submitted."}), 201

    rows = SupportTicket.query.filter_by(user_id=user.id).order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc()).all()
    return jsonify({
        "tickets": [r.to_dict() for r in rows],
        "categories": TICKET_CATEGORIES,
        "priorities": TICKET_PRIORITIES,
    }), 200


@customer_bp.route("/support/tickets/<ticket_id>", methods=["GET"])
def user_get_support_ticket(ticket_id):
    from models import SupportTicket
    user = _extract_current_user()
    if not user:
        return jsonify({"error": "Sign in required.", "code": "AUTH_REQUIRED"}), 401
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t:
        return jsonify({"error": "Ticket not found."}), 404
    if t.user_id != user.id:
        return jsonify({"error": "You can only access your own support tickets.", "code": "FORBIDDEN"}), 403
    return jsonify({"ticket": t.to_dict()}), 200


@customer_bp.route("/support/tickets/<ticket_id>/reply", methods=["POST"])
def user_reply_support_ticket(ticket_id):
    from models import SupportTicket
    from modules.admin_portal.support.service import append_ticket_message, notify_admins_for_user_reply

    user = _extract_current_user()
    if not user:
        return jsonify({"error": "Sign in required.", "code": "AUTH_REQUIRED"}), 401
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t:
        return jsonify({"error": "Ticket not found."}), 404
    if t.user_id != user.id:
        return jsonify({"error": "You can only reply to your own support tickets.", "code": "FORBIDDEN"}), 403

    data = request.get_json(silent=True) or {}
    body = (data.get("message") or data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Reply message cannot be empty."}), 400

    append_ticket_message(
        t,
        sender_type="USER",
        sender_id=user.user_uid,
        sender_name=user.full_name,
        sender_role=user.role or "STANDARD_USER",
        body=body,
    )
    if t.status == "AWAITING_USER":
        t.status = "IN_PROGRESS"
    notify_admins_for_user_reply(t)
    db.session.commit()
    return jsonify({"ticket": t.to_dict()}), 200


@customer_bp.route("/support/tickets/<ticket_id>/attachment", methods=["GET"])
def user_download_ticket_attachment(ticket_id):
    import os
    from flask import send_file
    from models import SupportTicket
    user = _extract_current_user()
    if not user:
        return jsonify({"error": "Sign in required.", "code": "AUTH_REQUIRED"}), 401
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t:
        return jsonify({"error": "Ticket not found."}), 404
    if t.user_id != user.id:
        return jsonify({"error": "Forbidden.", "code": "FORBIDDEN"}), 403
    if not t.attachment_path or not os.path.isfile(t.attachment_path):
        return jsonify({"error": "Attachment not found."}), 404
    return send_file(t.attachment_path, as_attachment=False, download_name=t.attachment_name or "attachment")


@customer_bp.route("/notifications", methods=["GET"])
def user_list_notifications():
    from models import PortalNotification
    user = _extract_current_user()
    if not user:
        return jsonify({"notifications": [], "unread_count": 0}), 200
    rows = PortalNotification.query.filter_by(
        recipient_type="USER_ID",
        recipient_target=str(user.id),
    ).order_by(PortalNotification.id.desc()).limit(40).all()
    items = [r.to_dict() for r in rows]
    return jsonify({
        "notifications": items,
        "unread_count": sum(1 for it in items if not it["is_read"]),
    }), 200


@customer_bp.route("/notifications/read-all", methods=["POST"])
def user_mark_all_notifications_read():
    from models import PortalNotification
    user = _extract_current_user()
    if not user:
        return jsonify({"notifications": [], "unread_count": 0}), 200
    PortalNotification.query.filter_by(
        recipient_type="USER_ID",
        recipient_target=str(user.id),
        is_read=False,
    ).update({"is_read": True})
    db.session.commit()
    return jsonify({"unread_count": 0}), 200


@customer_bp.route("/notifications/<notification_id>/read", methods=["POST"])
def user_mark_one_notification_read(notification_id):
    from models import PortalNotification
    user = _extract_current_user()
    if not user:
        return jsonify({"error": "Sign in required."}), 401
    n = PortalNotification.query.filter_by(
        notification_id=notification_id,
        recipient_type="USER_ID",
        recipient_target=str(user.id),
    ).first()
    if n:
        n.is_read = True
        db.session.commit()
    return jsonify({"ok": True}), 200
