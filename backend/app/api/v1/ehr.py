from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import User
from backend.app.models.queue import DocumentationRecord, CallRecord
from backend.app.ehr.mock_service import MockEHRService

router = APIRouter(prefix="/ehr", tags=["Mock EHR Integration"])

# Global flag for simulating EHR outage/failures during demo
SIMULATE_EHR_FAILURE = False

class EHRRecordSyncRequest(BaseModel):
    call_id: str

@router.get("/status")
def get_ehr_status():
    """Returns Mock EHR gateway connectivity and simulated failure status."""
    return {
        "status": "ONLINE" if not SIMULATE_EHR_FAILURE else "DEGRADED_SIMULATED_FAILURES",
        "simulate_failures": SIMULATE_EHR_FAILURE,
        "supported_resources": ["Patient", "Communication", "Observation", "Task"]
    }

@router.post("/toggle-failure-mode")
def toggle_failure_mode(
    enabled: bool,
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN"]))
):
    """Toggles simulated EHR failure mode to demonstrate failure handling and retry recovery."""
    global SIMULATE_EHR_FAILURE
    SIMULATE_EHR_FAILURE = enabled
    return {"simulate_failures": SIMULATE_EHR_FAILURE, "message": f"EHR simulated failure mode set to {enabled}."}

@router.post("/sync-documentation")
def sync_call_documentation_to_ehr(
    req: EHRRecordSyncRequest,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Synchronizes call documentation into the EHR as structured Communication
    and Observation records. Demonstrates error handling and recovery if EHR is degraded.
    """
    call = db.query(CallRecord).filter(CallRecord.id == req.call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call record not found")
    tenant_ctx.validate_tenant_access(call.hospital_id)

    doc = db.query(DocumentationRecord).filter(DocumentationRecord.call_id == call.id).first()
    if not doc:
        # Create documentation record if not existing
        doc = DocumentationRecord(
            hospital_id=call.hospital_id,
            patient_id=call.patient_id,
            call_id=call.id,
            clinical_summary=f"Post-discharge outreach completed ({call.outcome}).",
            ehr_sync_status="PENDING"
        )
        db.add(doc)
        db.flush()

    ehr_service = MockEHRService(db, simulate_failures=SIMULATE_EHR_FAILURE)
    sync_result = ehr_service.record_communication(
        hospital_id=call.hospital_id,
        patient_id=call.patient_id,
        communication_type="POST_DISCHARGE_OUTREACH",
        summary=doc.clinical_summary,
        payload={"call_id": call.id, "outcome": call.outcome}
    )

    if not sync_result.get("success"):
        doc.ehr_sync_status = "FAILED"
        doc.ehr_sync_error = sync_result.get("message")
        db.commit()
        raise HTTPException(status_code=502, detail=f"EHR Synchronization failed: {sync_result.get('message')}")

    doc.ehr_sync_status = "SYNCED"
    doc.ehr_sync_timestamp = datetime.now(timezone.utc)
    doc.ehr_sync_error = None
    db.commit()

    return {
        "success": True,
        "ehr_sync_status": "SYNCED",
        "operation_id": sync_result.get("operation_id"),
        "synced_at": doc.ehr_sync_timestamp.isoformat()
    }
