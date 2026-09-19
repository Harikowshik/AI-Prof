from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple
from backend.app.models.queue import OutreachTask
from backend.app.models.campaign import Campaign
from backend.app.models.healthcare import Discharge

# Component weights
W_RISK = 0.30
W_DEADLINE = 0.30
W_CALLBACK = 0.15
W_RETRY = 0.10
W_ELAPSED = 0.05
W_CAMPAIGN = 0.10
AGING_RATE_PER_HOUR = 0.02
MAX_AGING_BOOST = 0.25

def compute_task_priority(
    task: OutreachTask,
    campaign: Campaign,
    now: datetime = None
) -> Tuple[float, Dict[str, float]]:
    """
    Computes a continuous explainable priority score P in [0.0, 1.0]
    incorporating clinical risk, clinical deadline urgency, callback precedence,
    retry urgency, time since discharge, campaign priority, and wait-time aging.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # 1. Clinical Risk Component (S_risk)
    s_risk = task.risk_score or 0.5

    # 2. Deadline Urgency Component (S_deadline)
    deadline = task.clinical_deadline
    if deadline:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        hours_remaining = (deadline - now).total_seconds() / 3600.0
        
        if hours_remaining <= 0:
            s_deadline = 1.0 # Expired or cutoff imminent
        elif hours_remaining <= 2:
            s_deadline = 0.95
        elif hours_remaining <= 6:
            s_deadline = 0.80
        elif hours_remaining <= 12:
            s_deadline = 0.60
        elif hours_remaining <= 24:
            s_deadline = 0.40
        else:
            s_deadline = 0.20
    else:
        s_deadline = 0.30

    # 3. Callback Urgency Component (S_callback)
    s_callback = 0.0
    if task.status == "CALLBACK_SCHEDULED" and task.callback_scheduled_at:
        cb_time = task.callback_scheduled_at
        if cb_time.tzinfo is None:
            cb_time = cb_time.replace(tzinfo=timezone.utc)
        time_diff = (now - cb_time).total_seconds() / 60.0 # minutes
        
        if time_diff >= 0:
            s_callback = 1.0 # Due or overdue
        elif -30 <= time_diff < 0:
            s_callback = 0.85 # Due within 30 minutes

    # 4. Retry Urgency Component (S_retry)
    s_retry = 0.0
    if task.status == "RETRY_SCHEDULED":
        s_retry = min(1.0, 0.35 * max(task.attempt_count, 1))

    # 5. Time Elapsed Since Creation / Discharge (S_elapsed)
    created_at = task.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed_hours = (now - created_at).total_seconds() / 3600.0
    window_hours = campaign.clinical_window_hours if campaign else 48
    s_elapsed = min(1.0, max(0.0, elapsed_hours / max(window_hours, 1)))

    # 6. Campaign Priority Baseline (S_campaign)
    s_campaign = campaign.campaign_priority_weight if campaign else 0.5

    # 7. Starvation Prevention / Aging Boost
    wait_hours = elapsed_hours
    aging_boost = min(MAX_AGING_BOOST, AGING_RATE_PER_HOUR * wait_hours)

    # Calculate final continuous priority
    total_priority = (
        (W_RISK * s_risk) +
        (W_DEADLINE * s_deadline) +
        (W_CALLBACK * s_callback) +
        (W_RETRY * s_retry) +
        (W_ELAPSED * s_elapsed) +
        (W_CAMPAIGN * s_campaign) +
        aging_boost
    )
    
    # Clamp to [0.0, 1.5]
    total_priority = min(1.5, max(0.0, total_priority))

    breakdown = {
        "risk_score": round(s_risk, 3),
        "deadline_urgency": round(s_deadline, 3),
        "callback_urgency": round(s_callback, 3),
        "retry_urgency": round(s_retry, 3),
        "elapsed_urgency": round(s_elapsed, 3),
        "campaign_priority": round(s_campaign, 3),
        "starvation_boost": round(aging_boost, 3),
        "total_score": round(total_priority, 4)
    }
    
    return total_priority, breakdown
