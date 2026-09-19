import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class Patient(Base):
    """FHIR-inspired Patient entity strictly scoped to a hospital tenant."""
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    mrn = Column(String(100), nullable=False, index=True) # Medical Record Number
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(String(20), nullable=False)
    gender = Column(String(20), nullable=False)
    phone_number = Column(String(50), nullable=False)
    email = Column(String(255), nullable=True)
    
    # Preferences & Baseline Risk
    communication_preference = Column(String(50), default="PHONE", nullable=False)
    consent_granted = Column(Boolean, default=True, nullable=False)
    # Risk tiers: LOW, MEDIUM, HIGH, URGENT
    clinical_risk_tier = Column(String(50), default="MEDIUM", nullable=False, index=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    hospital = relationship("Hospital", back_populates="patients")
    encounters = relationship("Encounter", back_populates="patient", cascade="all, delete-orphan")
    discharges = relationship("Discharge", back_populates="patient", cascade="all, delete-orphan")
    conditions = relationship("Condition", back_populates="patient", cascade="all, delete-orphan")
    observations = relationship("Observation", back_populates="patient", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="patient", cascade="all, delete-orphan")
    care_plans = relationship("CarePlan", back_populates="patient", cascade="all, delete-orphan")
    outreach_tasks = relationship("OutreachTask", back_populates="patient", cascade="all, delete-orphan")

class Encounter(Base):
    """Represents a hospital admission/inpatient stay."""
    __tablename__ = "encounters"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    encounter_type = Column(String(100), default="INPATIENT", nullable=False)
    department = Column(String(100), nullable=False)
    admit_time = Column(DateTime, nullable=False)
    discharge_time = Column(DateTime, nullable=True)
    attending_physician = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    patient = relationship("Patient", back_populates="encounters")
    discharge_record = relationship("Discharge", back_populates="encounter", uselist=False, cascade="all, delete-orphan")

class Discharge(Base):
    """Detailed discharge clinical instructions, follow-up deadlines, and disposition."""
    __tablename__ = "discharges"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_id = Column(String(36), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    discharge_time = Column(DateTime, nullable=False, index=True)
    clinical_deadline = Column(DateTime, nullable=False, index=True) # Discharge time + window
    disposition = Column(String(100), default="HOME", nullable=False)
    primary_diagnosis = Column(String(255), nullable=False)
    discharge_instructions = Column(Text, nullable=False)
    red_flag_warnings = Column(JSON, default=list, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    patient = relationship("Patient", back_populates="discharges")
    encounter = relationship("Encounter", back_populates="discharge_record")

class Condition(Base):
    """Patient active conditions or chronic diagnoses."""
    __tablename__ = "conditions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    icd10_code = Column(String(20), nullable=True)
    display_name = Column(String(255), nullable=False)
    clinical_status = Column(String(50), default="ACTIVE", nullable=False) # ACTIVE, RESOLVED
    verification_status = Column(String(50), default="CONFIRMED", nullable=False)

    patient = relationship("Patient", back_populates="conditions")

class Observation(Base):
    """Clinical measurements, vitals, or patient-reported symptoms."""
    __tablename__ = "observations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    code = Column(String(100), nullable=False) # e.g. "blood-pressure", "heart-rate", "pain-score"
    display_name = Column(String(255), nullable=False)
    value_string = Column(String(255), nullable=True)
    value_numeric = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    source = Column(String(50), default="AI_OUTREACH", nullable=False) # EHR, AI_OUTREACH, CLINICIAN
    observed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    patient = relationship("Patient", back_populates="observations")

class Medication(Base):
    """Prescribed medications upon discharge."""
    __tablename__ = "medications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False)
    dosage = Column(String(100), nullable=False)
    frequency = Column(String(100), nullable=False)
    instructions = Column(Text, nullable=True)

    patient = relationship("Patient", back_populates="medications")

class CarePlan(Base):
    """Post-discharge recovery guidelines and follow-up activities."""
    __tablename__ = "care_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    goals = Column(JSON, default=list, nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False)

    patient = relationship("Patient", back_populates="care_plans")
