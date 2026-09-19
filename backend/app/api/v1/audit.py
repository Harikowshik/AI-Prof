from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.operations import AuditEvent
from backend.app.models.tenant import User

router = APIRouter(prefix="/audit", tags=["Audit Trail"])

class AuditEventResponse(BaseModel):
    id: str
    hospital_id: Optional[str]
    user_id: Optional[str]
    user_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    old_state: Optional[dict] = None
    new_state: Optional[dict] = None
    details: Optional[Any] = None
    reason: Optional[str] = None
    correlation_id: Optional[str] = None
    timestamp: str
    created_at: str

@router.get("", response_model=List[AuditEventResponse])
def get_audit_logs(
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Returns immutable audit logs strictly scoped to caller's hospital tenant.
    Captures who, what, when, old state, and new state.
    """
    query = db.query(AuditEvent)
    if not tenant_ctx.is_platform_admin:
        query = query.filter(AuditEvent.hospital_id == tenant_ctx.hospital_id)
    elif tenant_ctx.hospital_id:
        query = query.filter(AuditEvent.hospital_id == tenant_ctx.hospital_id)

    if action:
        query = query.filter(AuditEvent.action.ilike(f"%{action}%"))

    logs = query.order_by(AuditEvent.timestamp.desc()).offset(offset).limit(limit).all()

    # Pre-fetch users for name enrichment
    user_ids = {l.user_id for l in logs if l.user_id}
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {u.id: f"{u.full_name} ({u.role})" for u in users}

    results = []
    for l in logs:
        ts_iso = l.timestamp.isoformat() if l.timestamp else ""
        actor = user_map.get(l.user_id, l.user_id or "SYSTEM_DAEMON")
        payload = l.new_state if l.new_state else (l.old_state if l.old_state else ({"reason": l.reason} if l.reason else {}))

        results.append(AuditEventResponse(
            id=l.id,
            hospital_id=l.hospital_id,
            user_id=l.user_id,
            user_name=actor,
            action=l.action,
            entity_type=l.entity_type,
            entity_id=l.entity_id,
            resource_type=l.entity_type,
            resource_id=l.entity_id,
            old_state=l.old_state,
            new_state=l.new_state,
            details=payload,
            reason=l.reason,
            correlation_id=l.correlation_id,
            timestamp=ts_iso,
            created_at=ts_iso
        ))
    return results
