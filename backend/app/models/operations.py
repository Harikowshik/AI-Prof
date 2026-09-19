import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON, Float
from backend.app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class AuditEvent(Base):
    """Append-only audit trail capturing state changes, clinical reviews, and tool invocations."""
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True) # e.g. TASK, CAMPAIGN, ESCALATION, EHR
    entity_id = Column(String(36), nullable=False, index=True)
    
    old_state = Column(JSON, nullable=True)
    new_state = Column(JSON, nullable=True)
    reason = Column(String(255), nullable=True)
    correlation_id = Column(String(100), nullable=True, index=True)
    
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

class NotificationRecord(Base):
    """Internal notifications for clinical reviewers, campaign managers, and supervisors."""
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), nullable=False, index=True)
    recipient_role = Column(String(50), nullable=False, index=True)
    recipient_id = Column(String(36), nullable=True)
    
    notification_type = Column(String(100), nullable=False) # ESCALATION_CREATED, MAX_RETRIES_REACHED, REVIEWER_TIMEOUT
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(50), default="INFO", nullable=False) # INFO, WARNING, CRITICAL
    
    status = Column(String(50), default="PENDING", nullable=False) # PENDING, DELIVERED, READ
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class AIUsageRecord(Base):
    """Telemetry logging for all AI agent and LLM invocations."""
    __tablename__ = "ai_usage_records"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), nullable=True, index=True)
    agent_name = Column(String(100), nullable=False, index=True) # VoiceIntake, TriageAgent, AssessmentA, AssessmentB, DocAgent
    model_name = Column(String(100), nullable=False)
    request_purpose = Column(String(255), nullable=False)
    
    latency_ms = Column(Float, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
    cost_estimate = Column(Float, default=0.0, nullable=False)
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
