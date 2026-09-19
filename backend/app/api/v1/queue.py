from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import case

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import Hospital, HospitalCapacity, User
from backend.app.models.queue import OutreachTask
from backend.app.queue.scheduler import QueueScheduler
from backend.app.queue.stale_tasks import reap_stale_tasks

router = APIRouter(prefix="/queue", tags=["Outbound Queue & Concurrency"])

class QueueStatsResponse(BaseModel):
    hospital_id: str
    active_calls: int
    max_capacity: int
    capacity_utilization_percent: float
    total_pending: int
    pending_tasks: int = 0
    total_scheduled: int = 0
    total_retry_scheduled: int = 0
    total_callback_scheduled: int = 0
    total_calling: int = 0
    in_progress_tasks: int = 0
    total_completed: int = 0
    completed_tasks: int = 0
    total_escalated: int = 0
    total_manual_follow_up: int = 0
    oldest_pending_hours: Optional[float] = None
    tasks_approaching_cutoff: int = 0

@router.get("")
@router.get("/tasks")
def get_live_queue(
    hospital_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Returns dynamically ranked queue strictly scoped to caller's hospital.
    Sorts by continuous computed_priority with deadline pressure and starvation boost.
    Supports both /queue and /queue/tasks.
    """
    target_hospital_id = hospital_id or tenant_ctx.hospital_id
    if not target_hospital_id:
        # Default to first available hospital if platform admin
        h = db.query(Hospital).first()
        target_hospital_id = h.id if h else None

    if not target_hospital_id:
        return []

    QueueScheduler.refresh_and_score_tasks(db, target_hospital_id)
    now = datetime.now(timezone.utc)

    query = db.query(OutreachTask).filter(
        OutreachTask.hospital_id == target_hospital_id
    )

    if status and status.upper() in ["PENDING", "CLAIMED", "CALLING", "IN_PROGRESS", "COMPLETED", "FAILED", "DROPPED"]:
        st = "CALLING" if status.upper() == "IN_PROGRESS" else status.upper()
        query = query.filter(OutreachTask.status == st)

    limit_val = int(limit.default) if hasattr(limit, "default") else int(limit or 50)
    offset_val = int(offset.default) if hasattr(offset, "default") else int(offset or 0)
    tasks = query.order_by(
        case(
            (OutreachTask.status == 'CALLING', 1),
            (OutreachTask.status.in_(['PENDING', 'SCHEDULED', 'RETRY_SCHEDULED', 'CALLBACK_SCHEDULED']), 2),
            else_=3
        ),
        OutreachTask.computed_priority.desc(),
        OutreachTask.created_at.desc()
    ).offset(offset_val).limit(limit_val).all()

    formatted_tasks = []
    for t in tasks:
        p = t.patient
        c = t.campaign
        risk_tier = "HIGH" if (t.risk_score or 0) >= 0.7 else ("MEDIUM" if (t.risk_score or 0) >= 0.4 else "LOW")
        formatted_tasks.append({
            "id": t.id,
            "task_id": t.id,
            "patient_id": t.patient_id,
            "patient_name": f"{p.first_name} {p.last_name}" if p else "Patient",
            "patient_phone": p.phone_number if p else None,
            "mrn": p.mrn if p else "N/A",
            "campaign_id": t.campaign_id,
            "campaign_name": c.name if c else "Outreach Campaign",
            "condition": getattr(c, "target_condition_or_dept", "Post-Discharge Recovery") if c else "Post-Discharge Recovery",
            "risk_tier": risk_tier,
            "risk_score": t.risk_score or 0.5,
            "priority_score": round(t.computed_priority or 0.5, 4),
            "computed_priority": round(t.computed_priority or 0.5, 4),
            "status": "IN_PROGRESS" if t.status == "CALLING" else t.status,
            "attempts": t.attempt_count or 0,
            "max_attempts": 3,
            "clinical_deadline": t.clinical_deadline.isoformat() if t.clinical_deadline else None,
            "scheduled_time": t.scheduled_for.isoformat() if t.scheduled_for else None,
            "context_state": {
                "stage": t.conversation_stage,
                "partial_transcript": t.partial_transcript or [],
                "partial_observations": t.partial_observations or []
            } if (t.partial_transcript or t.conversation_stage != "NOT_STARTED") else None
        })

    return formatted_tasks

@router.get("/stats", response_model=QueueStatsResponse)
def get_queue_statistics(
    hospital_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Returns live queue operational statistics and capacity utilization."""
    target_hospital_id = hospital_id or tenant_ctx.hospital_id
    if not target_hospital_id:
        h = db.query(Hospital).first()
        target_hospital_id = h.id if h else None

    if not target_hospital_id:
        raise HTTPException(status_code=404, detail="No hospital context found")

    cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == target_hospital_id).first()
    active_calls = cap.current_active_calls if cap else 0
    max_capacity = cap.max_capacity if cap else 10
    
    # Calculate counts by state
    tasks = db.query(OutreachTask).filter(OutreachTask.hospital_id == target_hospital_id).all()
    counts = {
        "PENDING": 0, "SCHEDULED": 0, "RETRY_SCHEDULED": 0, "CALLBACK_SCHEDULED": 0,
        "CALLING": 0, "COMPLETED": 0, "ESCALATED": 0, "MANUAL_FOLLOW_UP": 0
    }
    
    now = datetime.now(timezone.utc)
    oldest_pending_time = None
    cutoff_risk_count = 0

    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
        
        if t.status in ["PENDING", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"]:
            if oldest_pending_time is None or t.created_at < oldest_pending_time:
                oldest_pending_time = t.created_at
                
            if t.clinical_deadline:
                dl = t.clinical_deadline
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                if 0 <= (dl - now).total_seconds() <= 6 * 3600:
                    cutoff_risk_count += 1

    oldest_hours = None
    if oldest_pending_time:
        if oldest_pending_time.tzinfo is None:
            oldest_pending_time = oldest_pending_time.replace(tzinfo=timezone.utc)
        oldest_hours = round((now - oldest_pending_time).total_seconds() / 3600.0, 1)

    util_pct = round((active_calls / max(max_capacity, 1)) * 100.0, 1)

    return QueueStatsResponse(
        hospital_id=target_hospital_id,
        active_calls=active_calls,
        max_capacity=max_capacity,
        capacity_utilization_percent=util_pct,
        total_pending=counts["PENDING"],
        pending_tasks=counts["PENDING"] + counts["SCHEDULED"] + counts["RETRY_SCHEDULED"],
        total_scheduled=counts["SCHEDULED"],
        total_retry_scheduled=counts["RETRY_SCHEDULED"],
        total_callback_scheduled=counts["CALLBACK_SCHEDULED"],
        total_calling=counts["CALLING"],
        in_progress_tasks=counts["CALLING"],
        total_completed=counts["COMPLETED"],
        completed_tasks=counts["COMPLETED"],
        total_escalated=counts["ESCALATED"],
        total_manual_follow_up=counts["MANUAL_FOLLOW_UP"],
        oldest_pending_hours=oldest_hours,
        tasks_approaching_cutoff=cutoff_risk_count
    )

class ScheduleBatchRequest(BaseModel):
    limit: Optional[int] = 2
    batch_size: Optional[int] = 2

@router.post("/schedule-next")
def schedule_next_call(
    payload: Optional[ScheduleBatchRequest] = None,
    worker_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER", "CLINICAL_REVIEWER"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Atomically reserves capacity and schedules the top-priority task(s) up to batch limit.
    Returns error if capacity is full (guaranteeing active_calls <= max_capacity).
    """
    target_hospital_id = tenant_ctx.hospital_id
    if not target_hospital_id:
        h = db.query(Hospital).first()
        target_hospital_id = h.id if h else None

    if not target_hospital_id:
        raise HTTPException(status_code=400, detail="hospital_id context required")

    batch_limit = 2
    if payload and payload.limit:
        batch_limit = payload.limit
    elif payload and payload.batch_size:
        batch_limit = payload.batch_size

    claimed_tasks = []
    last_err = None

    for _ in range(batch_limit):
        task, error_msg = QueueScheduler.schedule_next_available_task(
            db=db,
            hospital_id=target_hospital_id,
            worker_id=worker_id or f"user-{current_user.id[:8]}"
        )
        if task:
            claimed_tasks.append(task)
        else:
            last_err = error_msg
            break

    cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == target_hospital_id).first()
    active_calls = cap.current_active_calls if cap else len(claimed_tasks)
    max_cap = cap.max_capacity if cap else 10

    if not claimed_tasks and last_err and active_calls >= max_cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Capacity exhausted: active calls ({active_calls}/{max_cap}) have reached maximum line capacity."
        )

    first_task = claimed_tasks[0] if claimed_tasks else None
    patient = first_task.patient if first_task else None

    return {
        "success": True,
        "claimed_count": len(claimed_tasks),
        "active_calls": active_calls,
        "max_capacity": max_cap,
        "message": f"Scheduled {len(claimed_tasks)} tasks." if claimed_tasks else (last_err or "No eligible tasks ready in queue."),
        "task_id": first_task.id if first_task else None,
        "patient_id": first_task.patient_id if first_task else None,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        "phone": patient.phone_number if patient else "Unknown",
        "status": first_task.status if first_task else "IDLE",
        "computed_priority": round(first_task.computed_priority, 4) if first_task else 0.0,
        "worker_id": first_task.worker_id if first_task else None,
        "attempt_count": first_task.attempt_count if first_task else 0
    }

@router.post("/reap-stale")
def trigger_stale_task_recovery(
    lease_timeout_seconds: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN", "CAMPAIGN_MANAGER", "CLINICAL_REVIEWER"]))
):
    """
    Runs the stale task reaper job: detects crashed workers,
    releases capacity, and recovers orphaned tasks.
    """
    recovered = reap_stale_tasks(db, lease_timeout_seconds=lease_timeout_seconds)
    return {
        "recovered_count": len(recovered),
        "reaped_count": len(recovered),
        "recovered_tasks": recovered
    }
