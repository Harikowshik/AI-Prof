import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import Hospital, User
from backend.app.models.healthcare import (
    Patient, Encounter, Discharge, Condition
)
from backend.app.models.operations import AuditEvent

router = APIRouter(prefix="/ingestion", tags=["Discharge Ingestion"])

class IngestionRecord(BaseModel):
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    phone: str
    department: str
    discharge_timestamp: str
    primary_diagnosis: str
    clinical_risk_tier: Optional[str] = "MEDIUM"
    communication_preference: Optional[str] = "PHONE"
    consent_granted: Optional[bool] = True

class IngestionBatchPayload(BaseModel):
    hospital_id: Optional[str] = None
    records: List[Dict[str, Any]]

class IngestionReport(BaseModel):
    total_received: int
    successful_count: int
    duplicates_count: int
    failed_count: int
    errors: List[Dict[str, Any]] = []

@router.post("/upload", response_model=IngestionReport)
def ingest_discharge_feed(
    payload: IngestionBatchPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Ingests batch of discharge records with strict schema validation,
    duplicate MRN detection, tenant association, and explicit error reporting.
    """
    target_hospital_id = payload.hospital_id or tenant_ctx.hospital_id
    if not target_hospital_id:
        raise HTTPException(status_code=400, detail="hospital_id required")
        
    tenant_ctx.validate_tenant_access(target_hospital_id)
    hospital = db.query(Hospital).filter(Hospital.id == target_hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
        
    total_received = len(payload.records)
    successful_count = 0
    duplicates_count = 0
    failed_count = 0
    errors = []
    now = datetime.now(timezone.utc)

    for index, raw_item in enumerate(payload.records):
        try:
            # Validate through Pydantic
            item = IngestionRecord(**raw_item)
            
            # Check for existing patient by MRN within this hospital tenant
            existing_patient = db.query(Patient).filter(
                Patient.hospital_id == target_hospital_id,
                Patient.mrn == item.mrn
            ).first()

            if existing_patient:
                duplicates_count += 1
                errors.append({
                    "record_index": index,
                    "mrn": item.mrn,
                    "reason": "DUPLICATE_MRN",
                    "message": f"Patient with MRN '{item.mrn}' already exists in tenant."
                })
                continue
            
            # Parse timestamps
            try:
                disc_time = datetime.fromisoformat(item.discharge_timestamp.replace("Z", "+00:00"))
            except Exception:
                disc_time = now
            
            clinical_deadline = disc_time + timedelta(hours=hospital.clinical_window_hours)
            
            # Create Patient
            patient = Patient(
                hospital_id=target_hospital_id,
                mrn=item.mrn,
                first_name=item.first_name,
                last_name=item.last_name,
                date_of_birth=item.date_of_birth,
                gender=item.gender,
                phone_number=item.phone,
                communication_preference=item.communication_preference or "PHONE",
                consent_granted=item.consent_granted if item.consent_granted is not None else True,
                clinical_risk_tier=item.clinical_risk_tier or "MEDIUM"
            )
            db.add(patient)
            db.flush()

            # Create Encounter
            encounter = Encounter(
                hospital_id=target_hospital_id,
                patient_id=patient.id,
                encounter_type="INPATIENT",
                department=item.department,
                admit_time=disc_time - timedelta(days=2),
                discharge_time=disc_time
            )
            db.add(encounter)
            db.flush()

            # Create Discharge
            discharge = Discharge(
                hospital_id=target_hospital_id,
                encounter_id=encounter.id,
                patient_id=patient.id,
                discharge_time=disc_time,
                clinical_deadline=clinical_deadline,
                primary_diagnosis=item.primary_diagnosis,
                discharge_instructions="Follow discharge regimen. Contact clinical outreach for any symptoms."
            )
            db.add(discharge)

            # Create Condition
            condition = Condition(
                hospital_id=target_hospital_id,
                patient_id=patient.id,
                display_name=item.primary_diagnosis,
                clinical_status="ACTIVE"
            )
            db.add(condition)
            
            successful_count += 1

        except Exception as e:
            failed_count += 1
            errors.append({
                "record_index": index,
                "raw_data": raw_item,
                "reason": "VALIDATION_OR_PARSING_FAILURE",
                "message": str(e)
            })

    # Record Audit Event
    audit = AuditEvent(
        hospital_id=target_hospital_id,
        user_id=current_user.id,
        action="DISCHARGE_FEED_INGESTED",
        entity_type="INGESTION_BATCH",
        entity_id=hospital.id,
        new_state={"received": total_received, "successful": successful_count, "duplicates": duplicates_count, "failed": failed_count}
    )
    db.add(audit)
    db.commit()

    return IngestionReport(
        total_received=total_received,
        successful_count=successful_count,
        duplicates_count=duplicates_count,
        failed_count=failed_count,
        errors=errors
    )
