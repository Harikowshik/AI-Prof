from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import Hospital, User
from backend.app.models.healthcare import Patient, Discharge
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask
from backend.app.models.operations import AuditEvent
from backend.app.campaigns.engine import (
    evaluate_patient_eligibility, estimate_campaign_workload
)

router = APIRouter(prefix="/campaigns", tags=["Campaign Management"])

class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_condition_or_dept: str = "ALL"
    clinical_window_hours: int = 48
    calling_hours_start: int = 8
    calling_hours_end: int = 20
    max_retries: int = 3
    campaign_priority_weight: float = 0.5
    eligibility_rules: Dict[str, Any] = {}

class CampaignResponse(BaseModel):
    id: str
    hospital_id: str
    name: str
    description: Optional[str]
    target_condition_or_dept: str
    clinical_window_hours: int
    calling_hours_start: int
    calling_hours_end: int
    max_retries: int
    campaign_priority_weight: float
    status: str
    created_at: datetime
    active_tasks_count: Optional[int] = 0
    completed_tasks_count: Optional[int] = 0

    class Config:
        from_attributes = True

@router.get("", response_model=List[CampaignResponse])
def list_campaigns(
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """List campaigns scoped to the caller's hospital."""
    query = db.query(Campaign)
    if not tenant_ctx.is_platform_admin:
        query = query.filter(Campaign.hospital_id == tenant_ctx.hospital_id)
    elif tenant_ctx.hospital_id:
        query = query.filter(Campaign.hospital_id == tenant_ctx.hospital_id)
        
    campaigns = query.all()
    res = []
    for c in campaigns:
        active_count = db.query(OutreachTask).filter(
            OutreachTask.campaign_id == c.id,
            OutreachTask.status.in_(["PENDING", "SCHEDULED", "CALLING", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"])
        ).count()
        completed_count = db.query(OutreachTask).filter(
            OutreachTask.campaign_id == c.id,
            OutreachTask.status == "COMPLETED"
        ).count()
        
        c_dict = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        c_dict["active_tasks_count"] = active_count
        c_dict["completed_tasks_count"] = completed_count
        res.append(CampaignResponse(**c_dict))
    return res

@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Get single campaign details with tenant access check."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)
    
    active_count = db.query(OutreachTask).filter(
        OutreachTask.campaign_id == campaign.id,
        OutreachTask.status.in_(["PENDING", "SCHEDULED", "CALLING", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"])
    ).count()
    completed_count = db.query(OutreachTask).filter(
        OutreachTask.campaign_id == campaign.id,
        OutreachTask.status == "COMPLETED"
    ).count()
    
    c_dict = {col.name: getattr(campaign, col.name) for col in campaign.__table__.columns}
    c_dict["active_tasks_count"] = active_count
    c_dict["completed_tasks_count"] = completed_count
    return CampaignResponse(**c_dict)

@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    req: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new post-discharge outreach campaign in DRAFT state."""
    target_hospital_id = tenant_ctx.hospital_id
    if not target_hospital_id:
        raise HTTPException(status_code=400, detail="Cannot create campaign without hospital_id")
        
    c = Campaign(
        hospital_id=target_hospital_id,
        status="DRAFT",
        **req.model_dump()
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    
    c_dict = {col.name: getattr(c, col.name) for col in c.__table__.columns}
    c_dict["active_tasks_count"] = 0
    c_dict["completed_tasks_count"] = 0
    return CampaignResponse(**c_dict)

@router.get("/{campaign_id}/workload")
def get_campaign_workload(
    campaign_id: str,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Pre-activation workload projection (eligible patients, expected attempts, capacity)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)
    
    return estimate_campaign_workload(db, campaign)

@router.post("/{campaign_id}/evaluate-eligibility")
def run_eligibility_and_populate_queue(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Evaluates patient eligibility for the campaign, populates outreach tasks into the queue,
    and returns detailed eligible and ineligible breakdowns with explainable reasons.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)
    
    patients = db.query(Patient).filter(Patient.hospital_id == campaign.hospital_id).all()
    results = []
    created_tasks_count = 0
    now = datetime.now(timezone.utc)

    for p in patients:
        eval_res = evaluate_patient_eligibility(db, p, campaign)
        results.append(eval_res.to_dict())
        
        if eval_res.eligible:
            # Check if pending task already exists
            existing_task = db.query(OutreachTask).filter(
                OutreachTask.patient_id == p.id,
                OutreachTask.campaign_id == campaign.id,
                OutreachTask.status.in_(["PENDING", "SCHEDULED", "CALLING", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"])
            ).first()
            
            if not existing_task:
                disc = db.query(Discharge).filter(Discharge.id == eval_res.discharge_id).first()
                deadline = disc.clinical_deadline if disc else now + timedelta(hours=campaign.clinical_window_hours)
                
                # Base risk score
                risk_val = 1.0 if p.clinical_risk_tier == "URGENT" else (0.8 if p.clinical_risk_tier == "HIGH" else (0.5 if p.clinical_risk_tier == "MEDIUM" else 0.25))
                
                task = OutreachTask(
                    hospital_id=campaign.hospital_id,
                    patient_id=p.id,
                    campaign_id=campaign.id,
                    status="PENDING",
                    risk_score=risk_val,
                    clinical_deadline=deadline,
                    max_retries=campaign.max_retries
                )
                db.add(task)
                created_tasks_count += 1
                
    db.commit()
    
    return {
        "campaign_id": campaign.id,
        "total_evaluated": len(patients),
        "eligible_count": sum(1 for r in results if r["eligible"]),
        "matched_count": sum(1 for r in results if r["eligible"]),
        "ineligible_count": sum(1 for r in results if not r["eligible"]),
        "new_tasks_created": created_tasks_count,
        "evaluations": results
    }

@router.post("/{campaign_id}/evaluate")
def evaluate_campaign_alias(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Alias for /evaluate-eligibility matching frontend api client."""
    return run_eligibility_and_populate_queue(campaign_id, db, current_user, tenant_ctx)

class CampaignStatusUpdate(BaseModel):
    status: str

@router.patch("/{campaign_id}/status")
@router.post("/{campaign_id}/status")
def update_campaign_status(
    campaign_id: str,
    req: CampaignStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Update campaign status (ACTIVE/RUNNING, PAUSED, DRAFT) with audit log."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)

    st_val = req.status.upper()
    target_status = "RUNNING" if st_val in ["ACTIVE", "RUNNING"] else ("PAUSED" if st_val in ["PAUSED", "PAUSE"] else st_val)
    old_status = campaign.status
    campaign.status = target_status
    if target_status == "RUNNING" and not campaign.start_date:
        campaign.start_date = datetime.now(timezone.utc)

    db.add(AuditEvent(
        hospital_id=campaign.hospital_id,
        user_id=current_user.id,
        action=f"CAMPAIGN_{target_status}",
        entity_type="CAMPAIGN",
        entity_id=campaign.id,
        old_state={"status": old_status},
        new_state={"status": target_status}
    ))
    db.commit()
    return {"status": target_status, "campaign_id": campaign.id, "message": f"Campaign status updated to {target_status}."}

@router.post("/{campaign_id}/start")
def start_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Starts the campaign and enables queue worker scheduling."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)
    
    campaign.status = "RUNNING"
    if not campaign.start_date:
        campaign.start_date = datetime.now(timezone.utc)
        
    db.add(AuditEvent(
        hospital_id=campaign.hospital_id,
        user_id=current_user.id,
        action="CAMPAIGN_STARTED",
        entity_type="CAMPAIGN",
        entity_id=campaign.id,
        new_state={"status": "RUNNING"}
    ))
    db.commit()
    return {"status": "RUNNING", "campaign_id": campaign.id, "message": "Campaign started successfully."}

@router.post("/{campaign_id}/pause")
def pause_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Pauses campaign:
    - Stops NEW outbound work from being reserved.
    - Allows currently active calls to conclude safely.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)
    
    campaign.status = "PAUSED"
    db.add(AuditEvent(
        hospital_id=campaign.hospital_id,
        user_id=current_user.id,
        action="CAMPAIGN_PAUSED",
        entity_type="CAMPAIGN",
        entity_id=campaign.id,
        new_state={"status": "PAUSED"}
    ))
    db.commit()
    return {"status": "PAUSED", "campaign_id": campaign.id, "message": "Campaign paused. Active calls will conclude safely."}

@router.post("/{campaign_id}/resume")
def resume_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Resumes campaign, transitioning status back to RUNNING."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tenant_ctx.validate_tenant_access(campaign.hospital_id)
    
    campaign.status = "RUNNING"
    db.add(AuditEvent(
        hospital_id=campaign.hospital_id,
        user_id=current_user.id,
        action="CAMPAIGN_RESUMED",
        entity_type="CAMPAIGN",
        entity_id=campaign.id,
        new_state={"status": "RUNNING"}
    ))
    db.commit()
    return {"status": "RUNNING", "campaign_id": campaign.id, "message": "Campaign resumed."}
