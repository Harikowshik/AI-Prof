from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session

from backend.app.models.tenant import Hospital, HospitalCapacity
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask, CallRecord
from backend.app.models.operations import AuditEvent
from backend.app.queue.concurrency import ConcurrencyManager
from backend.app.queue.retries import calculate_next_retry
from backend.app.queue.callbacks import schedule_patient_callback

# Legal state machine transitions map
VALID_TRANSITIONS = {
    "PENDING": ["SCHEDULED", "CALLING", "FAILED"],
    "SCHEDULED": ["CALLING", "PENDING", "FAILED"],
    "CALLING": ["CONNECTED", "NO_ANSWER", "BUSY", "VOICEMAIL", "DROPPED", "FAILED", "COMPLETED"],
    "CONNECTED": ["COMPLETED", "CALLBACK_SCHEDULED", "ESCALATED", "DROPPED"],
    "NO_ANSWER": ["RETRY_SCHEDULED", "MANUAL_FOLLOW_UP"],
    "BUSY": ["RETRY_SCHEDULED", "MANUAL_FOLLOW_UP"],
    "VOICEMAIL": ["RETRY_SCHEDULED", "MANUAL_FOLLOW_UP"],
    "DROPPED": ["RETRY_SCHEDULED", "MANUAL_FOLLOW_UP"],
    "RETRY_SCHEDULED": ["SCHEDULED", "CALLING", "MANUAL_FOLLOW_UP"],
    "CALLBACK_SCHEDULED": ["SCHEDULED", "CALLING", "MANUAL_FOLLOW_UP"],
    "ESCALATED": ["MANUAL_FOLLOW_UP", "COMPLETED"],
    "MANUAL_FOLLOW_UP": ["COMPLETED", "FAILED"],
    "COMPLETED": [],
    "FAILED": ["MANUAL_FOLLOW_UP"]
}

def validate_state_transition(current_state: str, new_state: str) -> bool:
    """Validates whether a state transition is legal under the outreach state machine."""
    allowed = VALID_TRANSITIONS.get(current_state, [])
    return new_state in allowed

class TelephonySimulator:
    """
    High-fidelity deterministic call simulator implementing the full outreach lifecycle,
    telephony outcomes, retry scheduling, callback capture, and partial context persistence.
    """

    @staticmethod
    def simulate_call_outcome(
        db: Session,
        task_id: str,
        outcome: str,
        duration_seconds: int = 45,
        transcript: Optional[List[Dict[str, str]]] = None,
        callback_time: Optional[datetime] = None,
        answered_questions: Optional[List[str]] = None,
        partial_observations: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[CallRecord, OutreachTask]:
        """
        Processes a deterministic call outcome, creates a CallRecord,
        updates the OutreachTask state, handles retries or callbacks,
        and safely releases hospital capacity.
        """
        task = db.query(OutreachTask).filter(OutreachTask.id == task_id).first()
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        hospital = task.patient.hospital
        campaign = task.campaign
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=duration_seconds)

        # 1. Create CallRecord
        call = CallRecord(
            hospital_id=task.hospital_id,
            patient_id=task.patient_id,
            campaign_id=task.campaign_id,
            outreach_task_id=task.id,
            attempt_number=task.attempt_count,
            outcome=outcome,
            duration_seconds=duration_seconds,
            raw_transcript=transcript or [],
            started_at=start_time,
            ended_at=now
        )
        db.add(call)
        db.flush()

        # 2. Process Outcome & Determine Destination State
        if outcome == "SUCCESSFUL":
            dest_status = "COMPLETED"
            task.conversation_stage = "COMPLETED"
            task.partial_transcript = transcript or []
            task.scheduled_for = None
            ConcurrencyManager.release_capacity(db, task.hospital_id, task.id, dest_status)

        elif outcome in ["NO_ANSWER", "BUSY", "VOICEMAIL", "TECHNICAL_FAILURE"]:
            next_status, next_sched, reason = calculate_next_retry(
                task=task,
                outcome=outcome,
                hospital=hospital,
                campaign=campaign,
                now=now
            )
            task.scheduled_for = next_sched
            dest_status = next_status
            ConcurrencyManager.release_capacity(db, task.hospital_id, task.id, dest_status, reason=reason)

        elif outcome == "DROPPED":
            # Section 24: Persist partial interaction context
            task.conversation_stage = "DROPPED_MID_CALL"
            task.partial_transcript = transcript or []
            task.answered_questions = answered_questions or []
            task.partial_observations = partial_observations or []
            
            next_status, next_sched, reason = calculate_next_retry(
                task=task,
                outcome="DROPPED",
                hospital=hospital,
                campaign=campaign,
                now=now
            )
            task.scheduled_for = next_sched
            dest_status = next_status
            ConcurrencyManager.release_capacity(db, task.hospital_id, task.id, dest_status, reason=reason)

        elif outcome == "CALLBACK_REQUESTED":
            # Section 23: Explicit callback scheduling
            target_cb_time = callback_time or (now + timedelta(hours=2))
            scheduled_time, cb_note = schedule_patient_callback(
                task=task,
                hospital=hospital,
                requested_time=target_cb_time,
                reason="Patient explicitly requested callback"
            )
            dest_status = "CALLBACK_SCHEDULED"
            ConcurrencyManager.release_capacity(db, task.hospital_id, task.id, dest_status, reason=cb_note)

        else:
            dest_status = "FAILED"
            ConcurrencyManager.release_capacity(db, task.hospital_id, task.id, dest_status)

        # Audit Log
        audit = AuditEvent(
            hospital_id=task.hospital_id,
            action=f"CALL_OUTCOME_{outcome}",
            entity_type="CALL",
            entity_id=call.id,
            old_state={"task_status": "CALLING"},
            new_state={"task_status": dest_status, "outcome": outcome}
        )
        db.add(audit)
        db.commit()
        db.refresh(task)
        db.refresh(call)

        return call, task
