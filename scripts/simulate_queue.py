import sys
import time
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone, timedelta
from backend.app.core.database import SessionLocal
from backend.app.models.tenant import Hospital, HospitalCapacity
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask
from backend.app.queue.scheduler import QueueScheduler
from backend.app.queue.stale_tasks import reap_stale_tasks
from backend.app.calls.simulator import TelephonySimulator

def run_interactive_queue_simulation(max_cycles: int = 15, delay_seconds: float = 1.0):
    """
    Executes an observable simulation of the capacity-constrained outbound queue
    with 20-30 patients, showing capacity bounding (e.g. 3/3 active), priority scheduling,
    retries, callbacks, escalations, max retries handoff, and worker failure recovery.
    """
    db = SessionLocal()
    try:
        print("=" * 80)
        print("  MULTI-HOSPITAL OUTREACH PLATFORM — 25-PATIENT DYNAMIC QUEUE SIMULATION")
        print("  Strict Concurrency Bounding, Deadline Pressure & Retries (PRD Section 53)")
        print("=" * 80)

        # 1. Setup St. Jude with intentionally constrained capacity = 3 for clear observation
        st_jude = db.query(Hospital).filter(Hospital.slug == "st-jude").first()
        if not st_jude:
            print("Error: St. Jude hospital not found. Run scripts/seed.py first.")
            return

        cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == st_jude.id).first()
        original_cap = cap.max_capacity if cap else 10
        if cap:
            cap.max_capacity = 3
            cap.current_active_calls = 0
            db.commit()

        print(f"Configured Hospital: {st_jude.name}")
        print(f"Telephony Concurrency Limit: {cap.max_capacity} Concurrent Lines (Intentionally constrained)")

        # Ensure active campaign is RUNNING
        campaign = db.query(Campaign).filter(
            Campaign.hospital_id == st_jude.id,
            Campaign.target_condition_or_dept == "CARDIOLOGY"
        ).first()
        if campaign:
            campaign.status = "RUNNING"
            db.commit()

        print(f"Active Campaign: {campaign.name if campaign else 'N/A'}\n")

        for cycle in range(1, max_cycles + 1):
            now = datetime.now(timezone.utc)
            
            # Step A: Reap any stale crashed tasks
            reaped = reap_stale_tasks(db, lease_timeout_seconds=30)

            # Step B: Attempt to dispatch calls up to capacity
            dispatched = []
            while True:
                task, err = QueueScheduler.schedule_next_available_task(
                    db=db,
                    hospital_id=st_jude.id,
                    worker_id=f"sim-worker-{random.randint(1, 3)}"
                )
                if not task:
                    break
                dispatched.append(task)

            # Step C: Simulate call progression for active tasks
            active_tasks = db.query(OutreachTask).filter(
                OutreachTask.hospital_id == st_jude.id,
                OutreachTask.status == "CALLING"
            ).all()

            # Randomly progress 1 or 2 active calls to realistic outcomes
            if active_tasks:
                target_task = random.choice(active_tasks)
                possible_outcomes = [
                    ("SUCCESSFUL", 60),
                    ("NO_ANSWER", 20),
                    ("BUSY", 10),
                    ("VOICEMAIL", 35),
                    ("DROPPED", 25),
                    ("CALLBACK_REQUESTED", 40)
                ]
                # Pick outcome
                outcome, dur = random.choices(
                    possible_outcomes,
                    weights=[0.35, 0.20, 0.15, 0.10, 0.10, 0.10]
                )[0]

                cb_target = (now + timedelta(minutes=15)) if outcome == "CALLBACK_REQUESTED" else None

                TelephonySimulator.simulate_call_outcome(
                    db=db,
                    task_id=target_task.id,
                    outcome=outcome,
                    duration_seconds=dur,
                    callback_time=cb_target,
                    answered_questions=["pain_status", "medication_adherence"] if outcome == "DROPPED" else None
                )

            # Step D: Read current queue state counts
            db.refresh(cap)
            tasks = db.query(OutreachTask).filter(OutreachTask.hospital_id == st_jude.id).all()
            counts = {
                "PENDING": 0, "CALLING": 0, "RETRY_SCHEDULED": 0,
                "CALLBACK_SCHEDULED": 0, "COMPLETED": 0, "ESCALATED": 0, "MANUAL_FOLLOW_UP": 0
            }
            for t in tasks:
                counts[t.status] = counts.get(t.status, 0) + 1

            # Invariant check
            assert cap.current_active_calls <= cap.max_capacity, f"CONCURRENCY BREACH: {cap.current_active_calls} > {cap.max_capacity}"

            print(f"[CYCLE {cycle:02d}] "
                  f"CAPACITY: {cap.current_active_calls}/{cap.max_capacity} | "
                  f"PENDING: {counts['PENDING']:<2} | "
                  f"CALLING: {counts['CALLING']:<2} | "
                  f"RETRY_SCHED: {counts['RETRY_SCHEDULED']:<2} | "
                  f"CALLBACKS: {counts['CALLBACK_SCHEDULED']:<2} | "
                  f"COMPLETED: {counts['COMPLETED']:<2} | "
                  f"MANUAL_FOLLOW_UP: {counts['MANUAL_FOLLOW_UP']:<2}")

            time.sleep(delay_seconds)

        # Restore original capacity
        if cap:
            cap.max_capacity = original_cap
            db.commit()

        print("\nSimulation concluded successfully. All concurrency invariants maintained.")
    finally:
        db.close()

if __name__ == "__main__":
    run_interactive_queue_simulation(max_cycles=8, delay_seconds=0.5)
