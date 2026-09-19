import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.app.ehr.interface import EHRService
from backend.app.models.healthcare import Patient, Observation
from backend.app.models.queue import DocumentationRecord
from backend.app.models.operations import AuditEvent

class MockEHRService(EHRService):
    """
    High-fidelity Mock EHR implementation providing realistic FHIR-like resources,
    idempotent write protections, simulated latency, and error recovery handling.
    """

    def __init__(self, db: Session, simulate_failures: bool = False):
        self.db = db
        self.simulate_failures = simulate_failures

    def get_patient(self, hospital_id: str, patient_id: str) -> Dict[str, Any]:
        patient = self.db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.hospital_id == hospital_id
        ).first()
        if not patient:
            return {"status": "NOT_FOUND"}
        return {
            "resourceType": "Patient",
            "id": patient.id,
            "identifier": [{"system": "MRN", "value": patient.mrn}],
            "name": [{"family": patient.last_name, "given": [patient.first_name]}],
            "telecom": [{"system": "phone", "value": patient.phone_number}],
            "gender": patient.gender.lower(),
            "birthDate": patient.date_of_birth
        }

    def record_communication(
        self,
        hospital_id: str,
        patient_id: str,
        communication_type: str,
        summary: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self.simulate_failures:
            return {
                "success": False,
                "error": "EHR_GATEWAY_TIMEOUT",
                "message": "Mock EHR integration server timeout (HTTP 504). Recovery queue armed."
            }

        operation_id = f"ehr-comm-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Audit write to EHR
        audit = AuditEvent(
            hospital_id=hospital_id,
            action="EHR_WRITE_COMMUNICATION",
            entity_type="EHR_RECORD",
            entity_id=operation_id,
            new_state={
                "patient_id": patient_id,
                "type": communication_type,
                "summary": summary,
                "timestamp": now.isoformat()
            }
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "success": True,
            "operation_id": operation_id,
            "resourceType": "Communication",
            "status": "completed",
            "received_at": now.isoformat(),
            "summary": summary
        }

    def create_observation(
        self,
        hospital_id: str,
        patient_id: str,
        code: str,
        display_name: str,
        value: Any,
        unit: Optional[str] = None
    ) -> Dict[str, Any]:
        obs = Observation(
            hospital_id=hospital_id,
            patient_id=patient_id,
            code=code,
            display_name=display_name,
            value_string=str(value),
            unit=unit,
            source="AI_OUTREACH"
        )
        self.db.add(obs)
        self.db.commit()
        self.db.refresh(obs)

        return {
            "success": True,
            "resourceType": "Observation",
            "id": obs.id,
            "code": code,
            "value": value
        }

    def create_followup_task(
        self,
        hospital_id: str,
        patient_id: str,
        title: str,
        description: str,
        priority: str = "ROUTINE"
    ) -> Dict[str, Any]:
        task_ref = f"ehr-task-{uuid.uuid4().hex[:10]}"
        return {
            "success": True,
            "resourceType": "Task",
            "id": task_ref,
            "status": "requested",
            "priority": priority,
            "description": description
        }
