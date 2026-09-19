from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from backend.app.models.tenant import Hospital
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask

# Base backoff in minutes
BACKOFF_CONFIG = {
    "NO_ANSWER": {"base_minutes": 15, "factor": 2.0},
    "BUSY": {"base_minutes": 10, "factor": 1.5},
    "VOICEMAIL": {"base_minutes": 30, "factor": 1.0},
    "DROPPED": {"base_minutes": 5, "factor": 1.0},
    "TECHNICAL_FAILURE": {"base_minutes": 15, "factor": 2.0}
}

def calculate_next_retry(
    task: OutreachTask,
    outcome: str,
    hospital: Hospital,
    campaign: Campaign,
    now: datetime = None
) -> Tuple[str, Optional[datetime], str]:
    """
    Calculates next retry timestamp applying exponential backoff,
    calling hours clamping, and clinical deadline enforcement.
    Returns: (new_status, next_scheduled_time, reason)
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # 1. Max Retries Check
    max_retries = task.max_retries or hospital.max_retries or 3
    if task.attempt_count >= max_retries:
        return "MANUAL_FOLLOW_UP", None, f"Maximum outreach attempts ({task.attempt_count}/{max_retries}) reached. Escalated to manual follow-up."

    # 2. Outcome Backoff Calculation
    cfg = BACKOFF_CONFIG.get(outcome, {"base_minutes": 15, "factor": 1.5})
    multiplier = cfg["factor"] ** max(task.attempt_count - 1, 0)
    delay_minutes = cfg["base_minutes"] * multiplier
    target_time = now + timedelta(minutes=delay_minutes)

    # 3. Clinical Deadline Enforcement
    deadline = task.clinical_deadline
    if deadline:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        
        # If target retry is past deadline or deadline has less than 15 mins left
        if target_time >= deadline:
            if now < deadline - timedelta(minutes=15):
                # Expedite retry right before deadline
                target_time = deadline - timedelta(minutes=15)
            else:
                # Deadline expired or too close $\to$ Manual Follow-Up immediately
                return "MANUAL_FOLLOW_UP", None, f"Clinical deadline ({deadline.isoformat()}) expired or imminent. Handing off to clinical team."

    # 4. Hospital Calling Hours Clamping
    calling_start = hospital.calling_hours_start if hospital else 8
    calling_end = hospital.calling_hours_end if hospital else 20
    
    # If target_time falls after calling_end (e.g. 20:30), shift to next morning calling_start (08:30)
    if target_time.hour >= calling_end:
        # Move to tomorrow morning
        target_time = target_time.replace(hour=calling_start, minute=15, second=0) + timedelta(days=1)
    elif target_time.hour < calling_start:
        target_time = target_time.replace(hour=calling_start, minute=15, second=0)

    return "RETRY_SCHEDULED", target_time, f"Retry attempt {task.attempt_count + 1} scheduled for {target_time.isoformat()} ({outcome} backoff)."
