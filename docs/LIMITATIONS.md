# Architectural Limitations, Simplifications & Tradeoffs

## Multi-Hospital Post-Discharge Outreach Platform (PRD v2.0)

As required by Section 77 of the PRD, this document explicitly delineates what has been **IMPLEMENTED**, **SIMULATED**, **SIMPLIFIED**, and **NOT IMPLEMENTED** in this prototype.

---

### 1. Categorical Breakdown

#### IMPLEMENTED (Full Production Architecture)
- **Multi-Tenancy & Hard Isolation**: Strict server-side tenant scoping at database, repository, service, worker, and RAG retrieval levels. Zero cross-tenant data leakage.
- **Role-Based Access Control (RBAC)**: 4 explicit tiers (`PLATFORM_ADMIN`, `HOSPITAL_ADMIN`, `CAMPAIGN_MANAGER`, `CLINICAL_REVIEWER`) with route-level and service-level enforcement.
- **Centralized Capacity-Aware Queue**: Strict concurrency limit (e.g. 10 concurrent active calls) enforced via database transactional locking.
- **Mathematical Queue Prioritization**: Multi-factor scoring incorporating clinical risk, deadline pressure curve, callback urgency, retry urgency, time since discharge, and starvation prevention aging.
- **Queue State Machine**: Explicit transitions, state history tracking, and invalid transition rejection across all PRD-defined states.
- **Retry & Exponential Backoff**: Outcome-based delays (No Answer, Busy, Dropped, Voicemail, Tech Failure) clamped to hospital calling hours and clinical cutoffs.
- **Stale Task & Worker Crash Recovery**: Heartbeat lease tracking, lease expiration reapers, and automatic capacity release.
- **Dual AI Clinical Assessments & Consensus**: Independent Assessment A (LLM/protocol reasoning) and Assessment B (independent clinical rule validation) with conservative disagreement escalation.
- **Controlled AI Tools Layer**: Schema-validated, authenticated, and audited tools with zero direct SQL access for AI agents.
- **EHR Abstraction Layer**: Pluggable interface (`EHRService`) with structured operations and error simulation.
- **Safety Evaluation Suite**: 30-case reproducible benchmark measuring True Positives, True Negatives, False Positives, False Negatives, and False Negative Rate (FNR).
- **Audit Logging & Telemetry**: Append-only audit records, correlation IDs, and system health endpoints (`/health`, `/ready`).

#### SIMULATED (High-Fidelity Deterministic Mocks)
- **Telephony / Voice Carrier**: Real outbound SIP/WebRTC trunking is replaced by a deterministic telephony simulator supporting configurable outcomes (`SUCCESSFUL`, `NO_ANSWER`, `BUSY`, `VOICEMAIL`, `DROPPED`, `TECHNICAL_FAILURE`, `CALLBACK_REQUESTED`).
- **Patient Speech Interface**: Deterministic conversation simulator supporting 7 clinically diverse patient interaction scenarios (Routine, Concerning, Urgent, Ambiguous, Incomplete, Conflicting, Prompt Injection).
- **EHR Backend**: The `MockEHRService` simulates a real FHIR/HL7 EHR endpoint with configurable network latency and write failure recovery modes.

#### SIMPLIFIED
- **Healthcare Data Entities**: Implements simplified FHIR-like resources (`Patient`, `Encounter`, `Discharge`, `Condition`, `Observation`, `Medication`, `CarePlan`) tailored to post-discharge operations rather than 100+ FHIR R4 resource specifications.
- **Database Engine**: Dual-support architecture providing immediate zero-setup SQLite (WAL mode, foreign keys, transaction locks) alongside full PostgreSQL + pgvector schema and Docker configurations.

#### NOT IMPLEMENTED (Out of Scope for 3–4 Day Operational Prototype)
- Real clinical production deployment with live human patients (prohibited for safety/regulatory compliance).
- HIPAA / SOC 2 formal compliance certification (demo data only; synthetic patient records).
- Commercial EHR vendor App Orchard certification (Epic/Cerner sandbox).

---

### 2. Tradeoffs & Design Decisions
1. **Modular Monolith vs. Microservices**:
   - *Decision*: A unified modular monolith with clean domain boundaries and background workers was chosen over 10 microservices.
   - *Rationale*: Eliminates distributed transaction failures and service mesh overhead, enabling complete focus on queue correctness, safety consensus, and multi-tenant integrity.
2. **Dual-Assessment Consensus vs. Single LLM Call**:
   - *Decision*: Two independent assessments are evaluated and compared before escalating.
   - *Rationale*: In healthcare, single-model hallucinations or missed red flags represent unacceptable safety risks. Redundant evaluation with conservative disagreement handling reduces clinical false negatives to near zero.
