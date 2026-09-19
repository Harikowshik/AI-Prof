from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import User
from backend.app.models.healthcare import Patient
from backend.app.models.queue import OutreachTask, CallRecord, EscalationRecord, DocumentationRecord
from backend.app.models.operations import AuditEvent

router = APIRouter(prefix="/escalations", tags=["Escalations & Human-in-the-Loop"])

class EscalationActionRequest(BaseModel):
    action: str # ASSIGN, IN_REVIEW, RESOLVE, CLOSE
    reviewer_id: Optional[str] = None
    reviewer_notes: Optional[str] = None
    resolution_action: Optional[str] = None

class ResolveEscalationRequest(BaseModel):
    status: Optional[str] = "RESOLVED"
    clinical_notes: Optional[str] = ""
    action_taken: Optional[str] = ""
    resolution_action: Optional[str] = ""

class EscalationResponse(BaseModel):
    id: str
    hospital_id: str
    patient_id: str
    patient_name: Optional[str] = None
    mrn: Optional[str] = None
    phone: Optional[str] = None
    campaign_id: str
    outreach_task_id: str
    call_id: Optional[str] = None
    trigger_reason: str
    clinical_indicators: List[Any] = []
    assessment_a: Dict[str, Any] = {}
    assessment_b: Dict[str, Any] = {}
    disagreement_detected: bool = False
    consensus_decision: str = ""
    evidence_citations: List[Any] = []
    status: str
    priority: str
    assigned_reviewer_id: Optional[str] = None
    assigned_reviewer_name: Optional[str] = None
    reviewer_notes: Optional[str] = None
    resolution_action: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    # Frontend UI compatibility fields
    severity: Optional[str] = None
    reason: Optional[str] = None
    red_flags: List[str] = []
    call_transcript: Optional[str] = None

    class Config:
        from_attributes = True

def _enrich_escalation_dict(db: Session, esc: EscalationRecord) -> Dict[str, Any]:
    patient = db.query(Patient).filter(Patient.id == esc.patient_id).first()
    reviewer = db.query(User).filter(User.id == esc.assigned_reviewer_id).first() if esc.assigned_reviewer_id else None

    call = db.query(CallRecord).filter(CallRecord.id == esc.call_id).first() if esc.call_id else None
    if not call:
        call = db.query(CallRecord).filter(CallRecord.outreach_task_id == esc.outreach_task_id).order_by(CallRecord.started_at.desc()).first()

    transcript_text = ""
    if call and isinstance(call.raw_transcript, list) and call.raw_transcript:
        transcript_text = "\n".join([
            f"[{t.get('speaker', 'user').upper()}]: {t.get('text', '')}"
            for t in call.raw_transcript if isinstance(t, dict)
        ])
    elif call:
        transcript_text = str(call.raw_transcript or "")

    red_flags_list = []
    for ind in (esc.clinical_indicators or []):
        if isinstance(ind, dict):
            s = ind.get("symptom") or ind.get("quote")
            if s:
                red_flags_list.append(s)
        elif isinstance(ind, str):
            red_flags_list.append(ind)

    esc_dict = {col.name: getattr(esc, col.name) for col in esc.__table__.columns}
    esc_dict["patient_name"] = f"{patient.first_name} {patient.last_name}" if patient else "Unknown"
    esc_dict["mrn"] = patient.mrn if patient else "N/A"
    esc_dict["phone"] = patient.phone_number if patient else "N/A"
    esc_dict["assigned_reviewer_name"] = reviewer.full_name if reviewer else None

    # Map frontend compatibility aliases
    esc_dict["severity"] = esc.priority
    esc_dict["reason"] = esc.trigger_reason
    esc_dict["red_flags"] = red_flags_list
    esc_dict["call_transcript"] = transcript_text
    
    # Normalize OPEN to PENDING for UI
    if esc_dict.get("status") == "OPEN":
        esc_dict["status"] = "PENDING"

    return esc_dict

@router.get("", response_model=List[EscalationResponse])
def list_escalations(
    status_filter: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """List clinical escalations strictly scoped to caller's hospital."""
    query = db.query(EscalationRecord)
    if not tenant_ctx.is_platform_admin:
        query = query.filter(EscalationRecord.hospital_id == tenant_ctx.hospital_id)
    elif tenant_ctx.hospital_id:
        query = query.filter(EscalationRecord.hospital_id == tenant_ctx.hospital_id)

    if status_filter:
        st_upper = status_filter.upper()
        if st_upper in ["PENDING", "OPEN"]:
            query = query.filter(EscalationRecord.status.in_(["PENDING", "OPEN", "ASSIGNED"]))
        elif st_upper in ["RESOLVED", "CLOSED", "DISMISSED"]:
            query = query.filter(EscalationRecord.status.in_(["RESOLVED", "CLOSED", "DISMISSED"]))
        else:
            query = query.filter(EscalationRecord.status == st_upper)

    if severity:
        query = query.filter(EscalationRecord.priority == severity.upper())

    escalations = query.order_by(EscalationRecord.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for esc in escalations:
        results.append(EscalationResponse(**_enrich_escalation_dict(db, esc)))
    return results

@router.get("/{escalation_id}", response_model=EscalationResponse)
def get_escalation(
    escalation_id: str,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Get single escalation details with complete patient and dual assessment context."""
    esc = db.query(EscalationRecord).filter(EscalationRecord.id == escalation_id).first()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation record not found")
    tenant_ctx.validate_tenant_access(esc.hospital_id)

    return EscalationResponse(**_enrich_escalation_dict(db, esc))

@router.post("/{escalation_id}/action")
def update_escalation_action(
    escalation_id: str,
    req: EscalationActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CLINICAL_REVIEWER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Human-in-the-loop clinical workflow action:
    - ASSIGN: assigns to reviewer
    - IN_REVIEW: review underway
    - RESOLVE: clinician records follow-up action and marks resolved
    - CLOSE: closes case
    All human actions are strictly audited.
    """
    esc = db.query(EscalationRecord).filter(EscalationRecord.id == escalation_id).first()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation record not found")
    tenant_ctx.validate_tenant_access(esc.hospital_id)

    old_status = esc.status
    now = datetime.now(timezone.utc)
    action_upper = req.action.upper()

    if action_upper in ["ASSIGN", "ASSIGNED"]:
        esc.assigned_reviewer_id = req.reviewer_id or current_user.id
        esc.status = "ASSIGNED"
    elif action_upper in ["IN_REVIEW", "REVIEW"]:
        esc.status = "IN_REVIEW"
        if not esc.assigned_reviewer_id:
            esc.assigned_reviewer_id = current_user.id
    elif action_upper in ["RESOLVE", "RESOLVED"]:
        esc.status = "RESOLVED"
        esc.resolution_action = req.resolution_action or "Clinical reviewer evaluated triage consensus and completed intervention."
        esc.resolved_at = now
        if not esc.assigned_reviewer_id:
            esc.assigned_reviewer_id = current_user.id
        
        # Update associated outreach task to COMPLETED
        task = db.query(OutreachTask).filter(OutreachTask.id == esc.outreach_task_id).first()
        if task:
            task.status = "COMPLETED"

        # Update EHR documentation if present
        if esc.call_id:
            doc = db.query(DocumentationRecord).filter(DocumentationRecord.call_id == esc.call_id).first()
            if doc:
                doc.clinical_summary = (doc.clinical_summary or "") + f"\n[CLINICAL INTERVENTION]: {esc.resolution_action}"
                doc.ehr_sync_status = "SYNCED"
                doc.ehr_sync_timestamp = now
    elif action_upper in ["CLOSE", "CLOSED", "DISMISS", "DISMISSED"]:
        esc.status = "CLOSED"
        esc.resolution_action = req.resolution_action or "Case dismissed by clinical reviewer."
        esc.resolved_at = now
        if not esc.assigned_reviewer_id:
            esc.assigned_reviewer_id = current_user.id
        task = db.query(OutreachTask).filter(OutreachTask.id == esc.outreach_task_id).first()
        if task:
            task.status = "COMPLETED"

    if req.reviewer_notes:
        esc.reviewer_notes = (esc.reviewer_notes or "") + f"\n[{now.strftime('%Y-%m-%d %H:%M')}] {current_user.full_name}: {req.reviewer_notes}"

    # Audit human action
    audit = AuditEvent(
        hospital_id=esc.hospital_id,
        user_id=current_user.id,
        action=f"ESCALATION_{action_upper}",
        entity_type="ESCALATION",
        entity_id=esc.id,
        old_state={"status": old_status},
        new_state={"status": esc.status, "reviewer_id": esc.assigned_reviewer_id, "resolution": esc.resolution_action},
        reason=req.resolution_action or req.reviewer_notes
    )
    db.add(audit)
    db.commit()
    db.refresh(esc)

    return {
        "success": True,
        "escalation_id": esc.id,
        "status": esc.status,
        "assigned_reviewer_id": esc.assigned_reviewer_id,
        "resolved_at": esc.resolved_at.isoformat() if esc.resolved_at else None
    }

@router.post("/{escalation_id}/resolve")
def resolve_escalation_endpoint(
    escalation_id: str,
    req: ResolveEscalationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CLINICAL_REVIEWER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    action_req = EscalationActionRequest(
        action=req.status or "RESOLVE",
        reviewer_id=current_user.id,
        reviewer_notes=req.clinical_notes,
        resolution_action=req.action_taken or req.resolution_action or "Clinical reviewer evaluated triage consensus and completed intervention."
    )
    return update_escalation_action(escalation_id, action_req, db, current_user, tenant_ctx)
