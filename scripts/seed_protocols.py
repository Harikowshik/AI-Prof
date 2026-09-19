import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone
from backend.app.core.database import SessionLocal
from backend.app.models.tenant import Hospital
from backend.app.models.knowledge import ProtocolDocument, ProtocolChunk

# Realistic hospital clinical protocols with red flags and triage guidelines
PROTOCOLS = [
    {
        "hospital_slug": "st-jude",
        "title": "Cardiology Post-Discharge Clinical Triage Protocol",
        "protocol_type": "CARDIOLOGY",
        "version": "2.4",
        "source": "St. Jude Heart & Vascular Clinical Governance",
        "content": """
St. Jude Cardiology Post-Discharge Clinical Outreach Guidelines

SECTION 1: MANDATORY OUTREACH TIMING & WINDOWS
All congestive heart failure (CHF) and acute coronary syndrome (ACS) patients must receive outreach within 24 to 48 hours of discharge to prevent 30-day hospital readmissions.

SECTION 2: CARDIOVASCULAR RED-FLAG SYMPTOMS (IMMEDIATE URGENT ESCALATION)
If the patient reports ANY of the following, classify as URGENT and initiate immediate clinical escalation:
1. Recurrent or worsening substernal chest pressure, tightness, or pain radiating to jaw, left shoulder, or back.
2. Sudden onset of shortness of breath at rest or paroxysmal nocturnal dyspnea (waking up gasping).
3. Sudden rapid weight gain: greater than 3 lbs in 24 hours or greater than 5 lbs in one week, accompanied by bilateral ankle swelling or pedal edema.
4. Syncope, near-syncope, severe dizziness, or systolic blood pressure < 90 mmHg or > 180 mmHg.
5. Heart palpitations with sustained tachycardia (> 110 bpm) or severe fatigue.

SECTION 3: CONCERNING SYMPTOMS (REQUIRING REVIEW WITHIN 4 HOURS)
Classify as CONCERNING if:
1. Mild exertion dyspnea that is not worse than baseline prior to admission.
2. Inability to afford or pick up discharge cardiac medications (beta blockers, ACEi/ARBs, diuretics).
3. Mild nausea or dizziness upon standing without loss of consciousness.

SECTION 4: ROUTINE RECOVERY (NO ESCALATION REQUIRED)
Classify as ROUTINE if:
1. Patient states they feel improved or same as discharge status.
2. Vitals reported in safe range (BP 110-135 / 70-85, HR 60-85).
3. Taking all prescribed medications with no missed doses.
4. Confirmed outpatient cardiology follow-up appointment within 7-14 days.
        """,
        "chunks": [
            ("Section 1: Mandatory Outreach Timing", "All CHF and ACS patients must receive outreach within 24 to 48 hours of discharge."),
            ("Section 2: Cardiovascular Red Flags", "Chest pain radiating to jaw/back, dyspnea at rest, weight gain >3 lbs in 24 hours with edema, syncope, BP <90 or >180."),
            ("Section 3: Concerning Symptoms", "Mild exertion dyspnea, difficulty obtaining cardiac meds, mild orthostatic dizziness."),
            ("Section 4: Routine Recovery Criteria", "Feeling improved, stable vitals, full medication adherence, follow-up scheduled.")
        ]
    },
    {
        "hospital_slug": "st-jude",
        "title": "General Post-Surgical Wound & Sepsis Triage Protocol",
        "protocol_type": "GENERAL_SURGERY",
        "version": "1.8",
        "source": "St. Jude Department of Surgery",
        "content": """
St. Jude Post-Surgical Recovery & Wound Infection Surveillance Protocol

SECTION 1: SURGICAL SITE INFECTION RED FLAGS (URGENT ESCALATION)
1. Purulent, foul-smelling, thick yellow or green drainage from incision.
2. Spreading erythema (redness) extending more than 2 inches from incision margins or marked wound warmth/induration.
3. Incisional wound dehiscence or separation of staples/sutures.
4. Systemic fever > 101.5°F (38.6°C) or severe shaking chills (rigors).
5. Uncontrolled acute surgical pain not responsive to prescribed analgesics.

SECTION 2: CONCERNING INDICATORS
1. Low-grade fever between 99.5°F and 100.9°F.
2. Mild serosanguinous (clear pinkish) drainage on wound dressing requiring more than 2 dressing changes per day.
3. Constipation exceeding 72 hours post-surgery while taking opioid analgesics.

SECTION 3: ROUTINE RECOVERY
1. Incision clean, intact, dry with mild expected healing tenderness.
2. Temperature normal (< 99.5°F).
3. Resumed light oral diet and normal bowel function.
        """,
        "chunks": [
            ("Section 1: Surgical Site Red Flags", "Purulent drainage, spreading erythema >2 inches, wound dehiscence, fever >101.5 F with chills, uncontrolled pain."),
            ("Section 2: Concerning Indicators", "Low-grade fever 99.5-100.9 F, increased serosanguinous drainage, constipation >72 hours on opioids."),
            ("Section 3: Routine Recovery", "Incision clean, dry, intact, afebrile, normal diet and bowel movements.")
        ]
    },
    {
        "hospital_slug": "metro-general",
        "title": "Metro General Orthopedic Total Joint Recovery Protocol",
        "protocol_type": "ORTHOPEDIC",
        "version": "3.1",
        "source": "Metro General Orthopedics Institute",
        "content": """
Metro General Orthopedic Post-Arthroplasty Clinical Protocol

SECTION 1: DEEP VEIN THROMBOSIS & PULMONARY EMBOLISM RED FLAGS (URGENT)
1. Unilateral calf pain, tenderness, severe swelling, or warmth in operative or non-operative leg.
2. Sudden chest tightness, pleuritic chest pain with deep inspiration, or sudden unexplained dyspnea (suspected PE).
3. Acute inability to bear weight after previous successful ambulation with walker/crutches.

SECTION 2: CONCERNING INDICATORS
1. Persistent drainage from joint incision beyond 5 days post-operation.
2. Numbness or tingling in operative foot/toes not improving.
3. Difficulty adhering to deep vein thrombosis chemical prophylaxis (e.g. missed doses of Lovenox, Eliquis, or Aspirin).

SECTION 3: ROUTINE
1. Gradual reduction in surgical swelling with leg elevation and icing.
2. Compliant with physical therapy exercises and ambulating safely.
3. Taking prescribed anticoagulation without bleeding complications.
        """,
        "chunks": [
            ("Section 1: DVT and PE Red Flags", "Unilateral calf swelling, pleuritic chest pain, sudden dyspnea, acute inability to bear weight."),
            ("Section 2: Concerning Indicators", "Persistent wound drainage >5 days, progressive peripheral numbness, missed anticoagulation."),
            ("Section 3: Routine Recovery", "Decreasing swelling, safe ambulation, physical therapy compliant, anticoagulant adherence.")
        ]
    }
]

def seed_protocols():
    db = SessionLocal()
    try:
        print("Seeding hospital-specific clinical protocols...")
        hospitals = {h.slug: h for h in db.query(Hospital).all()}
        
        for proto in PROTOCOLS:
            h = hospitals.get(proto["hospital_slug"])
            if not h:
                continue
            
            # Check existing
            existing = db.query(ProtocolDocument).filter(
                ProtocolDocument.hospital_id == h.id,
                ProtocolDocument.title == proto["title"]
            ).first()
            
            if not existing:
                doc = ProtocolDocument(
                    hospital_id=h.id,
                    title=proto["title"],
                    protocol_type=proto["protocol_type"],
                    version=proto["version"],
                    source=proto["source"],
                    content=proto["content"],
                    effective_date=datetime.now(timezone.utc),
                    metadata_json={"department": proto["protocol_type"]}
                )
                db.add(doc)
                db.flush()
                
                # Add chunks
                for idx, (sec_title, chunk_txt) in enumerate(proto["chunks"]):
                    # Generate simple normalized term frequency / character hash embedding representation
                    chunk = ProtocolChunk(
                        protocol_id=doc.id,
                        hospital_id=h.id,
                        chunk_index=idx,
                        section_title=sec_title,
                        chunk_text=chunk_txt,
                        embedding_json=[round(float((ord(c) % 20) / 20.0), 3) for c in (chunk_txt[:64] + " " * 64)[:64]]
                    )
                    db.add(chunk)
                print(f"  -> Added protocol: '{proto['title']}' for {h.name} (tenant {h.id})")
        
        db.commit()
        print("Protocols successfully seeded.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_protocols()
