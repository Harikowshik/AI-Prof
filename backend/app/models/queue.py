import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class OutreachTask(Base):
    """Core operational unit representing an outbound post-discharge outreach attempt."""
    __tablename__ = "outreach_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # State Machine: PENDING, SCHEDULED, CALLING, CONNECTED, COMPLETED, NO_ANSWER, BUSY, 
    # VOICEMAIL, DROPPED, RETRY_SCHEDULED, CALLBACK_SCHEDULED, ESCALATED, MANUAL_FOLLOW_UP, FAILED
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    previous_status = Column(String(50), nullable=True)
    
    # Prioritization Components
    computed_priority = Column(Float, default=0.0, nullable=False, index=True)
    risk_score = Column(Float, default=0.5, nullable=False)
    deadline_urgency = Column(Float, default=0.0, nullable=False)
    starvation_boost = Column(Float, default=0.0, nullable=False)
    
    # Timing & Deadlines
    clinical_deadline = Column(DateTime, nullable=False, index=True)
    scheduled_for = Column(DateTime, nullable=True, index=True)
    callback_scheduled_at = Column(DateTime, nullable=True, index=True)
    callback_reason = Column(String(255), nullable=True)
    
    # Retries & Worker Lease
    attempt_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)
    worker_id = Column(String(100), nullable=True, index=True)
    heartbeat_at = Column(DateTime, nullable=True)
    
    # Context Preservation for Dropped / In-progress Calls
    conversation_stage = Column(String(50), default="NOT_STARTED", nullable=False)
    partial_transcript = Column(JSON, default=list, nullable=False)
    partial_observations = Column(JSON, default=list, nullable=False)
    answered_questions = Column(JSON, default=list, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="outreach_tasks")
    campaign = relationship("Campaign", back_populates="outreach_tasks")
    calls = relationship("CallRecord", back_populates="outreach_task", cascade="all, delete-orphan")
    escalations = relationship("EscalationRecord", back_populates="outreach_task", cascade="all, delete-orphan")

class CallRecord(Base):
    """Detailed log of a single telephone interaction attempt."""
    __tablename__ = "call_records"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    outreach_task_id = Column(String(36), ForeignKey("outreach_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    
    attempt_number = Column(Integer, default=1, nullable=False)
    # Outcomes: SUCCESSFUL, NO_ANSWER, BUSY, VOICEMAIL, DROPPED, CALLBACK_REQUESTED, ESCALATION, TECHNICAL_FAILURE
    outcome = Column(String(50), nullable=False, index=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    
    # Conversation Data
    raw_transcript = Column(JSON, default=list, nullable=False)
    scenario_id = Column(String(100), nullable=True)
    
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ended_at = Column(DateTime, nullable=True)

    outreach_task = relationship("OutreachTask", back_populates="calls")
    documentation = relationship("DocumentationRecord", back_populates="call", uselist=False, cascade="all, delete-orphan")

class EscalationRecord(Base):
    """Clinical escalation record requiring human-in-the-loop review."""
    __tablename__ = "escalation_records"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    outreach_task_id = Column(String(36), ForeignKey("outreach_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(String(36), ForeignKey("call_records.id", ondelete="CASCADE"), nullable=True)
    
    trigger_reason = Column(String(255), nullable=False)
    clinical_indicators = Column(JSON, default=list, nullable=False)
    
    # Dual Assessments & Consensus
    assessment_a = Column(JSON, default=dict, nullable=False)
    assessment_b = Column(JSON, default=dict, nullable=False)
    disagreement_detected = Column(Boolean, default=False, nullable=False)
    consensus_decision = Column(String(50), nullable=False)
    evidence_citations = Column(JSON, default=list, nullable=False)
    
    # Lifecycle: OPEN, ASSIGNED, IN_REVIEW, WAITING_FOR_INFORMATION, RESOLVED, CLOSED
    status = Column(String(50), default="OPEN", nullable=False, index=True)
    priority = Column(String(50), default="HIGH", nullable=False) # URGENT, HIGH, MEDIUM
    assigned_reviewer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    resolution_action = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    outreach_task = relationship("OutreachTask", back_populates="escalations")

class DocumentationRecord(Base):
    """Traceable clinical progress note and mock EHR synchronization payload."""
    __tablename__ = "documentation_records"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(String(36), ForeignKey("call_records.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    clinical_summary = Column(Text, nullable=False)
    patient_reported_symptoms = Column(JSON, default=list, nullable=False)
    follow_up_recommendations = Column(JSON, default=list, nullable=False)
    citations = Column(JSON, default=list, nullable=False)
    
    # EHR status: PENDING, SYNCED, FAILED
    ehr_sync_status = Column(String(50), default="PENDING", nullable=False)
    ehr_sync_error = Column(Text, nullable=True)
    ehr_sync_timestamp = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    call = relationship("CallRecord", back_populates="documentation")
