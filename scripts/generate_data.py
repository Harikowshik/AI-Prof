import sys
import json
import random
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone, timedelta
from backend.app.core.database import SessionLocal
from backend.app.models.tenant import Hospital
from backend.app.models.healthcare import (
    Patient, Encounter, Discharge, Condition, Observation, Medication, CarePlan
)
from backend.app.models.campaign import Campaign
from backend.app.models.queue import OutreachTask

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Donald", "Sandra", "Steven", "Ashley",
    "Paul", "Kimberly", "Andrew", "Emily", "Joshua", "Donna", "Kenneth", "Michelle",
    "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa", "Edward", "Deborah"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker"
]

CLINICAL_DEPARTMENTS = ["CARDIOLOGY", "GENERAL_SURGERY", "ORTHOPEDIC", "PULMONARY"]

CONDITIONS_MAP = {
    "CARDIOLOGY": [
        ("I50.9", "Congestive Heart Failure, unspecified", "HIGH"),
        ("I21.9", "Acute Myocardial Infarction, unspecified", "URGENT"),
        ("I48.91", "Atrial Fibrillation, unspecified", "MEDIUM"),
        ("I10", "Essential (primary) Hypertension", "LOW")
    ],
    "GENERAL_SURGERY": [
        ("K35.80", "Acute appendicitis with localized peritonitis", "MEDIUM"),
        ("K80.00", "Calculus of gallbladder with acute cholecystitis", "MEDIUM"),
        ("K40.90", "Unilateral inguinal hernia, without obstruction", "LOW"),
        ("T81.4XXA", "Infection following a procedure, initial encounter", "URGENT")
    ],
    "ORTHOPEDIC": [
        ("M16.11", "Unilateral primary osteoarthritis, right hip", "MEDIUM"),
        ("M17.11", "Unilateral primary osteoarthritis, right knee", "MEDIUM"),
        ("S72.001A", "Fracture of head of right femur", "HIGH"),
        ("I82.401", "Acute deep vein thrombosis of right lower extremity", "URGENT")
    ],
    "PULMONARY": [
        ("J44.1", "Chronic obstructive pulmonary disease with acute exacerbation", "HIGH"),
        ("J18.9", "Pneumonia, unspecified organism", "MEDIUM"),
        ("J45.901", "Unspecified asthma with acute exacerbation", "HIGH")
    ]
}

MEDICATIONS_MAP = {
    "CARDIOLOGY": [
        ("Carvedilol", "12.5 mg", "Twice daily with meals"),
        ("Lisinopril", "10 mg", "Once daily in the morning"),
        ("Furosemide", "40 mg", "Once daily, report sudden weight shifts")
    ],
    "GENERAL_SURGERY": [
        ("Amoxicillin-Clavulanate", "875 mg", "Every 12 hours for 7 days"),
        ("Acetaminophen", "500 mg", "Every 6 hours as needed for surgical tenderness"),
        ("Docusate Sodium", "100 mg", "Twice daily to prevent constipation")
    ],
    "ORTHOPEDIC": [
        ("Enoxaparin (Lovenox)", "40 mg", "Subcutaneously once daily for DVT prophylaxis"),
        ("Celecoxib", "200 mg", "Once daily with food"),
        ("Oxycodone", "5 mg", "Every 4 to 6 hours strictly for severe pain")
    ],
    "PULMONARY": [
        ("Albuterol Inhaler", "90 mcg", "2 puffs every 4 to 6 hours as needed for wheezing"),
        ("Prednisone", "20 mg", "Once daily tapering over 5 days"),
        ("Azithromycin", "250 mg", "Once daily")
    ]
}

def generate_synthetic_data(total_patients: int = 250):
    db = SessionLocal()
    try:
        existing_patients = db.query(Patient).count()
        if existing_patients > 0:
            print(f"Synthetic patients already present ({existing_patients}). Skipping generation.")
            return

        print(f"Generating {total_patients} synthetic patient records across all hospitals...")
        hospitals = db.query(Hospital).all()
        if not hospitals:
            print("Error: No hospitals found. Run scripts/seed.py first.")
            return

        now = datetime.now(timezone.utc)
        all_patient_json_feed = []

        # Track St. Jude campaign for auto-generating initial queue tasks
        st_jude = next((h for h in hospitals if h.slug == "st-jude"), hospitals[0])
        st_jude_cardio_camp = db.query(Campaign).filter(
            Campaign.hospital_id == st_jude.id,
            Campaign.target_condition_or_dept == "CARDIOLOGY"
        ).first()

        created_patients = 0
        queue_simulation_records = []

        for i in range(total_patients):
            hospital = random.choice(hospitals)
            dept = random.choice(CLINICAL_DEPARTMENTS)
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            gender = random.choice(["Male", "Female"])
            dob_year = random.randint(1940, 2003)
            dob_month = random.randint(1, 12)
            dob_day = random.randint(1, 28)
            dob = f"{dob_year:04d}-{dob_month:02d}-{dob_day:02d}"
            mrn = f"MRN-{hospital.slug[:3].upper()}-{10000 + i}"
            phone = f"+1-555-{random.randint(100, 999):03d}-{random.randint(1000, 9999):04d}"
            
            # Clinical risk distribution: 40% Medium, 30% Low, 20% High, 10% Urgent
            risk_tier = random.choices(["LOW", "MEDIUM", "HIGH", "URGENT"], weights=[0.30, 0.40, 0.20, 0.10])[0]

            # Discharge time: between 4 hours ago and 70 hours ago
            hours_ago = random.uniform(4, 70)
            discharge_time = now - timedelta(hours=hours_ago)
            admit_time = discharge_time - timedelta(days=random.randint(2, 6))
            
            # Clinical follow-up window (e.g., 48 hours from discharge)
            clinical_deadline = discharge_time + timedelta(hours=hospital.clinical_window_hours)

            # Persist Patient
            patient = Patient(
                hospital_id=hospital.id,
                mrn=mrn,
                first_name=first_name,
                last_name=last_name,
                date_of_birth=dob,
                gender=gender,
                phone_number=phone,
                email=f"{first_name.lower()}.{last_name.lower()}@synthetic-mail.test",
                communication_preference=random.choices(["PHONE", "SMS"], weights=[0.85, 0.15])[0],
                consent_granted=random.choices([True, False], weights=[0.95, 0.05])[0],
                clinical_risk_tier=risk_tier
            )
            db.add(patient)
            db.flush()

            # Persist Encounter
            encounter = Encounter(
                hospital_id=hospital.id,
                patient_id=patient.id,
                encounter_type="INPATIENT",
                department=dept,
                admit_time=admit_time,
                discharge_time=discharge_time,
                attending_physician=f"Dr. {random.choice(LAST_NAMES)}, MD"
            )
            db.add(encounter)
            db.flush()

            # Conditions
            cond_choices = CONDITIONS_MAP.get(dept, CONDITIONS_MAP["GENERAL_SURGERY"])
            cond_info = random.choice(cond_choices)
            condition = Condition(
                hospital_id=hospital.id,
                patient_id=patient.id,
                icd10_code=cond_info[0],
                display_name=cond_info[1],
                clinical_status="ACTIVE",
                verification_status="CONFIRMED"
            )
            db.add(condition)

            # Discharge record
            discharge = Discharge(
                hospital_id=hospital.id,
                encounter_id=encounter.id,
                patient_id=patient.id,
                discharge_time=discharge_time,
                clinical_deadline=clinical_deadline,
                disposition="HOME",
                primary_diagnosis=cond_info[1],
                discharge_instructions=f"Follow low sodium diet. Ambulate 15 min twice daily. Call clinical outreach if chest discomfort or wound changes occur.",
                red_flag_warnings=["Fever > 101.5", "Shortness of breath at rest", "Chest pain"]
            )
            db.add(discharge)

            # Medications
            for med in MEDICATIONS_MAP.get(dept, []):
                medication = Medication(
                    hospital_id=hospital.id,
                    patient_id=patient.id,
                    name=med[0],
                    dosage=med[1],
                    frequency=med[2],
                    instructions=med[2]
                )
                db.add(medication)

            # Baseline Observation
            obs = Observation(
                hospital_id=hospital.id,
                patient_id=patient.id,
                code="systolic-bp",
                display_name="Discharge Systolic Blood Pressure",
                value_numeric=float(random.randint(110, 160)),
                unit="mmHg",
                source="EHR",
                observed_at=discharge_time
            )
            db.add(obs)

            # If patient is St. Jude Cardiology, create an initial queue task to populate the queue simulation dataset
            if hospital.id == st_jude.id and dept == "CARDIOLOGY" and st_jude_cardio_camp and len(queue_simulation_records) < 30:
                task = OutreachTask(
                    hospital_id=st_jude.id,
                    patient_id=patient.id,
                    campaign_id=st_jude_cardio_camp.id,
                    status="PENDING",
                    computed_priority=0.5,
                    risk_score=1.0 if risk_tier == "URGENT" else (0.8 if risk_tier == "HIGH" else (0.5 if risk_tier == "MEDIUM" else 0.25)),
                    deadline_urgency=0.6,
                    clinical_deadline=clinical_deadline,
                    attempt_count=0,
                    max_retries=3
                )
                db.add(task)
                queue_simulation_records.append({
                    "patient_id": patient.id,
                    "mrn": mrn,
                    "name": f"{first_name} {last_name}",
                    "risk_tier": risk_tier,
                    "discharge_time": discharge_time.isoformat(),
                    "clinical_deadline": clinical_deadline.isoformat(),
                    "hours_until_deadline": round((clinical_deadline - now).total_seconds() / 3600.0, 1)
                })

            created_patients += 1

            all_patient_json_feed.append({
                "mrn": mrn,
                "hospital_slug": hospital.slug,
                "first_name": first_name,
                "last_name": last_name,
                "date_of_birth": dob,
                "gender": gender,
                "phone": phone,
                "department": dept,
                "discharge_timestamp": discharge_time.isoformat(),
                "primary_diagnosis": cond_info[1],
                "clinical_risk_tier": risk_tier,
                "communication_preference": patient.communication_preference,
                "consent_granted": patient.consent_granted
            })

        db.commit()
        print(f"Successfully generated and committed {created_patients} synthetic patient records.")

        # Save synthetic feed to data/synthetic_patients/discharge_feed.json
        data_dir = Path("data/synthetic_patients")
        data_dir.mkdir(parents=True, exist_ok=True)
        feed_path = data_dir / "discharge_feed.json"
        with open(feed_path, "w", encoding="utf-8") as f:
            json.dump(all_patient_json_feed, f, indent=2)
        print(f"Saved discharge ingestion feed to {feed_path}")

        # Save 25-30 patient queue simulation dataset to data/queue_simulation/simulation_tasks.json
        q_dir = Path("data/queue_simulation")
        q_dir.mkdir(parents=True, exist_ok=True)
        q_path = q_dir / "simulation_tasks.json"
        with open(q_path, "w", encoding="utf-8") as f:
            json.dump(queue_simulation_records, f, indent=2)
        print(f"Saved queue simulation dataset ({len(queue_simulation_records)} tasks) to {q_path}")

    finally:
        db.close()

if __name__ == "__main__":
    generate_synthetic_data(total_patients=250)
