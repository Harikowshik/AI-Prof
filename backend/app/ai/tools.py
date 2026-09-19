from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.app.core.tenants import TenantContext
from backend.app.models.healthcare import Patient, Encounter, Discharge, Observation
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask, CallRecord, EscalationRecord
from backend.app.models.operations import AuditEvent, NotificationRecord
from backend.app.rag.retriever import ProtocolRetriever

class ToolExecutionException(Exception):
    """Raised when controlled tool validation or execution fails."""
    pass

class ControlledAITools:
    """
    Controlled Tool Layer for AI Agents.
    Enforces authorization, tenant validation, business rule checking,
    audit logging, and returns machine-readable structured JSON.
    AI agents are STRICTLY prohibited from executing raw database operations.
    """

    def __init__(self, db: Session, tenant_ctx: TenantContext):
        self.db = db
        self.tenant_ctx = tenant_ctx

    def _audit_tool_invocation(self, tool_name: str, entity_type: str, entity_id: str, payload: Dict[str, Any]):
        audit = AuditEvent(
            hospital_id=self.tenant_ctx.hospital_id,
            user_id=self.tenant_ctx.user_id or "AI_AGENT_AUTOMATION",
            action=f"AI_TOOL_EXEC_{tool_name.upper()}",
            entity_type=entity_type,
            entity_id=entity_id,
            new_state=payload
        )
        self.db.add(audit)
        self.db.commit()

    def get_patient(self, patient_id: str) -> Dict[str, Any]:
        """Retrieves verified patient clinical summary within tenant boundary."""
        patient = self.db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            raise ToolExecutionException("Patient not found")
        self.tenant_ctx.validate_tenant_access(patient.hospital_id)

        self._audit_tool_invocation("get_patient", "PATIENT", patient.id, {"mrn": patient.mrn})
        return {
            "id": patient.id,
            "hospital_id": patient.hospital_id,
            "mrn": patient.mrn,
            "full_name": f"{patient.first_name} {patient.last_name}",
            "gender": patient.gender,
            "clinical_risk_tier": patient.clinical_risk_tier,
            "communication_preference": patient.communication_preference
        }

    def get_discharge(self, patient_id: str) -> Dict[str, Any]:
        """Retrieves patient latest discharge instructions and clinical deadlines."""
        discharge = self.db.query(Discharge).filter(
            Discharge.patient_id == patient_id,
            Discharge.hospital_id == self.tenant_ctx.hospital_id
        ).order_by(Discharge.discharge_time.desc()).first()

        if not discharge:
            raise ToolExecutionException("Discharge record not found for patient in this tenant")

        self._audit_tool_invocation("get_discharge", "DISCHARGE", discharge.id, {"primary_diagnosis": discharge.primary_diagnosis})
        return {
            "id": discharge.id,
            "discharge_time": discharge.discharge_time.isoformat(),
            "clinical_deadline": discharge.clinical_deadline.isoformat(),
            "primary_diagnosis": discharge.primary_diagnosis,
            "discharge_instructions": discharge.discharge_instructions,
            "red_flag_warnings": discharge.red_flag_warnings
        }

    def search_protocol(self, query: str, protocol_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Tenant-aware protocol knowledge retrieval."""
        results = ProtocolRetriever.search_protocol_chunks(
            db=self.db,
            hospital_id=self.tenant_ctx.hospital_id,
            query=query,
            protocol_type=protocol_type
        )
        self._audit_tool_invocation("search_protocol", "PROTOCOL_RETRIEVAL", self.tenant_ctx.hospital_id or "UNKNOWN", {"query": query, "count": len(results)})
        return results

    def create_escalation(
        self,
        task_id: str,
        trigger_reason: str,
        clinical_indicators: List[Dict[str, Any]],
        assessment_a: Dict[str, Any],
        assessment_b: Dict[str, Any],
        consensus_decision: str,
        disagreement_detected: bool,
        evidence_citations: List[str],
        priority: str = "HIGH"
    ) -> Dict[str, Any]:
        """Creates a verified clinical escalation ticket and triggers reviewer notification."""
        task = self.db.query(OutreachTask).filter(OutreachTask.id == task_id).first()
        if not task:
            raise ToolExecutionException("Outreach task not found")
        self.tenant_ctx.validate_tenant_access(task.hospital_id)

        # Prevent duplicate escalations for the same task
        existing = self.db.query(EscalationRecord).filter(
            EscalationRecord.outreach_task_id == task.id,
            EscalationRecord.status.in_(["OPEN", "ASSIGNED", "IN_REVIEW"])
        ).first()
        if existing:
            return {"escalation_id": existing.id, "status": existing.status, "message": "Escalation ticket already exists"}

        latest_call = self.db.query(CallRecord).filter(CallRecord.outreach_task_id == task.id).order_by(CallRecord.started_at.desc()).first()

        escalation = EscalationRecord(
            hospital_id=task.hospital_id,
            patient_id=task.patient_id,
            campaign_id=task.campaign_id,
            outreach_task_id=task.id,
            call_id=latest_call.id if latest_call else None,
            trigger_reason=trigger_reason,
            clinical_indicators=clinical_indicators,
            assessment_a=assessment_a,
            assessment_b=assessment_b,
            disagreement_detected=disagreement_detected,
            consensus_decision=consensus_decision,
            evidence_citations=evidence_citations,
            priority=priority,
            status="OPEN"
        )
        self.db.add(escalation)
        
        # Update outreach task status
        task.previous_status = task.status
        task.status = "ESCALATED"

        # Dispatch Internal Notification
        notif = NotificationRecord(
            hospital_id=task.hospital_id,
            recipient_role="CLINICAL_REVIEWER",
            notification_type="ESCALATION_CREATED",
            title=f"Clinical Escalation: {trigger_reason}",
            message=f"Patient requires immediate clinical attention: {trigger_reason}. Assessment Consensus: {consensus_decision}.",
            severity="CRITICAL" if priority == "URGENT" else "WARNING",
            status="PENDING"
        )
        self.db.add(notif)
        
        self.db.commit()
        self.db.refresh(escalation)

        self._audit_tool_invocation("create_escalation", "ESCALATION", escalation.id, {"priority": priority, "trigger": trigger_reason})
        return {
            "escalation_id": escalation.id,
            "status": escalation.status,
            "priority": escalation.priority,
            "message": "Clinical escalation ticket successfully created and notification dispatched."
        }
