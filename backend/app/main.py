import time
import uuid
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.database import engine, Base
import backend.app.models

# Import API routers
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.hospitals import router as hospitals_router
from backend.app.api.v1.patients import router as patients_router
from backend.app.api.v1.ingestion import router as ingestion_router
from backend.app.api.v1.campaigns import router as campaigns_router
from backend.app.api.v1.queue import router as queue_router
from backend.app.api.v1.calls import router as calls_router
from backend.app.api.v1.protocols import router as protocols_router
from backend.app.api.v1.ai import router as ai_router
from backend.app.api.v1.escalations import router as escalations_router
from backend.app.api.v1.ehr import router as ehr_router
from backend.app.api.v1.analytics import router as analytics_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.notifications import router as notifications_router
from backend.app.api.v1.health import router as health_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous AI-Powered Patient Follow-Up, Clinical Triage & Hospital Outreach Operations Platform (PRD v2.0)",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for Next.js (Netlify) and local dev
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_allow_all_origins = not _cors_origins or _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all_origins else _cors_origins,
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Observability middleware: attaches correlation ID and measures request latency
@app.middleware("http")
async def correlation_and_timing_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000.0
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Response-Time-Ms"] = f"{process_time:.2f}"
    return response

# Standardized Error Response Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "correlation_id": correlation_id
            }
        }
    )

# Mount Routers
api_v1 = settings.API_V1_STR
app.include_router(health_router, prefix=api_v1)
app.include_router(auth_router, prefix=api_v1)
app.include_router(hospitals_router, prefix=api_v1)
app.include_router(patients_router, prefix=api_v1)
app.include_router(ingestion_router, prefix=api_v1)
app.include_router(campaigns_router, prefix=api_v1)
app.include_router(queue_router, prefix=api_v1)
app.include_router(calls_router, prefix=api_v1)
app.include_router(protocols_router, prefix=api_v1)
app.include_router(ai_router, prefix=api_v1)
app.include_router(escalations_router, prefix=api_v1)
app.include_router(ehr_router, prefix=api_v1)
app.include_router(analytics_router, prefix=api_v1)
app.include_router(audit_router, prefix=api_v1)
app.include_router(notifications_router, prefix=api_v1)

@app.get("/")
def root():
    return {
        "platform": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "OPERATIONAL",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }
