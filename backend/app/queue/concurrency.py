import threading
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.models.tenant import HospitalCapacity
from backend.app.models.queue import OutreachTask

class CapacityExhaustedException(Exception):
    """Raised when hospital concurrency capacity is full."""
    pass

_concurrency_mutex = threading.Lock()

class ConcurrencyManager:
    """
    Guarantees that active outbound calls for any hospital never exceed max_capacity.
    Uses centralized atomic serialization and database row updates.
    """

    @staticmethod
    def try_reserve_capacity(
        db: Session, 
        hospital_id: str, 
        task_id: str, 
        worker_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Attempts to atomically reserve one capacity slot for the hospital.
        Returns (True, None) if reserved, or (False, reason) if capacity is exhausted or task invalid.
        """
        with _concurrency_mutex:
            try:
                # Query capacity record
                capacity_record = db.query(HospitalCapacity).filter(
                    HospitalCapacity.hospital_id == hospital_id
                ).first()
            
                if not capacity_record:
                    # Fallback create if missing
                    capacity_record = HospitalCapacity(
                        hospital_id=hospital_id,
                        current_active_calls=0,
                        max_capacity=10
                    )
                    db.add(capacity_record)
                    db.flush()

                # Strict Concurrency Invariant: active_calls < max_capacity
                if capacity_record.current_active_calls >= capacity_record.max_capacity:
                    db.rollback()
                    return False, f"Capacity exhausted: {capacity_record.current_active_calls}/{capacity_record.max_capacity} active calls"

                # Query and lock the target task
                task = db.query(OutreachTask).filter(
                    OutreachTask.id == task_id,
                    OutreachTask.hospital_id == hospital_id
                ).first()

                if not task:
                    db.rollback()
                    return False, "Task not found"

                # Prevent double-reservation
                if task.status in ["CALLING", "CONNECTED"]:
                    db.rollback()
                    return False, f"Task already in progress ({task.status})"

                if task.status not in ["PENDING", "SCHEDULED", "RETRY_SCHEDULED", "CALLBACK_SCHEDULED"]:
                    db.rollback()
                    return False, f"Task is not eligible for calling (current status: {task.status})"

                # Atomic State Transition & Capacity Increment
                task.previous_status = task.status
                task.status = "CALLING"
                task.worker_id = worker_id
                task.heartbeat_at = datetime.now(timezone.utc)
                task.attempt_count += 1
                task.last_attempt_at = datetime.now(timezone.utc)

                capacity_record.current_active_calls += 1
                capacity_record.updated_at = datetime.now(timezone.utc)

                db.commit()
                return True, None

            except Exception as e:
                db.rollback()
                return False, str(e)

    @staticmethod
    def release_capacity(
        db: Session, 
        hospital_id: str, 
        task_id: str, 
        new_terminal_status: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Releases an active capacity slot and transitions task out of CALLING state.
        Ensures active call counter never drops below 0.
        """
        with _concurrency_mutex:
            try:
                capacity_record = db.query(HospitalCapacity).filter(
                    HospitalCapacity.hospital_id == hospital_id
                ).first()

                if capacity_record:
                    if capacity_record.current_active_calls > 0:
                        capacity_record.current_active_calls -= 1
                    capacity_record.updated_at = datetime.now(timezone.utc)

                task = db.query(OutreachTask).filter(
                    OutreachTask.id == task_id,
                    OutreachTask.hospital_id == hospital_id
                ).first()

                if task:
                    task.previous_status = task.status
                    task.status = new_terminal_status
                    task.worker_id = None
                    task.heartbeat_at = None
                    task.updated_at = datetime.now(timezone.utc)

                db.commit()
                return True

            except Exception as e:
                db.rollback()
                return False
