from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.tenant import HospitalCapacity
from backend.app.models.queue import OutreachTask
from backend.app.models.operations import AuditEvent

DEFAULT_LEASE_TIMEOUT_SECONDS = 60

def reap_stale_tasks(
    db: Session, 
    lease_timeout_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS
) -> List[Dict[str, Any]]:
    """
    Detects crashed workers holding capacity, releases the capacity counter,
    and transitions stuck tasks back to RETRY_SCHEDULED or MANUAL_FOLLOW_UP.
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=lease_timeout_seconds)
    
    # Query tasks that are in CALLING state but have expired heartbeat leases
    stale_tasks = db.query(OutreachTask).filter(
        OutreachTask.status == "CALLING",
        (OutreachTask.heartbeat_at == None) | (OutreachTask.heartbeat_at < threshold)
    ).all()

    recovered_info = []

    for task in stale_tasks:
        hospital_id = task.hospital_id
        
        # Release capacity
        cap = db.query(HospitalCapacity).filter(
            HospitalCapacity.hospital_id == hospital_id
        ).with_for_update().first()

        if cap and cap.current_active_calls > 0:
            cap.current_active_calls -= 1
            cap.updated_at = now

        # Determine recovery destination state
        old_status = task.status
        old_worker = task.worker_id
        if task.attempt_count < task.max_retries:
            task.status = "RETRY_SCHEDULED"
            task.scheduled_for = now + timedelta(minutes=5)
            action_taken = "RETRY_SCHEDULED (Worker Lease Expired)"
        else:
            task.status = "MANUAL_FOLLOW_UP"
            task.scheduled_for = None
            action_taken = "MANUAL_FOLLOW_UP (Max Retries Exhausted During Crash)"

        task.worker_id = None
        task.heartbeat_at = None
        task.updated_at = now

        audit = AuditEvent(
            hospital_id=hospital_id,
            action="STALE_TASK_RECOVERED",
            entity_type="OUTREACH_TASK",
            entity_id=task.id,
            old_state={"status": old_status, "worker_id": old_worker},
            new_state={"status": task.status, "capacity_released": True},
            reason="Worker heartbeat timeout exceeded lease duration"
        )
        db.add(audit)

        recovered_info.append({
            "task_id": task.id,
            "hospital_id": hospital_id,
            "old_worker_id": old_worker,
            "new_status": task.status,
            "action": action_taken
        })

    db.commit()
    return recovered_info
