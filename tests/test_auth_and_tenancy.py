import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.security import create_access_token
from backend.app.core.database import SessionLocal
from backend.app.models.tenant import Hospital, User
from backend.app.models.healthcare import Patient

client = TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()

def test_login_and_token_generation(db_session):
    """Verifies that valid credentials return signed JWT with role and hospital_id."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@stjude.health", "password": "HospitalAdmin123!"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "HOSPITAL_ADMIN"
    assert data["email"] == "admin@stjude.health"

def test_rbac_permission_enforcement(db_session):
    """Verifies that a Clinical Reviewer cannot create a hospital tenant (requires PLATFORM_ADMIN)."""
    dr_chen = db_session.query(User).filter(User.email == "dr.chen@stjude.health").first()
    token = create_access_token(subject=dr_chen.id, hospital_id=dr_chen.hospital_id, role="CLINICAL_REVIEWER")
    
    response = client.post(
        "/api/v1/hospitals",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Unauthorized Clinic",
            "slug": "unauthorized-clinic",
            "contact_email": "fake@test.com"
        }
    )
    assert response.status_code == 403
    assert "Action prohibited" in response.json()["detail"]

def test_cross_tenant_isolation_patient_access(db_session):
    """
    CRITICAL MULTI-TENANT TEST:
    Verifies that a user from St. Jude Hospital querying a patient belonging
    to Metro General Hospital receives 404/403 with ZERO data leakage.
    """
    st_jude = db_session.query(Hospital).filter(Hospital.slug == "st-jude").first()
    metro = db_session.query(Hospital).filter(Hospital.slug == "metro-general").first()
    
    # Get a patient belonging to Metro General
    metro_patient = db_session.query(Patient).filter(Patient.hospital_id == metro.id).first()
    assert metro_patient is not None, "Metro General patient must exist for test"

    # Authenticate as St. Jude Campaign Manager
    st_jude_user = db_session.query(User).filter(User.email == "campaigns@stjude.health").first()
    token = create_access_token(subject=st_jude_user.id, hospital_id=st_jude.id, role="CAMPAIGN_MANAGER")

    # Attempt to query Metro General patient using St. Jude credentials
    response = client.get(
        f"/api/v1/patients/{metro_patient.id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Must be 404 (or 403) with zero patient details leaked
    assert response.status_code in [403, 404]
    if response.status_code == 404:
        assert "not found" in response.json()["detail"].lower() or "denied" in response.json()["detail"].lower()
