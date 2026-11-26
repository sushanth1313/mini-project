"""Shared persistent Support Ticket & Notification helpers backed by SQLite."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import PortalNotification, SupportTicket, db

TICKET_CATEGORIES = [
    "Property Valuation",
    "GIS / Map",
    "Document Analyzer",
    "PDF Report",
    "Login / Account",
    "Technical Bug",
    "Feature Request",
    "Other",
]

TICKET_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"]
TICKET_STATUSES = ["OPEN", "IN_PROGRESS", "AWAITING_USER", "RESOLVED", "CLOSED"]
ALLOWED_ATTACHMENT_EXTS = {".png", ".jpg", ".jpeg", ".pdf"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

ATTACH_DIR = Path(__file__).resolve().parents[3] / "uploads" / "support_attachments"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_notification(
    recipient_type: str,
    recipient_target: str,
    category: str,
    title: str,
    message: str,
    ticket_id: Optional[str] = None,
    link: Optional[str] = None,
) -> PortalNotification:
    rec = PortalNotification(
        notification_id=f"NTF-{uuid.uuid4().hex[:8].upper()}",
        recipient_type=recipient_type,
        recipient_target=str(recipient_target),
        ticket_id=ticket_id,
        category=category,
        title=title[:200],
        message=message[:1000],
        link=link,
        is_read=False,
        read_by_json="[]",
    )
    db.session.add(rec)
    return rec


def notify_roles_for_new_ticket(ticket: SupportTicket) -> None:
    msg = f"[{ticket.priority}] {ticket.category}: {ticket.title} (from {ticket.user_name})"
    for role in ("SUPPORT_ADMIN", "SUPER_ADMIN"):
        create_notification(
            recipient_type="ADMIN_ROLE",
            recipient_target=role,
            category="NEW_SUPPORT_TICKET",
            title=f"New Ticket {ticket.ticket_id}",
            message=msg,
            ticket_id=ticket.ticket_id,
            link=f"/admin/support?ticket={ticket.ticket_id}",
        )


def notify_admins_for_user_reply(ticket: SupportTicket) -> None:
    msg = f"User {ticket.user_name} replied on {ticket.ticket_id}: {ticket.title}"
    if ticket.assigned_admin_id:
        create_notification(
            recipient_type="ADMIN_ID",
            recipient_target=ticket.assigned_admin_id,
            category="USER_TICKET_REPLY",
            title=f"User Reply on {ticket.ticket_id}",
            message=msg,
            ticket_id=ticket.ticket_id,
            link=f"/admin/support?ticket={ticket.ticket_id}",
        )
    else:
        create_notification(
            recipient_type="ADMIN_ROLE",
            recipient_target="SUPPORT_ADMIN",
            category="USER_TICKET_REPLY",
            title=f"User Reply on {ticket.ticket_id}",
            message=msg,
            ticket_id=ticket.ticket_id,
            link=f"/admin/support?ticket={ticket.ticket_id}",
        )
    create_notification(
        recipient_type="ADMIN_ROLE",
        recipient_target="SUPER_ADMIN",
        category="USER_TICKET_REPLY",
        title=f"User Reply on {ticket.ticket_id}",
        message=msg,
        ticket_id=ticket.ticket_id,
        link=f"/admin/support?ticket={ticket.ticket_id}",
    )


def notify_user_for_admin_reply(ticket: SupportTicket, admin_name: str) -> None:
    if not ticket.user_id:
        return
    create_notification(
        recipient_type="USER_ID",
        recipient_target=str(ticket.user_id),
        category="ADMIN_TICKET_REPLY",
        title=f"Support Reply on {ticket.ticket_id}",
        message=f"{admin_name} responded to '{ticket.title}'.",
        ticket_id=ticket.ticket_id,
        link=f"/student/account?tab=help&ticket={ticket.ticket_id}",
    )


def notify_user_for_status_update(ticket: SupportTicket, new_status: str) -> None:
    if not ticket.user_id:
        return
    create_notification(
        recipient_type="USER_ID",
        recipient_target=str(ticket.user_id),
        category="TICKET_STATUS_UPDATED",
        title=f"Ticket {ticket.ticket_id} is now {new_status}",
        message=f"Status updated to {new_status} for '{ticket.title}'.",
        ticket_id=ticket.ticket_id,
        link=f"/student/account?tab=help&ticket={ticket.ticket_id}",
    )


def append_ticket_message(
    ticket: SupportTicket,
    sender_type: str,
    sender_id: str,
    sender_name: str,
    sender_role: str,
    body: str,
) -> List[Dict[str, Any]]:
    try:
        msgs = json.loads(ticket.messages_json) if ticket.messages_json else []
    except Exception:
        msgs = []
    msgs.append({
        "message_id": f"MSG-{uuid.uuid4().hex[:8].upper()}",
        "sender_type": sender_type,
        "sender_id": str(sender_id),
        "sender_name": sender_name,
        "sender_role": sender_role,
        "body": body.strip(),
        "timestamp": now_iso(),
    })
    ticket.messages_json = json.dumps(msgs)
    ticket.updated_at = datetime.utcnow()
    return msgs


def save_ticket_attachment(file_storage, ticket_id: str) -> tuple[Optional[str], Optional[str]]:
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None, None
    orig = os.path.basename(file_storage.filename)
    ext = os.path.splitext(orig)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTS:
        raise ValueError("Unsupported attachment format. Allowed: PNG, JPG, JPEG, PDF.")
    content = file_storage.read()
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError("Attachment exceeds 10 MB limit.")
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{ticket_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ATTACH_DIR / safe_name
    dest.write_bytes(content)
    return orig, str(dest)


def get_admin_notifications(admin_id: str, role: str) -> Dict[str, Any]:
    rows = PortalNotification.query.filter(
        ((PortalNotification.recipient_type == "ADMIN_ROLE") & (PortalNotification.recipient_target == role))
        | ((PortalNotification.recipient_type == "ADMIN_ID") & (PortalNotification.recipient_target == admin_id))
    ).order_by(PortalNotification.id.desc()).limit(60).all()
    items = [r.to_dict(viewer_id=admin_id) for r in rows]
    unread = sum(1 for it in items if not it["is_read"])
    return {"notifications": items, "unread_count": unread}


def mark_admin_notification_read(admin_id: str, role: str, notification_id: Optional[str] = None) -> int:
    q = PortalNotification.query.filter(
        ((PortalNotification.recipient_type == "ADMIN_ROLE") & (PortalNotification.recipient_target == role))
        | ((PortalNotification.recipient_type == "ADMIN_ID") & (PortalNotification.recipient_target == admin_id))
    )
    if notification_id:
        q = q.filter(PortalNotification.notification_id == notification_id)
    count = 0
    for r in q.all():
        if r.recipient_type == "ADMIN_ROLE":
            try:
                readers = json.loads(r.read_by_json or "[]")
            except Exception:
                readers = []
            if admin_id not in readers:
                readers.append(admin_id)
                r.read_by_json = json.dumps(readers)
                count += 1
        elif not r.is_read:
            r.is_read = True
            count += 1
    db.session.commit()
    return count
