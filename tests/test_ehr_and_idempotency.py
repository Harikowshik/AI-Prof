import pytest
import uuid
from backend.app.core.database import SessionLocal
from backend.app.core.idempotency import idempotency_manager, generate_idempotency_key
from backend.app.models.tenant import Hospital
from backend.app.models.healthcare import Patient
from backend.app.ehr.mock_service import MockEHRService

@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()

def test_mock_ehr_service_communication_and_observation(db_session):
    """Verifies that MockEHRService records FHIR-like communication and observations."""
    st_jude = db_session.query(Hospital).filter(Hospital.slug == "st-jude").first()
    patient = db_session.query(Patient).filter(Patient.hospital_id == st_jude.id).first()

    ehr = MockEHRService(db_session, simulate_failures=False)
    
    # 1. Record communication
    comm = ehr.record_communication(
        hospital_id=st_jude.id,
        patient_id=patient.id,
        communication_type="POST_DISCHARGE_CALL",
        summary="Automated patient outreach completed successfully.",
        payload={"call_outcome": "SUCCESSFUL"}
    )
    assert comm["success"] is True
    assert comm["resourceType"] == "Communication"
    assert "operation_id" in comm

    # 2. Record observation
    obs = ehr.create_observation(
        hospital_id=st_jude.id,
        patient_id=patient.id,
        code="systolic-bp",
        display_name="Systolic Blood Pressure",
        value=124,
        unit="mmHg"
    )
    assert obs["success"] is True
    assert obs["code"] == "systolic-bp"

def test_mock_ehr_failure_mode_and_recovery(db_session):
    """Verifies that when EHR failure mode is active, operations report explicit error states."""
    st_jude = db_session.query(Hospital).filter(Hospital.slug == "st-jude").first()
    patient = db_session.query(Patient).filter(Patient.hospital_id == st_jude.id).first()

    # Simulate EHR gateway outage
    degraded_ehr = MockEHRService(db_session, simulate_failures=True)
    res = degraded_ehr.record_communication(
        hospital_id=st_jude.id,
        patient_id=patient.id,
        communication_type="POST_DISCHARGE_CALL",
        summary="Test attempt during outage",
        payload={}
    )
    assert res["success"] is False
    assert res["error"] == "EHR_GATEWAY_TIMEOUT"

def test_idempotency_key_prevents_duplicate_side_effects():
    """
    IDEMPOTENCY TEST:
    Verifies that the same event payload delivered twice generates the same key
    and is flagged as already processed to prevent duplicate calls/escalations.
    """
    event_id = f"event-{uuid.uuid4().hex[:8]}"
    patient_id = f"pat-{uuid.uuid4().hex[:8]}"
    
    key1 = generate_idempotency_key(event_id, patient_id, "SCHEDULE_CALL")
    key2 = generate_idempotency_key(event_id, patient_id, "SCHEDULE_CALL")
    assert key1 == key2

    # First delivery
    assert not idempotency_manager.is_processed(key1)
    idempotency_manager.record_key(key1)

    # Second delivery of duplicate event
    assert idempotency_manager.is_processed(key2) is True
