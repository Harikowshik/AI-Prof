import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class Campaign(Base):
    """Campaign grouping patients for targeted clinical post-discharge outreach."""
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Operational & Clinical Rules
    target_condition_or_dept = Column(String(100), default="ALL", nullable=False)
    clinical_window_hours = Column(Integer, default=48, nullable=False)
    calling_hours_start = Column(Integer, default=8, nullable=False)
    calling_hours_end = Column(Integer, default=20, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    campaign_priority_weight = Column(Float, default=0.5, nullable=False) # [0.1, 1.0]
    
    # Eligibility Criteria Rules JSON (e.g. required departments, excluded flags)
    eligibility_rules = Column(JSON, default=dict, nullable=False)
    
    # Lifecycle: DRAFT, READY, SCHEDULED, RUNNING, PAUSED, COMPLETED, CANCELLED
    status = Column(String(50), default="DRAFT", nullable=False, index=True)
    
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    hospital = relationship("Hospital", back_populates="campaigns")
    outreach_tasks = relationship("OutreachTask", back_populates="campaign", cascade="all, delete-orphan")
