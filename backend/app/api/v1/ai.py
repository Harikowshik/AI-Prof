import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import User
from backend.app.models.queue import OutreachTask, CallRecord, DocumentationRecord
from backend.app.models.operations import AIUsageRecord
from backend.app.ai.intake import VoiceIntakeSimulator, PREDEFINED_SCENARIOS
from backend.app.rag.retriever import ProtocolRetriever
from backend.app.ai.assessments import DualAssessmentEngine
from backend.app.ai.consensus import ConsensusArbiter
from backend.app.ai.documentation import ClinicalDocumentationAgent
from backend.app.ai.tools import ControlledAITools
from backend.app.ehr.mock_service import MockEHRService

router = APIRouter(prefix="/ai", tags=["AI Clinical Pipeline"])

class RunInteractionRequest(BaseModel):
    task_id: str
    scenario_key: Optional[str] = "CONCERNING" # ROUTINE, CONCERNING, URGENT, AMBIGUOUS, INCOMPLETE, CONFLICTING, PROMPT_INJECTION
    custom_transcript: Optional[List[Dict[str, str]]] = None

@router.get("/scenarios")
def get_scenarios():
    """Returns available predefined clinical demo scenarios."""
    return VoiceIntakeSimulator.get_scenario_list()

@router.post("/run-interaction")
def run_clinical_ai_interaction(
    req: RunInteractionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER", "CLINICAL_REVIEWER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Executes complete Autonomous AI Outreach Pipeline:
    1. Protocol RAG retrieval (Strictly tenant isolated)
    2. Voice conversation intake / scenario execution
    3. Dual independent assessments (Assessment A + Assessment B)
    4. Conservative consensus arbitration
    5. Controlled tool execution (escalation creation if flagged)
    6. Structured clinical note generation
    7. Mock EHR update
    8. Observability & AI telemetry logging.
    """
    start_time = time.time()
    
    task = db.query(OutreachTask).filter(OutreachTask.id == req.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    tenant_ctx.validate_tenant_access(task.hospital_id)

    # 1. Determine transcript
    if req.custom_transcript:
        transcript = req.custom_transcript
        scenario_title = "Custom Clinical Interaction"
    else:
        scen = VoiceIntakeSimulator.get_scenario(req.scenario_key)
        if not scen:
            scen = PREDEFINED_SCENARIOS["CONCERNING"]
        transcript = scen["transcript"]
        scenario_title = scen["title"]

    # 2. Protocol RAG Retrieval
    protocols = ProtocolRetriever.search_protocol_chunks(
        db=db,
        hospital_id=task.hospital_id,
        query=scenario_title,
        top_k=2
    )

    # 3. Dual Independent Assessments
    assessment_a = DualAssessmentEngine.run_assessment_a(transcript, protocols)
    assessment_b = DualAssessmentEngine.run_assessment_b(transcript)

    # 4. Conservative Consensus Arbiter
    consensus = ConsensusArbiter.arbitrate(assessment_a, assessment_b)

    # 5. Record Call Attempt
    call = CallRecord(
        hospital_id=task.hospital_id,
        patient_id=task.patient_id,
        campaign_id=task.campaign_id,
        outreach_task_id=task.id,
        attempt_number=task.attempt_count + 1,
        outcome="SUCCESSFUL" if not consensus.escalation_required else "ESCALATION",
        duration_seconds=55,
        raw_transcript=transcript,
        scenario_id=req.scenario_key
    )
    db.add(call)
    db.flush()

    # 6. Controlled Tools: Escalation creation if required
    tools = ControlledAITools(db, tenant_ctx)
    escalation_info = None
    if consensus.escalation_required:
        escalation_info = tools.create_escalation(
            task_id=task.id,
            trigger_reason=consensus.consensus_decision_basis,
            clinical_indicators=consensus.combined_indicators,
            assessment_a=assessment_a.model_dump(),
            assessment_b=assessment_b.model_dump(),
            consensus_decision=consensus.final_classification.value,
            disagreement_detected=consensus.disagreement_detected,
            evidence_citations=consensus.combined_evidence,
            priority="URGENT" if consensus.final_classification == "URGENT" else "HIGH"
        )
    else:
        task.status = "COMPLETED"
        db.commit()

    # 7. Documentation Agent: Generate clinical note
    doc_note = ClinicalDocumentationAgent.generate_note(call, consensus, transcript)
    doc_record = DocumentationRecord(
        hospital_id=task.hospital_id,
        patient_id=task.patient_id,
        call_id=call.id,
        clinical_summary=doc_note.clinical_summary,
        patient_reported_symptoms=doc_note.patient_reported_symptoms,
        follow_up_recommendations=doc_note.follow_up_recommendations,
        citations=doc_note.citations,
        ehr_sync_status="SYNCED",
        ehr_sync_timestamp=datetime.now(timezone.utc)
    )
    db.add(doc_record)

    # 8. Mock EHR Update
    ehr = MockEHRService(db)
    ehr.record_communication(
        hospital_id=task.hospital_id,
        patient_id=task.patient_id,
        communication_type="AI_CLINICAL_OUTREACH",
        summary=doc_note.clinical_summary,
        payload={"call_id": call.id, "triage": consensus.final_classification.value}
    )

    # 9. AI Usage Observability Telemetry
    elapsed_ms = (time.time() - start_time) * 1000.0
    ai_log = AIUsageRecord(
        hospital_id=task.hospital_id,
        agent_name="MultiAgentClinicalPipeline",
        model_name="HospitalClinicalEngine-v2",
        request_purpose=f"Triage Evaluation ({scenario_title})",
        latency_ms=round(elapsed_ms, 2),
        tokens_used=485,
        cost_estimate=0.0012,
        success=True
    )
    db.add(ai_log)
    db.commit()

    return {
        "success": True,
        "call_id": call.id,
        "task_id": task.id,
        "scenario": scenario_title,
        "retrieved_protocols": protocols,
        "assessment_a": assessment_a.model_dump(),
        "assessment_b": assessment_b.model_dump(),
        "disagreement_detected": consensus.disagreement_detected,
        "consensus": consensus.model_dump(),
        "escalation": escalation_info,
        "documentation": doc_note.model_dump(),
        "latency_ms": round(elapsed_ms, 2)
    }
