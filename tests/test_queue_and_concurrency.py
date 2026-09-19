import pytest
import uuid
import threading
from datetime import datetime, timezone, timedelta
from backend.app.core.database import SessionLocal
from backend.app.models.tenant import Hospital, HospitalCapacity
from backend.app.models.healthcare import Patient
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask
from backend.app.queue.priority import compute_task_priority
from backend.app.queue.concurrency import ConcurrencyManager
from backend.app.queue.retries import calculate_next_retry
from backend.app.queue.stale_tasks import reap_stale_tasks

@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()

def test_concurrency_capacity_limit_under_parallel_workers(db_session):
    """
    CRITICAL CONCURRENCY TEST:
    Sets hospital capacity = 5.
    Simulates 25 concurrent worker threads attempting to reserve slots.
    Guarantees: Exactly 5 succeed, 20 are rejected.
    Active calls NEVER exceed 5.
    """
    hospital = db_session.query(Hospital).filter(Hospital.slug == "st-jude").first()
    cap = db_session.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == hospital.id).first()
    campaign = db_session.query(Campaign).filter(Campaign.hospital_id == hospital.id).first()
    patient = db_session.query(Patient).filter(Patient.hospital_id == hospital.id).first()
    
    # Configure capacity = 5 for test
    original_cap = cap.max_capacity
    cap.max_capacity = 5
    cap.current_active_calls = 0
    db_session.commit()

    # Create 25 dummy tasks in PENDING state with real patient/campaign
    tasks = []
    now = datetime.now(timezone.utc)
    for i in range(25):
        t = OutreachTask(
            hospital_id=hospital.id,
            patient_id=patient.id,
            campaign_id=campaign.id,
            status="PENDING",
            clinical_deadline=now + timedelta(hours=24)
        )
        db_session.add(t)
        tasks.append(t)
    db_session.commit()

    results = []
    
    def worker_reserve(task_id: str, worker_id: str):
        worker_db = SessionLocal()
        try:
            success, reason = ConcurrencyManager.try_reserve_capacity(
                db=worker_db,
                hospital_id=hospital.id,
                task_id=task_id,
                worker_id=worker_id
            )
            results.append((success, reason))
        finally:
            worker_db.close()

    # Launch 25 concurrent threads
    threads = []
    for i in range(25):
        t = threading.Thread(target=worker_reserve, args=(tasks[i].id, f"worker-{i}"))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    success_count = sum(1 for r in results if r[0] is True)
    failure_count = sum(1 for r in results if r[0] is False)

    db_session.refresh(cap)
    assert success_count == 5, f"Expected exactly 5 successful reservations, got {success_count}"
    assert failure_count == 20, f"Expected exactly 20 capacity rejections, got {failure_count}"
    assert cap.current_active_calls == 5, f"Expected current active calls to be 5, got {cap.current_active_calls}"

    # Cleanup: release reserved tasks and reset capacity
    for t in tasks:
        t.status = "COMPLETED"
    cap.current_active_calls = 0
    cap.max_capacity = original_cap
    db_session.commit()

def test_deadline_pressure_overcomes_baseline_risk(db_session):
    """
    PRIORITY ALGORITHM TEST:
    Patient A: High Risk (0.8), 36 hours remaining before clinical deadline.
    Patient B: Medium Risk (0.5), 45 minutes remaining before clinical cutoff.
    Proves that Patient B is scheduled BEFORE Patient A due to deadline urgency.
    """
    now = datetime.now(timezone.utc)
    camp = Campaign(clinical_window_hours=48, campaign_priority_weight=0.5)

    # Task A: High risk, plenty of time left
    task_a = OutreachTask(
        risk_score=0.80,
        clinical_deadline=now + timedelta(hours=36),
        status="PENDING",
        created_at=now - timedelta(minutes=30)
    )

    # Task B: Medium risk, deadline cutoff in 45 minutes!
    task_b = OutreachTask(
        risk_score=0.50,
        clinical_deadline=now + timedelta(minutes=45),
        status="PENDING",
        created_at=now - timedelta(minutes=60)
    )

    score_a, breakdown_a = compute_task_priority(task_a, camp, now=now)
    score_b, breakdown_b = compute_task_priority(task_b, camp, now=now)

    assert score_b > score_a, f"Task B (expiring soon) must rank higher than Task A! ({score_b:.3f} vs {score_a:.3f})"
    assert breakdown_b["deadline_urgency"] > breakdown_a["deadline_urgency"]

def test_starvation_prevention_aging_factor(db_session):
    """
    STARVATION TEST:
    A low-risk patient waiting in queue for 12 hours receives an aging boost
    that prevents indefinite starvation by newly arriving patients.
    """
    now = datetime.now(timezone.utc)
    camp = Campaign(clinical_window_hours=48, campaign_priority_weight=0.5)

    fresh_low_risk = OutreachTask(
        risk_score=0.25,
        clinical_deadline=now + timedelta(hours=40),
        status="PENDING",
        created_at=now
    )

    starved_low_risk = OutreachTask(
        risk_score=0.25,
        clinical_deadline=now + timedelta(hours=40),
        status="PENDING",
        created_at=now - timedelta(hours=10)
    )

    score_fresh, _ = compute_task_priority(fresh_low_risk, camp, now=now)
    score_starved, breakdown_starved = compute_task_priority(starved_low_risk, camp, now=now)

    assert score_starved > score_fresh
    assert breakdown_starved["starvation_boost"] == 0.20 # 10h * 0.02

def test_stale_task_recovery_releases_capacity(db_session):
    """
    WORKER CRASH TEST:
    Simulates a worker crashing while holding capacity.
    Verifies that the stale task reaper detects the expired lease,
    releases capacity, and re-queues the task.
    """
    hospital = db_session.query(Hospital).filter(Hospital.slug == "st-jude").first()
    cap = db_session.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == hospital.id).first()
    campaign = db_session.query(Campaign).filter(Campaign.hospital_id == hospital.id).first()
    patient = db_session.query(Patient).filter(Patient.hospital_id == hospital.id).first()
    
    # Ensure no previous orphaned tasks in CALLING state
    db_session.query(OutreachTask).filter(
        OutreachTask.hospital_id == hospital.id,
        OutreachTask.status == "CALLING"
    ).update({"status": "FAILED"})
    
    cap.current_active_calls = 3
    db_session.commit()

    # Create task with expired heartbeat and valid foreign keys
    now = datetime.now(timezone.utc)
    task = OutreachTask(
        hospital_id=hospital.id,
        patient_id=patient.id,
        campaign_id=campaign.id,
        status="CALLING",
        worker_id="crashed-worker-node-4",
        heartbeat_at=now - timedelta(seconds=90),
        clinical_deadline=now + timedelta(hours=24),
        attempt_count=1,
        max_retries=3
    )
    db_session.add(task)
    db_session.commit()

    # Run reaper with 60s timeout
    recovered = reap_stale_tasks(db_session, lease_timeout_seconds=60)
    
    db_session.refresh(cap)
    db_session.refresh(task)

    assert any(r["task_id"] == task.id for r in recovered)
    assert task.status == "RETRY_SCHEDULED"
    assert task.worker_id is None
    assert cap.current_active_calls == 2, "Capacity must be decremented upon stale recovery"

    # Cleanup
    cap.current_active_calls = 0
    db_session.commit()
