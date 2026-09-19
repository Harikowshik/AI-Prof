from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session

from backend.app.models.tenant import Hospital
from backend.app.models.healthcare import Patient, Encounter, Discharge
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask

class EligibilityEvaluation:
    def __init__(self, patient_id: str, eligible: bool, reasons: List[str], discharge_id: str = None):
        self.patient_id = patient_id
        self.eligible = eligible
        self.reasons = reasons
        self.discharge_id = discharge_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "eligible": self.eligible,
            "reasons": self.reasons,
            "discharge_id": self.discharge_id
        }

def evaluate_patient_eligibility(
    db: Session,
    patient: Patient,
    campaign: Campaign
) -> EligibilityEvaluation:
    """
    Deterministic, explainable eligibility engine verifying tenant match,
    discharge timing, clinical follow-up window, communication consent, and prior outreach.
    """
    reasons = []
    
    # 1. Hospital Tenant Match
    if patient.hospital_id != campaign.hospital_id:
        return EligibilityEvaluation(patient.id, False, ["Tenant mismatch: Patient does not belong to campaign hospital."])

    # 2. Consent and Communication Eligibility
    if not patient.consent_granted:
        return EligibilityEvaluation(patient.id, False, ["Consent withheld: Patient has not granted outreach consent."])
    if not patient.phone_number:
        return EligibilityEvaluation(patient.id, False, ["Missing contact info: No valid phone number on record."])

    # 3. Find Latest Discharge Record
    latest_discharge = db.query(Discharge).filter(
        Discharge.patient_id == patient.id,
        Discharge.hospital_id == campaign.hospital_id
    ).order_by(Discharge.discharge_time.desc()).first()

    if not latest_discharge:
        return EligibilityEvaluation(patient.id, False, ["No discharge record found for patient in this hospital."])

    # 4. Department / Clinical Condition Matching
    encounter = db.query(Encounter).filter(Encounter.id == latest_discharge.encounter_id).first()
    if campaign.target_condition_or_dept != "ALL":
        if not encounter or encounter.department != campaign.target_condition_or_dept:
            return EligibilityEvaluation(
                patient.id, 
                False, 
                [f"Department mismatch: Encounter department '{getattr(encounter, 'department', 'None')}' does not match campaign target '{campaign.target_condition_or_dept}'."],
                latest_discharge.id
            )

    # 5. Clinical Follow-up Window Compliance
    now = datetime.now(timezone.utc)
    disc_time = latest_discharge.discharge_time
    if disc_time.tzinfo is None:
        disc_time = disc_time.replace(tzinfo=timezone.utc)

    window_hours = campaign.clinical_window_hours or 48
    deadline = disc_time + timedelta(hours=window_hours)
    
    # If the discharge happened more than 2x the window ago, outreach window expired
    if now > deadline + timedelta(hours=24):
        return EligibilityEvaluation(
            patient.id,
            False,
            [f"Outside clinical follow-up window: Discharge occurred {round((now - disc_time).total_seconds()/3600, 1)}h ago (window: {window_hours}h)."],
            latest_discharge.id
        )

    # 6. Existing Completed Outreach Check
    existing_completed = db.query(OutreachTask).filter(
        OutreachTask.patient_id == patient.id,
        OutreachTask.campaign_id == campaign.id,
        OutreachTask.status.in_(["COMPLETED", "ESCALATED", "MANUAL_FOLLOW_UP"])
    ).first()

    if existing_completed:
        return EligibilityEvaluation(
            patient.id,
            False,
            [f"Outreach already completed: Existing task {existing_completed.id} in terminal state '{existing_completed.status}'."],
            latest_discharge.id
        )

    # Patient passed all checks
    reasons.append("Discharge within clinical follow-up window")
    reasons.append(f"Department '{encounter.department if encounter else 'GENERAL'}' matches campaign criteria")
    reasons.append("Patient communication consent active")
    reasons.append("No prior completed outreach for this discharge encounter")
    
    return EligibilityEvaluation(patient.id, True, reasons, latest_discharge.id)

def estimate_campaign_workload(db: Session, campaign: Campaign) -> Dict[str, Any]:
    """
    Computes workload projection before campaign activation:
    - total eligible patients
    - expected call attempts (assuming ~1.4 attempts per patient)
    - active capacity utilization
    """
    patients = db.query(Patient).filter(Patient.hospital_id == campaign.hospital_id).all()
    eligible_count = 0
    ineligible_count = 0
    
    for p in patients:
        eval_res = evaluate_patient_eligibility(db, p, campaign)
        if eval_res.eligible:
            eligible_count += 1
        else:
            ineligible_count += 1
            
    expected_attempts = int(round(eligible_count * 1.4))
    hospital = db.query(Hospital).filter(Hospital.id == campaign.hospital_id).first()
    capacity = hospital.max_concurrent_calls if hospital else 10
    
    return {
        "campaign_id": campaign.id,
        "eligible_patients": eligible_count,
        "ineligible_patients": ineligible_count,
        "expected_total_attempts": expected_attempts,
        "hospital_concurrency_capacity": capacity,
        "estimated_hours_to_complete": round(expected_attempts / max(capacity * 4, 1), 1)
    }
