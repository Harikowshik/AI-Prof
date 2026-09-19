import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone, timedelta
from backend.app.core.database import SessionLocal
from backend.app.core.security import get_password_hash
from backend.app.models.tenant import Hospital, HospitalCapacity, User
from backend.app.models.campaign import Campaign
from scripts.seed_protocols import seed_protocols

def seed_database():
    db = SessionLocal()
    try:
        print("Starting system seed process...")
        
        # 1. Seed Hospital Tenants
        hospitals_data = [
            {
                "name": "St. Jude Hospital",
                "slug": "st-jude",
                "contact_email": "ops@stjude.health",
                "phone_number": "+1-800-555-0101",
                "timezone": "America/New_York",
                "calling_hours_start": 8,
                "calling_hours_end": 20,
                "max_concurrent_calls": 10,
                "clinical_window_hours": 48,
                "status": "READY"
            },
            {
                "name": "Metro General Hospital",
                "slug": "metro-general",
                "contact_email": "ops@metro.health",
                "phone_number": "+1-800-555-0202",
                "timezone": "America/Chicago",
                "calling_hours_start": 8,
                "calling_hours_end": 20,
                "max_concurrent_calls": 8,
                "clinical_window_hours": 48,
                "status": "READY"
            },
            {
                "name": "Pine Valley Medical",
                "slug": "pine-valley",
                "contact_email": "ops@pinevalley.health",
                "phone_number": "+1-800-555-0303",
                "timezone": "America/Los_Angeles",
                "calling_hours_start": 9,
                "calling_hours_end": 19,
                "max_concurrent_calls": 5,
                "clinical_window_hours": 72,
                "status": "READY"
            }
        ]

        hospitals = {}
        for h_info in hospitals_data:
            existing = db.query(Hospital).filter(Hospital.slug == h_info["slug"]).first()
            if not existing:
                h = Hospital(**h_info)
                db.add(h)
                db.flush()
                # Create corresponding capacity record
                cap = HospitalCapacity(
                    hospital_id=h.id,
                    current_active_calls=0,
                    max_capacity=h.max_concurrent_calls
                )
                db.add(cap)
                hospitals[h.slug] = h
                print(f"Created hospital: {h.name} (ID: {h.id})")
            else:
                hospitals[h_info["slug"]] = existing

        db.commit()

        # 2. Seed Users across 4-tier RBAC
        users_data = [
            # Platform Admin (Global, no tenant scoping required)
            {
                "email": "admin@platform.health",
                "full_name": "Sarah Connor (Platform Admin)",
                "password": "PlatformAdmin123!",
                "role": "PLATFORM_ADMIN",
                "hospital_id": None
            },
            # St. Jude Users
            {
                "email": "admin@stjude.health",
                "full_name": "Marcus Vance (Hospital Admin)",
                "password": "HospitalAdmin123!",
                "role": "HOSPITAL_ADMIN",
                "hospital_id": hospitals["st-jude"].id
            },
            {
                "email": "campaigns@stjude.health",
                "full_name": "Elena Rostova (Campaign Manager)",
                "password": "CampaignMgr123!",
                "role": "CAMPAIGN_MANAGER",
                "hospital_id": hospitals["st-jude"].id
            },
            {
                "email": "dr.chen@stjude.health",
                "full_name": "Dr. David Chen, MD (Clinical Reviewer)",
                "password": "ClinicalRev123!",
                "role": "CLINICAL_REVIEWER",
                "hospital_id": hospitals["st-jude"].id
            },
            # Metro General Users
            {
                "email": "admin@metro.health",
                "full_name": "Rachel Zane (Metro Hospital Admin)",
                "password": "HospitalAdmin123!",
                "role": "HOSPITAL_ADMIN",
                "hospital_id": hospitals["metro-general"].id
            },
            {
                "email": "dr.patel@metro.health",
                "full_name": "Dr. Ananya Patel, MD (Metro Reviewer)",
                "password": "ClinicalRev123!",
                "role": "CLINICAL_REVIEWER",
                "hospital_id": hospitals["metro-general"].id
            }
        ]

        for u_info in users_data:
            existing = db.query(User).filter(User.email == u_info["email"]).first()
            if not existing:
                u = User(
                    email=u_info["email"],
                    full_name=u_info["full_name"],
                    hashed_password=get_password_hash(u_info["password"]),
                    role=u_info["role"],
                    hospital_id=u_info["hospital_id"]
                )
                db.add(u)
                print(f"Created user: {u.email} [{u.role}]")

        db.commit()

        # 3. Seed Protocols
        seed_protocols()

        # 4. Seed Campaigns
        campaigns_data = [
            {
                "hospital_id": hospitals["st-jude"].id,
                "name": "Cardiology Post-Discharge 48h Outreach",
                "description": "High-priority clinical follow-up for CHF and Acute Coronary patients within 48 hours of discharge.",
                "target_condition_or_dept": "CARDIOLOGY",
                "clinical_window_hours": 48,
                "calling_hours_start": 8,
                "calling_hours_end": 20,
                "max_retries": 3,
                "campaign_priority_weight": 0.85,
                "eligibility_rules": {"min_age": 18, "required_department": "CARDIOLOGY"},
                "status": "RUNNING",
                "start_date": datetime.now(timezone.utc) - timedelta(days=1),
                "end_date": datetime.now(timezone.utc) + timedelta(days=30)
            },
            {
                "hospital_id": hospitals["st-jude"].id,
                "name": "General Surgery Post-Op Wound Surveillance",
                "description": "Surveillance of surgical incisions to detect early surgical site infections and prevent readmission.",
                "target_condition_or_dept": "GENERAL_SURGERY",
                "clinical_window_hours": 72,
                "calling_hours_start": 9,
                "calling_hours_end": 19,
                "max_retries": 3,
                "campaign_priority_weight": 0.65,
                "eligibility_rules": {"min_age": 18, "required_department": "GENERAL_SURGERY"},
                "status": "READY",
                "start_date": datetime.now(timezone.utc),
                "end_date": datetime.now(timezone.utc) + timedelta(days=60)
            },
            {
                "hospital_id": hospitals["metro-general"].id,
                "name": "Orthopedic Total Joint Recovery Outreach",
                "description": "Post-discharge mobilization, DVT prophylaxis adherence, and pain management surveillance.",
                "target_condition_or_dept": "ORTHOPEDIC",
                "clinical_window_hours": 48,
                "calling_hours_start": 8,
                "calling_hours_end": 20,
                "max_retries": 3,
                "campaign_priority_weight": 0.75,
                "eligibility_rules": {"min_age": 18, "required_department": "ORTHOPEDIC"},
                "status": "RUNNING",
                "start_date": datetime.now(timezone.utc) - timedelta(days=2),
                "end_date": datetime.now(timezone.utc) + timedelta(days=45)
            }
        ]

        for c_info in campaigns_data:
            existing = db.query(Campaign).filter(
                Campaign.hospital_id == c_info["hospital_id"],
                Campaign.name == c_info["name"]
            ).first()
            if not existing:
                c = Campaign(**c_info)
                db.add(c)
                print(f"Created campaign: {c.name} (Status: {c.status})")

        db.commit()
        print("System seed complete!")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
