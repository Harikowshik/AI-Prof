from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import User
from backend.app.models.knowledge import ProtocolDocument, ProtocolChunk
from backend.app.rag.retriever import ProtocolRetriever

router = APIRouter(prefix="/protocols", tags=["Hospital Protocols & Knowledge"])

from datetime import datetime, timezone

class ProtocolChunkResponse(BaseModel):
    id: str
    chunk_index: int
    topic: str
    content: str
    red_flags: List[str] = []

class ProtocolResponse(BaseModel):
    id: str
    hospital_id: str
    title: str
    protocol_type: str
    specialty: str
    version: str
    source: str
    content: str
    description: Optional[str] = None
    effective_date: str
    created_at: str
    chunks: List[ProtocolChunkResponse] = []

@router.get("", response_model=List[ProtocolResponse])
def list_protocols(
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Lists clinical protocols strictly scoped to caller's hospital."""
    query = db.query(ProtocolDocument)
    if not tenant_ctx.is_platform_admin:
        query = query.filter(ProtocolDocument.hospital_id == tenant_ctx.hospital_id)
    elif tenant_ctx.hospital_id:
        query = query.filter(ProtocolDocument.hospital_id == tenant_ctx.hospital_id)

    docs = query.all()
    res = []
    for d in docs:
        chunk_list = []
        for c in (d.chunks or []):
            flags = []
            t_lower = c.chunk_text.lower()
            if "chest pain" in t_lower or "pressure" in t_lower:
                flags.append("Substernal Chest Pain / Pressure")
            if "shortness of breath" in t_lower or "dyspnea" in t_lower:
                flags.append("Severe Dyspnea at Rest")
            if "weight gain" in t_lower:
                flags.append("Rapid Fluid Retention (>3 lbs / 24h)")
            if "fever" in t_lower or "temperature" in t_lower:
                flags.append("Post-Op Temperature > 101 F")
            if "purulent" in t_lower or "drainage" in t_lower:
                flags.append("Purulent Incisional Drainage")
            if "swelling" in t_lower or "dvt" in t_lower or "calf" in t_lower:
                flags.append("Unilateral Lower Extremity Edema / DVT")
            if "dizziness" in t_lower or "syncope" in t_lower:
                flags.append("Syncope or Severe Hypotension")
            if "medication" in t_lower or "dose" in t_lower:
                flags.append("Critical Medication Non-Adherence")

            chunk_list.append(ProtocolChunkResponse(
                id=c.id,
                chunk_index=c.chunk_index,
                topic=c.section_title,
                content=c.chunk_text,
                red_flags=flags
            ))

        spec = d.protocol_type.replace("_", " ").title()
        c_at = d.created_at.isoformat() if hasattr(d, 'created_at') and d.created_at else (d.effective_date.isoformat() if d.effective_date else datetime.now(timezone.utc).isoformat())

        res.append(ProtocolResponse(
            id=d.id,
            hospital_id=d.hospital_id,
            title=d.title,
            protocol_type=d.protocol_type,
            specialty=spec,
            version=d.version,
            source=d.source,
            content=d.content,
            description=f"Evidence-based {spec.lower()} post-discharge monitoring and red flag triage guideline.",
            effective_date=d.effective_date.isoformat() if d.effective_date else c_at,
            created_at=c_at,
            chunks=chunk_list
        ))
    return res

@router.get("/search")
def search_protocols(
    query: str,
    top_k: int = 3,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Tenant-isolated semantic search for hospital protocol chunks."""
    target_hospital_id = tenant_ctx.hospital_id
    if not target_hospital_id:
        h = db.query(ProtocolDocument).first()
        target_hospital_id = h.hospital_id if h else None

    return ProtocolRetriever.search_protocol_chunks(
        db=db,
        hospital_id=target_hospital_id,
        query=query,
        top_k=top_k
    )
