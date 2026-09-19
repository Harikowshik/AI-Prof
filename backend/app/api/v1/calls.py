from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import User
from backend.app.models.queue import OutreachTask, CallRecord
from backend.app.calls.simulator import TelephonySimulator
from backend.app.ai.intake import PREDEFINED_SCENARIOS
from backend.app.ai.assessments import DualAssessmentEngine
from backend.app.ai.consensus import ConsensusArbiter
from backend.app.ai.tools import ControlledAITools
from backend.app.rag.retriever import ProtocolRetriever

router = APIRouter(prefix="/calls", tags=["Calls & Telephony Simulation"])

class SimulateOutcomeRequest(BaseModel):
    task_id: str
    outcome: str # SUCCESSFUL, NO_ANSWER, BUSY, VOICEMAIL, DROPPED, CALLBACK_REQUESTED, TECHNICAL_FAILURE, or COMPLETED_*
    duration_seconds: Optional[int] = 45
    transcript: Optional[List[Dict[str, str]]] = None
    callback_time: Optional[datetime] = None
    answered_questions: Optional[List[str]] = None
    partial_observations: Optional[List[Dict[str, Any]]] = None
    scenario: Optional[str] = None
    custom_transcript: Optional[str] = None
    callback_minutes: Optional[int] = None

class CallRecordResponse(BaseModel):
    id: str
    hospital_id: str
    patient_id: str
    campaign_id: str
    outreach_task_id: str
    attempt_number: int
    outcome: str
    duration_seconds: int
    raw_transcript: List[Any]
    started_at: datetime
    ended_at: Optional[datetime]

    class Config:
        from_attributes = True

@router.get("", response_model=List[CallRecordResponse])
def list_calls(
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """List call history strictly scoped to caller's hospital."""
    query = db.query(CallRecord)
    if not tenant_ctx.is_platform_admin:
        query = query.filter(CallRecord.hospital_id == tenant_ctx.hospital_id)
    elif tenant_ctx.hospital_id:
        query = query.filter(CallRecord.hospital_id == tenant_ctx.hospital_id)
        
    return query.order_by(CallRecord.started_at.desc()).limit(100).all()

@router.get("/{call_id}", response_model=CallRecordResponse)
def get_call(
    call_id: str,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Get single call details."""
    call = db.query(CallRecord).filter(CallRecord.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call record not found")
    tenant_ctx.validate_tenant_access(call.hospital_id)
    return call

@router.post("/simulate")
@router.post("/simulate-outcome")
def simulate_call_outcome(
    req: SimulateOutcomeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER", "CLINICAL_REVIEWER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Simulates telephony outcome for an active task.
    Evaluators can trigger: SUCCESSFUL, NO_ANSWER, BUSY, VOICEMAIL, DROPPED, CALLBACK_REQUESTED, TECHNICAL_FAILURE,
    or scenario-based presets: COMPLETED_ROUTINE, COMPLETED_URGENT_CHEST_PAIN, COMPLETED_WOUND_INFECTION, COMPLETED_AMBIGUOUS.
    """
    task = db.query(OutreachTask).filter(OutreachTask.id == req.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    tenant_ctx.validate_tenant_access(task.hospital_id)

    # Ensure task is in CALLING state (or move to CALLING if simulating directly)
    if task.status != "CALLING":
        task.status = "CALLING"
        db.commit()

    outcome_raw = req.outcome.upper()
    transcript = req.transcript

    if req.custom_transcript and req.custom_transcript.strip():
        transcript = [
            {"speaker": "agent", "text": "Hello, this is the hospital post-discharge outreach team. How are you feeling today?"},
            {"speaker": "patient", "text": req.custom_transcript.strip()}
        ]

    # Map scenario presets
    if outcome_raw in ["COMPLETED_ROUTINE", "ROUTINE"]:
        outcome = "SUCCESSFUL"
        if not transcript:
            transcript = PREDEFINED_SCENARIOS.get("ROUTINE", {}).get("transcript")
    elif outcome_raw in ["COMPLETED_URGENT_CHEST_PAIN", "URGENT", "CHEST_PAIN"]:
        outcome = "SUCCESSFUL"
        if not transcript:
            transcript = PREDEFINED_SCENARIOS.get("URGENT", {}).get("transcript")
    elif outcome_raw in ["COMPLETED_WOUND_INFECTION", "CONCERNING", "WOUND_INFECTION"]:
        outcome = "SUCCESSFUL"
        if not transcript:
            transcript = PREDEFINED_SCENARIOS.get("CONCERNING", {}).get("transcript")
    elif outcome_raw in ["COMPLETED_AMBIGUOUS", "AMBIGUOUS"]:
        outcome = "SUCCESSFUL"
        if not transcript:
            transcript = PREDEFINED_SCENARIOS.get("AMBIGUOUS", {}).get("transcript")
    elif outcome_raw in ["DROPPED_CALL", "DROPPED"]:
        outcome = "DROPPED"
        if not transcript:
            transcript = PREDEFINED_SCENARIOS.get("INCOMPLETE", {}).get("transcript")
    else:
        outcome = outcome_raw

    callback_time = req.callback_time
    if req.callback_minutes and not callback_time:
        callback_time = datetime.now(timezone.utc) + timedelta(minutes=req.callback_minutes)

    try:
        call, updated_task = TelephonySimulator.simulate_call_outcome(
            db=db,
            task_id=req.task_id,
            outcome=outcome,
            duration_seconds=req.duration_seconds or 45,
            transcript=transcript,
            callback_time=callback_time,
            answered_questions=req.answered_questions,
            partial_observations=req.partial_observations
        )

        escalation_created = False
        escalation_severity = None
        escalation_reason = None

        # If call was completed with patient dialogue, evaluate clinical triage & consensus
        if outcome == "SUCCESSFUL" and transcript:
            try:
                patient = updated_task.patient
                condition = (patient.primary_discharge_condition if patient else "") or "POST_DISCHARGE"
                protocols = ProtocolRetriever.search_protocol_chunks(db, updated_task.hospital_id, condition)
                
                res_a = DualAssessmentEngine.run_assessment_a(transcript, protocols)
                res_b = DualAssessmentEngine.run_assessment_b(transcript)
                consensus = ConsensusArbiter.arbitrate(res_a, res_b)

                if consensus.escalation_required:
                    tools = ControlledAITools(db=db, tenant_ctx=tenant_ctx)
                    tools.create_escalation(
                        task_id=updated_task.id,
                        trigger_reason=consensus.consensus_decision_basis,
                        clinical_indicators=consensus.combined_indicators,
                        assessment_a=res_a.model_dump(),
                        assessment_b=res_b.model_dump(),
                        consensus_decision=f"{consensus.final_classification.value} (Consensus)",
                        disagreement_detected=consensus.disagreement_detected,
                        evidence_citations=consensus.combined_evidence,
                        priority="URGENT" if consensus.final_classification.value == "URGENT" else "HIGH"
                    )
                    escalation_created = True
                    escalation_severity = consensus.final_classification.value
                    escalation_reason = consensus.consensus_decision_basis
            except Exception as triage_err:
                print(f"[Simulate Call Triage Error]: {triage_err}")

        return {
            "success": True,
            "call_id": call.id,
            "task_id": updated_task.id,
            "outcome": call.outcome,
            "task_status": updated_task.status,
            "new_task_status": updated_task.status,
            "escalation_created": escalation_created,
            "escalation_severity": escalation_severity,
            "escalation_reason": escalation_reason,
            "retry_scheduled_at": updated_task.scheduled_for.isoformat() if (updated_task.scheduled_for and outcome != "CALLBACK_REQUESTED") else None,
            "callback_scheduled_at": updated_task.scheduled_for.isoformat() if (updated_task.scheduled_for and outcome == "CALLBACK_REQUESTED") else None,
            "scheduled_for": updated_task.scheduled_for.isoformat() if updated_task.scheduled_for else None,
            "attempt_count": updated_task.attempt_count
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
