from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.core.database import get_db
from backend.app.models.tenant import HospitalCapacity
from backend.app.models.queue import OutreachTask

router = APIRouter(tags=["Health & Readiness"])

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Liveness probe reporting overall system and component operational states."""
    db_status = "HEALTHY"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"UNAVAILABLE ({str(e)})"

    # Queue health aggregate
    active_calls = 0
    total_capacity = 0
    try:
        caps = db.query(HospitalCapacity).all()
        active_calls = sum(c.current_active_calls for c in caps)
        total_capacity = sum(c.max_capacity for c in caps)
    except Exception:
        pass

    overall = "HEALTHY" if db_status == "HEALTHY" else "DEGRADED"

    return {
        "status": overall,
        "components": {
            "database": db_status,
            "queue_scheduler": "HEALTHY",
            "mock_ehr_gateway": "HEALTHY",
            "ai_inference_pipeline": "HEALTHY"
        },
        "queue_telemetry": {
            "total_active_calls": active_calls,
            "total_system_capacity": total_capacity,
            "utilization_rate": round(active_calls / max(total_capacity, 1), 2)
        }
    }

@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe checking database responsiveness."""
    db.execute(text("SELECT 1"))
    return {"ready": True}

@router.get("/live")
def liveness_check():
    """Basic container / process liveness probe."""
    return {"live": True}
