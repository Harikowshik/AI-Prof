from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.healthcare import (
    Patient, Encounter, Discharge, Condition, Observation, Medication, CarePlan
)
from backend.app.models.queue import OutreachTask, CallRecord, EscalationRecord

router = APIRouter(prefix="/patients", tags=["Patients & Healthcare Records"])

class PatientListItem(BaseModel):
    id: str
    hospital_id: str
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    phone_number: str
    clinical_risk_tier: str
    communication_preference: str
    consent_granted: bool
    latest_discharge_date: Optional[str] = None
    primary_diagnosis: Optional[str] = None

class PatientDetailResponse(BaseModel):
    id: str
    hospital_id: str
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    phone_number: str
    email: Optional[str]
    clinical_risk_tier: str
    communication_preference: str
    consent_granted: bool
    
    encounters: List[Any] = []
    discharges: List[Any] = []
    conditions: List[Any] = []
    medications: List[Any] = []
    observations: List[Any] = []
    outreach_tasks: List[Any] = []
    calls: List[Any] = []
    timeline: List[Any] = []

@router.get("", response_model=List[PatientListItem])
def list_patients(
    risk_tier: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Returns list of patients strictly scoped to caller's hospital tenant.
    Cross-tenant queries are blocked server-side.
    """
    query = db.query(Patient)
    
    # Server-side tenant filter
    if not tenant_ctx.is_platform_admin:
        query = query.filter(Patient.hospital_id == tenant_ctx.hospital_id)
    elif tenant_ctx.hospital_id:
        query = query.filter(Patient.hospital_id == tenant_ctx.hospital_id)
        
    if risk_tier:
        query = query.filter(Patient.clinical_risk_tier == risk_tier.upper())
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((Patient.first_name.ilike(s)) | (Patient.last_name.ilike(s)) | (Patient.mrn.ilike(s)))
        
    patients = query.order_by(Patient.created_at.desc()).offset(offset).limit(limit).all()
    
    results = []
    for p in patients:
        latest_discharge = db.query(Discharge).filter(Discharge.patient_id == p.id).order_by(Discharge.discharge_time.desc()).first()
        results.append(PatientListItem(
            id=p.id,
            hospital_id=p.hospital_id,
            mrn=p.mrn,
            first_name=p.first_name,
            last_name=p.last_name,
            date_of_birth=p.date_of_birth,
            gender=p.gender,
            phone_number=p.phone_number,
            clinical_risk_tier=p.clinical_risk_tier,
            communication_preference=p.communication_preference,
            consent_granted=p.consent_granted,
            latest_discharge_date=latest_discharge.discharge_time.isoformat() if latest_discharge else None,
            primary_diagnosis=latest_discharge.primary_diagnosis if latest_discharge else None
        ))
    return results

@router.get("/{patient_id}", response_model=PatientDetailResponse)
def get_patient_detail(
    patient_id: str,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Returns complete Patient Operational View including clinical timeline.
    Enforces strict tenant isolation: if patient belongs to another hospital, returns 404.
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found")
        
    # Tenant verification
    tenant_ctx.validate_tenant_access(patient.hospital_id)
    
    encounters = db.query(Encounter).filter(Encounter.patient_id == patient.id).all()
    discharges = db.query(Discharge).filter(Discharge.patient_id == patient.id).all()
    conditions = db.query(Condition).filter(Condition.patient_id == patient.id).all()
    medications = db.query(Medication).filter(Medication.patient_id == patient.id).all()
    observations = db.query(Observation).filter(Observation.patient_id == patient.id).all()
    tasks = db.query(OutreachTask).filter(OutreachTask.patient_id == patient.id).all()
    calls = db.query(CallRecord).filter(CallRecord.patient_id == patient.id).order_by(CallRecord.started_at.desc()).all()
    escalations = db.query(EscalationRecord).filter(EscalationRecord.patient_id == patient.id).all()
    
    formatted_calls = []
    for c in calls:
        c_dict = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        c_dict["created_at"] = c.started_at.isoformat() if c.started_at else None
        c_dict["started_at"] = c.started_at.isoformat() if c.started_at else None
        c_dict["ended_at"] = c.ended_at.isoformat() if c.ended_at else None
        if isinstance(c.raw_transcript, list) and c.raw_transcript:
            c_dict["transcript"] = "\n".join([
                f"[{t.get('speaker', 'Unknown').upper()}]: {t.get('text', '')}"
                for t in c.raw_transcript if isinstance(t, dict)
            ])
        else:
            c_dict["transcript"] = str(c.raw_transcript or "")
        c_dict["summary"] = f"Attempt #{c.attempt_number} — Telephony status: {c.outcome}. Call duration: {c.duration_seconds}s."
        formatted_calls.append(c_dict)

    # Construct operational timeline
    timeline = []
    for enc in encounters:
        timeline.append({"time": enc.admit_time.isoformat(), "event": "ADMITTED", "details": f"Admitted to {enc.department}"})
    for disc in discharges:
        timeline.append({"time": disc.discharge_time.isoformat(), "event": "DISCHARGED", "details": f"Discharged with diagnosis: {disc.primary_diagnosis}"})
    for t in tasks:
        timeline.append({"time": t.created_at.isoformat(), "event": "QUEUE_TASK_CREATED", "details": f"Status: {t.status} (Priority: {round(t.computed_priority, 2)})"})
    for c in calls:
        timeline.append({"time": c.started_at.isoformat(), "event": "CALL_ATTEMPT", "details": f"Outcome: {c.outcome} ({c.duration_seconds}s)"})
    for esc in escalations:
        timeline.append({"time": esc.created_at.isoformat(), "event": "CLINICAL_ESCALATION", "details": f"Reason: {esc.trigger_reason} (Status: {esc.status})"})
        if esc.resolved_at:
            timeline.append({"time": esc.resolved_at.isoformat(), "event": "ESCALATION_RESOLVED", "details": f"Action: {esc.resolution_action}"})
            
    timeline.sort(key=lambda x: x["time"])
    
    return PatientDetailResponse(
        id=patient.id,
        hospital_id=patient.hospital_id,
        mrn=patient.mrn,
        first_name=patient.first_name,
        last_name=patient.last_name,
        date_of_birth=patient.date_of_birth,
        gender=patient.gender,
        phone_number=patient.phone_number,
        email=patient.email,
        clinical_risk_tier=patient.clinical_risk_tier,
        communication_preference=patient.communication_preference,
        consent_granted=patient.consent_granted,
        encounters=[{c.name: getattr(e, c.name) for c in e.__table__.columns} for e in encounters],
        discharges=[{c.name: getattr(d, c.name) for c in d.__table__.columns} for d in discharges],
        conditions=[{c.name: getattr(cd, c.name) for c in cd.__table__.columns} for cd in conditions],
        medications=[{c.name: getattr(m, c.name) for c in m.__table__.columns} for m in medications],
        observations=[{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in observations],
        outreach_tasks=[{c.name: getattr(t, c.name) for c in t.__table__.columns} for t in tasks],
        calls=formatted_calls,
        timeline=timeline
    )
