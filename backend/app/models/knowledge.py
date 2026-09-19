import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class ProtocolDocument(Base):
    """Hospital clinical guideline / red-flag protocol document."""
    __tablename__ = "protocol_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    protocol_type = Column(String(100), nullable=False) # e.g. CARDIOLOGY, ORTHOPEDIC, GENERAL_SURGERY
    version = Column(String(20), default="1.0", nullable=False)
    source = Column(String(255), nullable=False) # e.g. "Hospital Clinical Governance Board"
    content = Column(Text, nullable=False)
    effective_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    hospital = relationship("Hospital", back_populates="protocols")
    chunks = relationship("ProtocolChunk", back_populates="protocol", cascade="all, delete-orphan")

class ProtocolChunk(Base):
    """Chunked protocol sections with vector embeddings for tenant-isolated RAG."""
    __tablename__ = "protocol_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    protocol_id = Column(String(36), ForeignKey("protocol_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(String(36), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    
    chunk_index = Column(Integer, nullable=False)
    section_title = Column(String(255), nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding_json = Column(JSON, nullable=True) # Stored vector embedding list[float]
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    protocol = relationship("ProtocolDocument", back_populates="chunks")
