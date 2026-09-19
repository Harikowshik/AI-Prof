from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import Hospital, HospitalCapacity
from backend.app.models.healthcare import Patient
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask, CallRecord, EscalationRecord

router = APIRouter(prefix="/analytics", tags=["Operational Analytics"])

@router.get("/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Computes real-time operational outreach analytics from database records.
    Never returns hard-coded numbers.
    """
    target_hospital_id = tenant_ctx.hospital_id
    
    # Query base filters
    p_query = db.query(Patient)
    c_query = db.query(Campaign)
    t_query = db.query(OutreachTask)
    call_query = db.query(CallRecord)
    esc_query = db.query(EscalationRecord)

    if not tenant_ctx.is_platform_admin:
        p_query = p_query.filter(Patient.hospital_id == target_hospital_id)
        c_query = c_query.filter(Campaign.hospital_id == target_hospital_id)
        t_query = t_query.filter(OutreachTask.hospital_id == target_hospital_id)
        call_query = call_query.filter(CallRecord.hospital_id == target_hospital_id)
        esc_query = esc_query.filter(EscalationRecord.hospital_id == target_hospital_id)
    elif target_hospital_id:
        p_query = p_query.filter(Patient.hospital_id == target_hospital_id)
        c_query = c_query.filter(Campaign.hospital_id == target_hospital_id)
        t_query = t_query.filter(OutreachTask.hospital_id == target_hospital_id)
        call_query = call_query.filter(CallRecord.hospital_id == target_hospital_id)
        esc_query = esc_query.filter(EscalationRecord.hospital_id == target_hospital_id)

    total_patients = p_query.count()
    total_campaigns = c_query.count()
    total_tasks = t_query.count()
    
    completed_tasks = t_query.filter(OutreachTask.status == "COMPLETED").count()
    escalated_tasks = t_query.filter(OutreachTask.status == "ESCALATED").count()
    manual_tasks = t_query.filter(OutreachTask.status == "MANUAL_FOLLOW_UP").count()
    calling_tasks = t_query.filter(OutreachTask.status == "CALLING").count()
    pending_tasks = t_query.filter(OutreachTask.status.in_(["PENDING", "SCHEDULED", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"])).count()

    total_calls = call_query.count()
    successful_calls = call_query.filter(CallRecord.outcome == "SUCCESSFUL").count()
    no_answer_calls = call_query.filter(CallRecord.outcome == "NO_ANSWER").count()
    busy_calls = call_query.filter(CallRecord.outcome == "BUSY").count()
    dropped_calls = call_query.filter(CallRecord.outcome == "DROPPED").count()
    callback_calls = call_query.filter(CallRecord.outcome == "CALLBACK_REQUESTED").count()

    # Contact Rate Calculation
    contact_rate = round((successful_calls / max(total_calls, 1)) * 100.0, 1) if total_calls > 0 else 0.0

    # Average attempts per completed task
    avg_attempts = db.query(func.avg(OutreachTask.attempt_count)).filter(
        OutreachTask.status.in_(["COMPLETED", "ESCALATED", "MANUAL_FOLLOW_UP"])
    )
    if not tenant_ctx.is_platform_admin and target_hospital_id:
        avg_attempts = avg_attempts.filter(OutreachTask.hospital_id == target_hospital_id)
    avg_attempts_val = avg_attempts.scalar() or 1.0

    return {
        "tenant_id": target_hospital_id or "ALL_PLATFORM",
        "total_patients": total_patients,
        "total_campaigns": total_campaigns,
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "active_calling_tasks": calling_tasks,
        "completed_tasks": completed_tasks,
        "escalated_tasks": escalated_tasks,
        "manual_follow_up_tasks": manual_tasks,
        "total_calls_dialed": total_calls,
        "successful_calls": successful_calls,
        "contact_rate_percent": contact_rate,
        "average_attempts_per_case": round(float(avg_attempts_val), 2),
        "call_outcomes_breakdown": {
            "SUCCESSFUL": successful_calls,
            "NO_ANSWER": no_answer_calls,
            "BUSY": busy_calls,
            "DROPPED": dropped_calls,
            "CALLBACK_REQUESTED": callback_calls
        }
    }
