# Evaluator Demo Script (10-Minute Walkthrough)

## Multi-Hospital Post-Discharge Outreach Platform (PRD v2.0)

This script provides an evaluator with an exact minute-by-minute guide to verify the complete operational healthcare platform end-to-end.

---

### Demo Credentials
| Role | Username / Email | Password | Access Scope |
|---|---|---|---|
| **Platform Admin** | `admin@platform.health` | `PlatformAdmin123!` | System-wide aggregates, all hospital configurations, health metrics. No unrestricted patient PHI. |
| **Hospital Admin (St. Jude)** | `admin@stjude.health` | `HospitalAdmin123!` | St. Jude hospital configuration, staff management, protocols, patient uploads, analytics. |
| **Campaign Manager (St. Jude)** | `campaigns@stjude.health` | `CampaignMgr123!` | St. Jude campaigns, live queue table, start/pause controls, capacity monitoring. |
| **Clinical Reviewer (St. Jude)** | `dr.chen@stjude.health` | `ClinicalRev123!` | St. Jude escalation inbox, patient clinical context, AI transcripts, resolution panel. |
| **Hospital Admin (Metro General)** | `admin@metro.health` | `HospitalAdmin123!` | Metro General tenant (proves multi-tenant isolation from St. Jude). |

---

### Step-by-Step Flow (00:00 – 10:00)

#### 00:00 – 01:00: Platform Overview & Multi-Tenancy
1. Log in as **Platform Admin** (`admin@platform.health`).
2. Navigate to **Hospitals**: observe St. Jude Hospital, Metro General, and Pine Valley Medical.
3. Show that platform telemetry shows aggregate metrics without leaking patient clinical records.
4. Log out and log in as **Hospital Admin (St. Jude)** (`admin@stjude.health`).
5. Verify that Metro General data is completely invisible and unreachable.

#### 01:00 – 02:00: Hospital Configuration & Patient Discharge Ingestion
1. View Hospital Configuration: calling window (`08:00–20:00`), outbound capacity limit (`10 calls`), retry backoff rules.
2. Navigate to **Discharges**: click **Import Ingestion Feed** (select `data/synthetic_patients/discharge_feed.json` or sample CSV).
3. Observe validation, duplicate checking, and successful persistence into structured FHIR-like entities (`Patient`, `Encounter`, `Discharge`, `Condition`).

#### 02:00 – 03:00: Campaign Creation & Explainable Eligibility
1. Log in as **Campaign Manager** (`campaigns@stjude.health`).
2. Navigate to **Campaigns** $\to$ select "Cardiology Post-Discharge 48h Outreach".
3. Run **Evaluate Eligibility**: observe deterministic patient filtering (e.g. 25 patients eligible, 5 ineligible due to prior completed outreach or outside 48h window).
4. Review workload estimation (expected calls: 25, estimated attempts: 38, capacity utilization: 100%).
5. Click **Start Campaign** $\to$ state transitions to `RUNNING`.

#### 03:00 – 05:00: Outbound Queue, Capacity Bounding & Priority Scoring
1. Navigate to **Live Queue Dashboard**.
2. Observe active capacity gauge: **Strictly bounded at $10/10$ concurrent calls**.
3. Inspect task ordering:
   - Notice **Patient B** (Medium risk, but 45 min before clinical deadline) scheduled **ahead** of **Patient A** (High risk, but 36 hours remaining).
   - Notice **Starvation Aging Factor** boosting older pending tasks.
4. Demonstrate Call Simulator controls:
   - Trigger **No Answer** $\to$ observe automatic calculation of exponential backoff timestamp (`RETRY_SCHEDULED`).
   - Trigger **Busy** $\to$ backoff scheduled.
   - Trigger **Dropped Call** $\to$ partial transcript context saved.
   - Trigger **Callback Requested** $\to$ explicit target time saved (`CALLBACK_SCHEDULED`).
   - Trigger max retries reached $\to$ transitions automatically to `MANUAL_FOLLOW_UP`.

#### 05:00 – 07:00: AI Conversation, Protocol RAG & Dual-Assessment Triage
1. Open an active call simulation session for a Cardiac patient.
2. Select conversation scenario: **"Chest Discomfort & Shortness of Breath (Concerning / Urgent)"**.
3. Watch the **Voice Intake Agent** execute protocol follow-up questions.
4. Observe **Hospital Protocol RAG**: retrieved hospital-specific red flags for Congestive Heart Failure / Post-CABG.
5. Watch the **Clinical Triage Pipeline**:
   - Pydantic structured output generated with specific clinical indicator quotes.
   - **Assessment A (LLM)** flags `URGENT` due to chest pressure.
   - **Assessment B (Rule Validator)** flags `URGENT` due to resting dyspnea red flag.
   - **Consensus Arbiter** identifies agreement and issues immediate **ESCALATION**.

#### 07:00 – 08:30: Human-in-the-Loop Review & Mock EHR Synchronization
1. Log in as **Clinical Reviewer** (`dr.chen@stjude.health`).
2. Open **Escalation Inbox**: see the newly generated escalation ticket (`OPEN`).
3. Click into Escalation details:
   - View complete patient clinical context (CHF discharge, ejection fraction 35%, medications).
   - Read full conversation transcript with highlighted red flags.
   - Inspect side-by-side Assessment A and Assessment B evidence citations.
4. Click **Acknowledge & Assign to Self** $\to$ state changes to `IN_REVIEW`.
5. Enter Clinical Action: *"Called patient directly. Instructed to proceed immediately to Emergency Department. Contacted attending cardiologist."*
6. Click **Resolve Escalation** $\to$ state changes to `RESOLVED`.
7. Observe **Mock EHR Integration**: structured `Communication` record, `ClinicalImpression`, and `FollowUpTask` written with operation ID and audit trail.

#### 08:30 – 09:15: Observability, Audit Logs & System Health
1. Navigate to **Audit Explorer**: inspect immutable timeline of events (Task created $\to$ Call initiated $\to$ AI triage executed $\to$ Escalation created $\to$ Reviewer resolved $\to$ EHR updated).
2. Check `/api/v1/health` and `/api/v1/ready` endpoints: showing DB, Queue, Workers, and EHR status.

#### 09:15 – 10:00: Safety Evaluation Suite Execution
1. Run the automated clinical safety evaluation script:
   ```bash
   python scripts/evaluate_safety.py
   ```
2. Review the printed confusion matrix and False Negative Rate ($FNR = 0.00\%$).
3. Highlight adversarial prompt injection resilience.
