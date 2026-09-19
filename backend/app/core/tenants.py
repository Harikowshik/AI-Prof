from typing import Optional
from fastapi import HTTPException, status

class TenantContext:
    """Carries authenticated tenant (hospital) context throughout request or worker execution."""
    def __init__(self, hospital_id: Optional[str] = None, user_id: Optional[str] = None, role: str = "CLINICAL_REVIEWER"):
        self.hospital_id = hospital_id
        self.user_id = user_id
        self.role = role

    @property
    def is_platform_admin(self) -> bool:
        return self.role == "PLATFORM_ADMIN"

    def validate_tenant_access(self, target_hospital_id: str):
        """
        Enforces tenant boundary. Platform Admin can inspect aggregate configurations,
        but hospital users can ONLY ever access their own hospital's resources.
        """
        if self.is_platform_admin:
            return
        if not self.hospital_id or str(self.hospital_id) != str(target_hospital_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, # 404 to avoid leaking tenant resource existence
                detail="Resource not found or access denied."
            )

    def filter_query(self, query, model_hospital_id_col):
        """
        Applies tenant filter to SQLAlchemy query unless caller is platform admin.
        For patient/clinical queries, tenant filter is always strictly applied.
        """
        if self.is_platform_admin and self.hospital_id is None:
            return query
        return query.filter(model_hospital_id_col == self.hospital_id)
