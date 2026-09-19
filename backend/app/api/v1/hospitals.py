from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.deps import get_current_user, require_role, get_tenant_context
from backend.app.core.tenants import TenantContext
from backend.app.models.tenant import Hospital, HospitalCapacity, User

router = APIRouter(prefix="/hospitals", tags=["Hospitals & Tenants"])

class HospitalConfigUpdate(BaseModel):
    calling_hours_start: Optional[int] = None
    calling_hours_end: Optional[int] = None
    max_concurrent_calls: Optional[int] = None
    max_retries: Optional[int] = None
    clinical_window_hours: Optional[int] = None
    escalation_timeout_minutes: Optional[int] = None
    status: Optional[str] = None

class HospitalCreate(BaseModel):
    name: str
    slug: str
    contact_email: str
    phone_number: Optional[str] = None
    timezone: str = "America/New_York"
    calling_hours_start: int = 8
    calling_hours_end: int = 20
    max_concurrent_calls: int = 10
    max_retries: int = 3
    clinical_window_hours: int = 48

class HospitalResponse(BaseModel):
    id: str
    name: str
    slug: str
    contact_email: str
    phone_number: Optional[str]
    timezone: str
    calling_hours_start: int
    calling_hours_end: int
    max_concurrent_calls: int
    max_retries: int
    clinical_window_hours: int
    escalation_timeout_minutes: int
    status: str
    current_active_calls: Optional[int] = 0

    class Config:
        from_attributes = True

@router.get("", response_model=List[HospitalResponse])
def list_hospitals(
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List hospitals:
    - Platform Admin sees all hospitals.
    - Hospital users ONLY see their own hospital.
    """
    if tenant_ctx.is_platform_admin:
        hospitals = db.query(Hospital).all()
    else:
        hospitals = db.query(Hospital).filter(Hospital.id == tenant_ctx.hospital_id).all()
    
    res = []
    for h in hospitals:
        cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == h.id).first()
        active_count = cap.current_active_calls if cap else 0
        h_dict = {c.name: getattr(h, c.name) for c in h.__table__.columns}
        h_dict["current_active_calls"] = active_count
        res.append(HospitalResponse(**h_dict))
    return res

@router.get("/{hospital_id}", response_model=HospitalResponse)
def get_hospital(
    hospital_id: str,
    db: Session = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Get hospital configuration with tenant isolation check."""
    tenant_ctx.validate_tenant_access(hospital_id)
    h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Hospital not found")
    
    cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == h.id).first()
    active_count = cap.current_active_calls if cap else 0
    h_dict = {c.name: getattr(h, c.name) for c in h.__table__.columns}
    h_dict["current_active_calls"] = active_count
    return HospitalResponse(**h_dict)

@router.post("", response_model=HospitalResponse, status_code=status.HTTP_201_CREATED)
def create_hospital(
    req: HospitalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN"]))
):
    """Onboard a new hospital tenant (Platform Admin only)."""
    existing = db.query(Hospital).filter(Hospital.slug == req.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Hospital slug '{req.slug}' already exists")
    
    h = Hospital(**req.model_dump(), status="READY")
    db.add(h)
    db.flush()
    
    # Initialize capacity
    cap = HospitalCapacity(
        hospital_id=h.id,
        current_active_calls=0,
        max_capacity=h.max_concurrent_calls
    )
    db.add(cap)
    db.commit()
    db.refresh(h)
    
    h_dict = {c.name: getattr(h, c.name) for c in h.__table__.columns}
    h_dict["current_active_calls"] = 0
    return HospitalResponse(**h_dict)

@router.patch("/{hospital_id}", response_model=HospitalResponse)
def update_hospital_configuration(
    hospital_id: str,
    req: HospitalConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["PLATFORM_ADMIN", "HOSPITAL_ADMIN"])),
    tenant_ctx: TenantContext = Depends(get_tenant_context)
):
    """Update hospital operational settings and capacity limit."""
    tenant_ctx.validate_tenant_access(hospital_id)
    h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Hospital not found")
    
    update_data = req.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(h, field, val)
        if field == "max_concurrent_calls":
            cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == h.id).first()
            if cap:
                cap.max_capacity = val
                
    db.commit()
    db.refresh(h)
    
    cap = db.query(HospitalCapacity).filter(HospitalCapacity.hospital_id == h.id).first()
    h_dict = {c.name: getattr(h, c.name) for c in h.__table__.columns}
    h_dict["current_active_calls"] = cap.current_active_calls if cap else 0
    return HospitalResponse(**h_dict)
