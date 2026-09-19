from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import verify_password, create_access_token
from backend.app.api.deps import get_current_user
from backend.app.models.tenant import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

from fastapi import Request
from backend.app.models.tenant import Hospital

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str
    hospital_id: Optional[str] = None
    hospital_name: Optional[str] = None

class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    hospital_id: Optional[str] = None
    hospital_name: Optional[str] = None

@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    db: Session = Depends(get_db)
):
    """Authenticate via JSON body or OAuth2 form-data and return JWT."""
    content_type = request.headers.get("content-type", "").lower()
    username = ""
    password = ""
    
    if "application/json" in content_type:
        body = await request.json()
        username = body.get("email") or body.get("username", "")
        password = body.get("password", "")
    else:
        form = await request.form()
        username = str(form.get("username") or form.get("email") or "")
        password = str(form.get("password") or "")

    user = db.query(User).filter(User.email == username.strip().lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")
    
    access_token = create_access_token(
        subject=user.id,
        hospital_id=user.hospital_id,
        role=user.role
    )
    
    hospital_name = None
    if user.hospital_id:
        hosp = db.query(Hospital).filter(Hospital.id == user.hospital_id).first()
        if hosp:
            hospital_name = hosp.name

    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        hospital_id=user.hospital_id,
        hospital_name=hospital_name
    )

@router.post("/login-json", response_model=TokenResponse)
def login_json(
    req: LoginRequest,
    db: Session = Depends(get_db)
):
    """Authenticate via JSON payload and return JWT."""
    user = db.query(User).filter(User.email == req.email.strip().lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")
    
    access_token = create_access_token(
        subject=user.id,
        hospital_id=user.hospital_id,
        role=user.role
    )

    hospital_name = None
    if user.hospital_id:
        hosp = db.query(Hospital).filter(Hospital.id == user.hospital_id).first()
        if hosp:
            hospital_name = hosp.name

    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        hospital_id=user.hospital_id,
        hospital_name=hospital_name
    )

@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """Returns the authenticated user's profile and active permissions."""
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        hospital_id=current_user.hospital_id
    )
