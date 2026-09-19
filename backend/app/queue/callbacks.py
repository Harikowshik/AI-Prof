from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from backend.app.models.tenant import Hospital
from backend.app.models.queue import OutreachTask

def schedule_patient_callback(
    task: OutreachTask,
    hospital: Hospital,
    requested_time: datetime,
    reason: Optional[str] = "Patient requested follow-up at specific time"
) -> Tuple[datetime, str]:
    """
    Schedules an explicit callback, adjusting to valid hospital calling windows if needed.
    """
    if requested_time.tzinfo is None:
        requested_time = requested_time.replace(tzinfo=timezone.utc)

    calling_start = hospital.calling_hours_start if hospital else 8
    calling_end = hospital.calling_hours_end if hospital else 20
    adjusted_time = requested_time

    # Validate against hospital calling hours
    if requested_time.hour >= calling_end:
        # Move to next morning at start of calling hours
        adjusted_time = requested_time.replace(hour=calling_start, minute=30, second=0) + timedelta(days=1)
        note = f"Requested time was after calling hours ({calling_end}:00). Adjusted to next morning at {adjusted_time.isoformat()}."
    elif requested_time.hour < calling_start:
        adjusted_time = requested_time.replace(hour=calling_start, minute=30, second=0)
        note = f"Requested time was before calling hours ({calling_start}:00). Adjusted to morning at {adjusted_time.isoformat()}."
    else:
        note = f"Callback confirmed for requested time {adjusted_time.isoformat()}."

    task.previous_status = task.status
    task.status = "CALLBACK_SCHEDULED"
    task.callback_scheduled_at = adjusted_time
    task.callback_reason = reason
    task.scheduled_for = adjusted_time
    task.updated_at = datetime.now(timezone.utc)

    return adjusted_time, note
