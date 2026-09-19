import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    contact_email = Column(String(255), nullable=False)
    phone_number = Column(String(50), nullable=True)
    timezone = Column(String(50), default="America/New_York", nullable=False)
    
    # Operational Settings
    calling_hours_start = Column(Integer, default=8, nullable=False) # 08:00
    calling_hours_end = Column(Integer, default=20, nullable=False)   # 20:00
    max_concurrent_calls = Column(Integer, default=10, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    clinical_window_hours = Column(Integer, default=48, nullable=False)
    escalation_timeout_minutes = Column(Integer, default=60, nullable=False)
    
    # Lifecycle: CREATED, CONFIGURED, READY, ACTIVE, SUSPENDED
    status = Column(String(50), default="CONFIGURED", nullable=False)
    config_metadata = Column(JSON, default=dict, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    users = relationship("User", back_populates="hospital", cascade="all, delete-orphan")
    capacity = relationship("HospitalCapacity", back_populates="hospital", uselist=False, cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="hospital", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="hospital", cascade="all, delete-orphan")
    protocols = relationship("ProtocolDocument", back_populates="hospital", cascade="all, delete-orphan")

class HospitalCapacity(Base):
    """Tracks atomic concurrent active calls per hospital tenant."""
    __tablename__ = "hospital_capacities"

    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), primary_key=True)
    current_active_calls = Column(Integer, default=0, nullable=False)
    max_capacity = Column(Integer, default=10, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    hospital = relationship("Hospital", back_populates="capacity")

class User(Base):
    """System and hospital personnel with 4-tier RBAC."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    # Roles: PLATFORM_ADMIN, HOSPITAL_ADMIN, CAMPAIGN_MANAGER, CLINICAL_REVIEWER
    role = Column(String(50), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    hospital = relationship("Hospital", back_populates="users")
