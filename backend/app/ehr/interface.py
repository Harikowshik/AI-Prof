from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class EHRService(ABC):
    """
    Abstract EHR Interface.
    Allows substituting mock implementation with a real Epic/Cerner FHIR connector in future.
    """

    @abstractmethod
    def get_patient(self, hospital_id: str, patient_id: str) -> Dict[str, Any]:
        """Fetch patient demographics and identity from EHR."""
        pass

    @abstractmethod
    def record_communication(
        self,
        hospital_id: str,
        patient_id: str,
        communication_type: str,
        summary: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Writes a verified communication / interaction event to EHR."""
        pass

    @abstractmethod
    def create_observation(
        self,
        hospital_id: str,
        patient_id: str,
        code: str,
        display_name: str,
        value: Any,
        unit: Optional[str] = None
    ) -> Dict[str, Any]:
        """Writes a patient-reported clinical observation to EHR."""
        pass

    @abstractmethod
    def create_followup_task(
        self,
        hospital_id: str,
        patient_id: str,
        title: str,
        description: str,
        priority: str = "ROUTINE"
    ) -> Dict[str, Any]:
        """Creates a pending clinical follow-up task in EHR worklist."""
        pass
