"""
Admin Support Center & Notification Routes (/api/admin/support/*, /api/admin/notifications/*).
"""
import os
from flask import send_file
from models import AdminAccount, CustomerEnquiry, SupportTicket, db
from ..compat_flask import Blueprint, g, jsonify, request
from ..auth.security import require_permission
from ..audit.service import record_audit_log
from .service import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    append_ticket_message,
    get_admin_notifications,
    mark_admin_notification_read,
    notify_user_for_admin_reply,
    notify_user_for_status_update,
)

support_bp = Blueprint("admin_support", __name__, url_prefix="/api/admin")


@support_bp.route("/support/tickets", methods=["GET"])
@require_permission("support:view")
def list_support_tickets():
    status_q = (request.args.get("status") or "").strip().upper()
    priority_q = (request.args.get("priority") or "").strip().upper()
    category_q = (request.args.get("category") or "").strip()
    search_q = (request.args.get("search") or "").strip().lower()

    rows = SupportTicket.query.order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc()).all()
    filtered = []
    for r in rows:
        if status_q and r.status != status_q:
            continue
        if priority_q and r.priority != priority_q:
            continue
        if category_q and r.category != category_q:
            continue
        if search_q:
            hay = f"{r.ticket_id} {r.title} {r.user_name} {r.user_email} {r.category}".lower()
            if search_q not in hay:
                continue
        filtered.append(r.to_dict())

    enquiries = [e.to_dict() for e in CustomerEnquiry.query.order_by(CustomerEnquiry.id.desc()).limit(50).all()]
    support_admins = [
        {"admin_id": a.admin_uid, "username": a.username, "full_name": a.full_name, "role": a.role}
        for a in AdminAccount.query.filter(AdminAccount.is_active.is_(True), AdminAccount.role.in_(("SUPPORT_ADMIN", "SUPER_ADMIN"))).all()
    ]

    return jsonify({
        "tickets": filtered,
        "total": len(filtered),
        "open_count": sum(1 for t in rows if t.status in ("OPEN", "IN_PROGRESS", "AWAITING_USER")),
        "high_priority_open_count": sum(1 for t in rows if t.status not in ("RESOLVED", "CLOSED") and t.priority in ("HIGH", "URGENT")),
        "categories": TICKET_CATEGORIES,
        "priorities": TICKET_PRIORITIES,
        "statuses": TICKET_STATUSES,
        "support_admins": support_admins,
        "legacy_enquiries": enquiries,
    }), 200


@support_bp.route("/support/tickets/<ticket_id>", methods=["GET"])
@require_permission("support:view")
def get_support_ticket(ticket_id):
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t:
        return jsonify({"error": "Support ticket not found.", "code": "NOT_FOUND"}), 404
    return jsonify({"ticket": t.to_dict()}), 200


@support_bp.route("/support/tickets/<ticket_id>/reply", methods=["POST"])
@require_permission("support:reply")
def reply_to_ticket(ticket_id):
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t:
        return jsonify({"error": "Support ticket not found.", "code": "NOT_FOUND"}), 404

    data = request.get_json(silent=True) or {}
    body = (data.get("message") or data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Reply message cannot be empty.", "code": "VALIDATION_ERROR"}), 400

    admin = g.current_admin
    if not t.assigned_admin_id:
        t.assigned_admin_id = admin["admin_id"]
        t.assigned_admin_name = admin["full_name"] or admin["username"]

    append_ticket_message(
        t,
        sender_type="ADMIN",
        sender_id=admin["admin_id"],
        sender_name=admin["full_name"] or admin["username"],
        sender_role=admin["role"],
        body=body,
    )
    if t.status == "OPEN":
        t.status = "IN_PROGRESS"
    notify_user_for_admin_reply(t, admin["full_name"] or admin["username"])
    db.session.commit()

    record_audit_log(
        action="SUPPORT_TICKET_REPLIED",
        resource=f"support_tickets/{ticket_id}",
        result="SUCCESS",
        details=f"Admin {admin['username']} replied to {ticket_id}."
    )
    return jsonify({"ticket": t.to_dict()}), 200


@support_bp.route("/support/tickets/<ticket_id>/status", methods=["PATCH"])
@require_permission("support:manage")
def update_ticket_status(ticket_id):
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t:
        return jsonify({"error": "Support ticket not found.", "code": "NOT_FOUND"}), 404

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().upper()
    assigned_id = (data.get("assigned_admin_id") or "").strip()

    updates = []
    if new_status:
        if new_status not in TICKET_STATUSES:
            return jsonify({"error": f"Invalid status. Allowed: {TICKET_STATUSES}", "code": "VALIDATION_ERROR"}), 400
        if new_status != t.status:
            t.status = new_status
            notify_user_for_status_update(t, new_status)
            updates.append(f"status={new_status}")

    if assigned_id:
        adm = AdminAccount.query.filter_by(admin_uid=assigned_id).first()
        if not adm:
            return jsonify({"error": "Assigned admin not found.", "code": "NOT_FOUND"}), 404
        t.assigned_admin_id = adm.admin_uid
        t.assigned_admin_name = adm.full_name or adm.username
        updates.append(f"assigned={adm.username}")

    if not updates:
        return jsonify({"error": "No valid updates provided.", "code": "VALIDATION_ERROR"}), 400

    db.session.commit()
    record_audit_log(
        action="SUPPORT_TICKET_UPDATED",
        resource=f"support_tickets/{ticket_id}",
        result="SUCCESS",
        details=f"Updated ticket {ticket_id}: {', '.join(updates)}"
    )
    return jsonify({"ticket": t.to_dict()}), 200


@support_bp.route("/support/tickets/<ticket_id>/attachment", methods=["GET"])
@require_permission("support:view")
def download_ticket_attachment_admin(ticket_id):
    t = SupportTicket.query.filter_by(ticket_id=ticket_id).first()
    if not t or not t.attachment_path or not os.path.isfile(t.attachment_path):
        return jsonify({"error": "Attachment not found.", "code": "NOT_FOUND"}), 404
    return send_file(t.attachment_path, as_attachment=False, download_name=t.attachment_name or "attachment")


@support_bp.route("/notifications", methods=["GET"])
@require_permission("notifications:view")
def admin_list_notifications():
    admin = g.current_admin
    return jsonify(get_admin_notifications(admin["admin_id"], admin["role"])), 200


@support_bp.route("/notifications/<notification_id>/read", methods=["POST"])
@require_permission("notifications:manage")
def admin_mark_notification_read(notification_id):
    admin = g.current_admin
    updated = mark_admin_notification_read(admin["admin_id"], admin["role"], notification_id=notification_id)
    res = get_admin_notifications(admin["admin_id"], admin["role"])
    res["marked_count"] = updated
    return jsonify(res), 200


@support_bp.route("/notifications/read-all", methods=["POST"])
@require_permission("notifications:manage")
def admin_mark_all_notifications_read():
    admin = g.current_admin
    updated = mark_admin_notification_read(admin["admin_id"], admin["role"], notification_id=None)
    res = get_admin_notifications(admin["admin_id"], admin["role"])
    res["marked_count"] = updated
    return jsonify(res), 200
