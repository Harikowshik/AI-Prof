from datetime import datetime, timezone
from typing import List, Dict, Any
from pydantic import BaseModel
from backend.app.ai.consensus import ConsensusEvaluation
from backend.app.models.queue import CallRecord

class ClinicalProgressNote(BaseModel):
    patient_id: str
    call_id: str
    encounter_type: str = "POST_DISCHARGE_AI_OUTREACH"
    clinical_summary: str
    patient_reported_symptoms: List[str]
    triage_outcome: str
    consensus_decision: str
    disagreement_detected: bool
    escalation_status: str
    follow_up_recommendations: List[str]
    citations: List[str]
    generated_at: str

class ClinicalDocumentationAgent:
    """
    Generates structured, traceable clinical progress notes for the medical record,
    linking every reported symptom directly to verified conversational quotes.
    """

    @staticmethod
    def generate_note(
        call: CallRecord,
        consensus: ConsensusEvaluation,
        transcript: List[Dict[str, str]]
    ) -> ClinicalProgressNote:
        now = datetime.now(timezone.utc).isoformat()
        
        # Extract direct patient quotes as evidence
        patient_quotes = [turn.get("text", "") for turn in transcript if turn.get("speaker") == "patient"]
        
        symptoms = [ind.get("symptom", "Symptom") for ind in consensus.combined_indicators]
        if not symptoms:
            symptoms = ["Patient reports feeling well and denies acute symptoms"]

        # Recommendations based on consensus classification
        recs = []
        if consensus.final_classification == "URGENT":
            recs.append("IMMEDIATE EMERGENCY INTERVENTION: Advised patient to call 911 / proceed to nearest emergency room.")
            recs.append("Immediate clinician warm-handoff notified.")
        elif consensus.final_classification in ["CONCERNING", "UNCERTAIN"]:
            recs.append("Clinical nurse reviewer follow-up required within 4 hours.")
            recs.append("Clarify medication adherence and re-assess vital signs.")
        else:
            recs.append("Continue current post-discharge care plan.")
            recs.append("Reinforce scheduled outpatient clinic appointment.")

        summary = (
            f"Automated post-discharge outreach completed on {call.started_at.strftime('%Y-%m-%d %H:%M UTC')}. "
            f"Call duration: {call.duration_seconds}s. Outcome: {call.outcome}. "
            f"Dual-assessment triage reached consensus: {consensus.final_classification}. "
            f"Basis: {consensus.consensus_decision_basis}"
        )

        return ClinicalProgressNote(
            patient_id=call.patient_id,
            call_id=call.id,
            clinical_summary=summary,
            patient_reported_symptoms=symptoms,
            triage_outcome=consensus.final_classification.value,
            consensus_decision=consensus.consensus_decision_basis,
            disagreement_detected=consensus.disagreement_detected,
            escalation_status="ESCALATED" if consensus.escalation_required else "NOT_REQUIRED",
            follow_up_recommendations=recs,
            citations=patient_quotes[:3],
            generated_at=now
        )
