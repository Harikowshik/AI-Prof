import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.tenant import Hospital, HospitalCapacity
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask
from backend.app.queue.priority import compute_task_priority
from backend.app.queue.concurrency import ConcurrencyManager

class QueueScheduler:
    """
    Central Outbound Queue Scheduler coordinating multi-factor priority scoring,
    deadline pressure, starvation aging, and atomic capacity reservation.
    """

    @staticmethod
    def refresh_and_score_tasks(db: Session, hospital_id: str) -> List[OutreachTask]:
        """
        Updates computed_priority for all candidate tasks in the hospital queue.
        """
        now = datetime.now(timezone.utc)
        
        # Only process tasks in RUNNING campaigns
        candidate_tasks = db.query(OutreachTask).join(Campaign).filter(
            OutreachTask.hospital_id == hospital_id,
            Campaign.status == "RUNNING",
            OutreachTask.status.in_(["PENDING", "SCHEDULED", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"])
        ).all()

        campaign_cache = {}
        for task in candidate_tasks:
            if task.campaign_id not in campaign_cache:
                campaign_cache[task.campaign_id] = db.query(Campaign).filter(Campaign.id == task.campaign_id).first()
            camp = campaign_cache[task.campaign_id]
            
            # If retry or callback, check if scheduled time has arrived
            if task.status in ["RETRY_SCHEDULED", "CALLBACK_SCHEDULED"] and task.scheduled_for:
                task_sched = task.scheduled_for
                if task_sched.tzinfo is None:
                    task_sched = task_sched.replace(tzinfo=timezone.utc)
                if now < task_sched:
                    # Still in waiting period
                    continue

            score, breakdown = compute_task_priority(task, camp, now=now)
            task.computed_priority = score
            task.risk_score = breakdown["risk_score"]
            task.deadline_urgency = breakdown["deadline_urgency"]
            task.starvation_boost = breakdown["starvation_boost"]

        db.commit()
        return candidate_tasks

    @staticmethod
    def get_ranked_queue(
        db: Session, 
        hospital_id: str, 
        limit: int = 50, 
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Returns ranked queue sorted by computed_priority descending with patient context.
        """
        QueueScheduler.refresh_and_score_tasks(db, hospital_id)
        now = datetime.now(timezone.utc)

        query = db.query(OutreachTask).filter(
            OutreachTask.hospital_id == hospital_id
        ).order_by(OutreachTask.computed_priority.desc(), OutreachTask.created_at.asc())

        total = query.count()
        tasks = query.offset(offset).limit(limit).all()

        results = []
        for t in tasks:
            patient = t.patient
            hours_rem = None
            if t.clinical_deadline:
                dl = t.clinical_deadline
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                hours_rem = round((dl - now).total_seconds() / 3600.0, 1)

            results.append({
                "task_id": t.id,
                "hospital_id": t.hospital_id,
                "patient_id": t.patient_id,
                "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
                "mrn": patient.mrn if patient else "N/A",
                "phone": patient.phone_number if patient else "N/A",
                "campaign_id": t.campaign_id,
                "campaign_name": t.campaign.name if t.campaign else "N/A",
                "status": t.status,
                "computed_priority": round(t.computed_priority, 4),
                "risk_score": t.risk_score,
                "deadline_urgency": t.deadline_urgency,
                "starvation_boost": t.starvation_boost,
                "clinical_deadline": t.clinical_deadline.isoformat() if t.clinical_deadline else None,
                "hours_until_deadline": hours_rem,
                "attempt_count": t.attempt_count,
                "max_retries": t.max_retries,
                "scheduled_for": t.scheduled_for.isoformat() if t.scheduled_for else None,
                "callback_scheduled_at": t.callback_scheduled_at.isoformat() if t.callback_scheduled_at else None,
                "worker_id": t.worker_id,
                "created_at": t.created_at.isoformat()
            })

        return results, total

    @staticmethod
    def schedule_next_available_task(
        db: Session, 
        hospital_id: str, 
        worker_id: str = None
    ) -> Tuple[Optional[OutreachTask], Optional[str]]:
        """
        Finds the highest priority task ready to be dialed, atomically reserves capacity,
        and transitions the task into CALLING state.
        """
        if worker_id is None:
            worker_id = f"worker-{uuid.uuid4().hex[:8]}"

        # Refresh scores
        QueueScheduler.refresh_and_score_tasks(db, hospital_id)
        now = datetime.now(timezone.utc)

        # Check hospital calling hours
        hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if hospital:
            calling_start = hospital.calling_hours_start
            calling_end = hospital.calling_hours_end
            current_hour = now.hour # Note: in real deployment adjusted to hospital.timezone
            if current_hour < calling_start or current_hour >= calling_end:
                return None, f"Outside permitted hospital calling hours ({calling_start}:00 - {calling_end}:00)"

        # Find candidate task: eligible status, campaign running, scheduled_for <= now
        candidate = db.query(OutreachTask).join(Campaign).filter(
            OutreachTask.hospital_id == hospital_id,
            Campaign.status == "RUNNING",
            OutreachTask.status.in_(["PENDING", "SCHEDULED", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"]),
            (OutreachTask.scheduled_for == None) | (OutreachTask.scheduled_for <= now)
        ).order_by(OutreachTask.computed_priority.desc()).first()

        if not candidate:
            return None, "No eligible tasks ready for scheduling in queue"

        # Attempt atomic capacity reservation
        success, reason = ConcurrencyManager.try_reserve_capacity(
            db=db,
            hospital_id=hospital_id,
            task_id=candidate.id,
            worker_id=worker_id
        )

        if not success:
            return None, reason

        db.refresh(candidate)
        return candidate, None
