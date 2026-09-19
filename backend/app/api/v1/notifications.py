from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import User
from backend.app.models.operations import NotificationRecord

router = APIRouter(prefix="/notifications", tags=["Internal Notifications"])

class NotificationItem(BaseModel):
    id: str
    hospital_id: str
    recipient_role: str
    title: str
    message: str
    severity: str
    status: str
    created_at: str

@router.get("", response_model=List[NotificationItem])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Lists internal notifications relevant to the user's role and hospital."""
    query = db.query(NotificationRecord)
    if not tenant_ctx.is_platform_admin:
        query = query.filter(NotificationRecord.hospital_id == tenant_ctx.hospital_id)
        
    # Match role or specific recipient
    query = query.filter(
        (NotificationRecord.recipient_role == current_user.role) |
        (NotificationRecord.recipient_id == current_user.id) |
        (NotificationRecord.recipient_role == "ALL")
    )

    notifs = query.order_by(NotificationRecord.created_at.desc()).limit(50).all()
    return [
        NotificationItem(
            id=n.id,
            hospital_id=n.hospital_id,
            recipient_role=n.recipient_role,
            title=n.title,
            message=n.message,
            severity=n.severity,
            status=n.status,
            created_at=n.created_at.isoformat()
        )
        for n in notifs
    ]

@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Marks a notification as READ."""
    notif = db.query(NotificationRecord).filter(NotificationRecord.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.status = "READ"
    notif.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "status": "READ"}
