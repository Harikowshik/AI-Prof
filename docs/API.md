# REST API Documentation & OpenAPI Specification

## Multi-Hospital Post-Discharge Outreach Platform (PRD v2.0)

All endpoints require JWT Bearer Authentication (`Authorization: Bearer <token>`) except `/api/v1/auth/login` and `/api/v1/health`.
All endpoints strictly enforce server-side **Tenant Isolation**: hospital users can only access their own hospital's resources.

---

### Authentication & RBAC (`/api/v1/auth`)

#### `POST /api/v1/auth/login`
- **Request**: Form data or JSON `{"username": "...", "password": "..."}`
- **Response**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "user_id": "u-123",
    "email": "dr.chen@stjude.health",
    "full_name": "Dr. David Chen, MD",
    "role": "CLINICAL_REVIEWER",
    "hospital_id": "h-stjude"
  }
  ```

#### `GET /api/v1/auth/me`
- **Response**: User profile and tenant mapping.

---

### Hospital & Tenant Management (`/api/v1/hospitals`)

#### `GET /api/v1/hospitals`
- **Roles**: `PLATFORM_ADMIN` sees all; `HOSPITAL_ADMIN` / others see caller's hospital.

#### `GET /api/v1/hospitals/{hospital_id}`
- Returns operational settings, calling hours, capacity limit, and active calls.

#### `PATCH /api/v1/hospitals/{hospital_id}`
- Updates capacity (`max_concurrent_calls`), calling window (`calling_hours_start/end`), retry limit.

---

### Discharge Ingestion (`/api/v1/ingestion`)

#### `POST /api/v1/ingestion/upload`
- **Payload**:
  ```json
  {
    "hospital_id": "...",
    "records": [
      {
        "mrn": "MRN-101",
        "first_name": "John",
        "last_name": "Doe",
        "date_of_birth": "1965-04-12",
        "gender": "Male",
        "phone": "+1-555-123-4567",
        "department": "CARDIOLOGY",
        "discharge_timestamp": "2026-09-15T14:30:00Z",
        "primary_diagnosis": "Congestive Heart Failure"
      }
    ]
  }
  ```
- **Response**: `total_received`, `successful_count`, `duplicates_count`, `failed_count`, and error array.

---

### Campaign Management & Eligibility (`/api/v1/campaigns`)

#### `GET /api/v1/campaigns`
- Returns tenant campaigns, active tasks count, completed count.

#### `GET /api/v1/campaigns/{id}/workload`
- Pre-activation projection: eligible patients, expected attempts, estimated completion time.

#### `POST /api/v1/campaigns/{id}/evaluate-eligibility`
- Evaluates discharge records against clinical rules, populates queue with `PENDING` tasks.

#### `POST /api/v1/campaigns/{id}/start` | `pause` | `resume`
- Manages campaign execution lifecycle.

---

### Outbound Queue & Concurrency (`/api/v1/queue`)

#### `GET /api/v1/queue`
- Returns dynamic prioritized queue sorted by `computed_priority` descending.
- Shows clinical risk, deadline urgency, hours until clinical cutoff, starvation boost, and attempt count.

#### `GET /api/v1/queue/stats`
- Returns active calls counter, capacity limit, capacity utilization rate %, breakdown by status.

#### `POST /api/v1/queue/schedule-next`
- Atomically reserves capacity and returns next task to dial. Returns 429 if capacity is full.

#### `POST /api/v1/queue/reap-stale`
- Recovers tasks from crashed workers, releases capacity, and re-queues.

---

### Telephony Simulation & Calls (`/api/v1/calls`)

#### `POST /api/v1/calls/simulate-outcome`
- **Request**:
  ```json
  {
    "task_id": "...",
    "outcome": "SUCCESSFUL | NO_ANSWER | BUSY | VOICEMAIL | DROPPED | CALLBACK_REQUESTED",
    "duration_seconds": 60,
    "callback_time": "2026-09-16T14:00:00Z"
  }
  ```

---

### AI Clinical Pipeline (`/api/v1/ai`)

#### `GET /api/v1/ai/scenarios`
- Returns 7 clinically diverse pre-programmed demonstration scenarios.

#### `POST /api/v1/ai/run-interaction`
- Executes end-to-end AI pipeline:
  1. Protocol RAG retrieval
  2. Dual Assessments (A: LLM protocol reasoning, B: Independent rule validator)
  3. Conservative Consensus Arbiter
  4. Controlled tool execution (escalation ticket if flagged)
  5. Traceable Clinical Progress Note
  6. Mock EHR update
  7. Audit log & AI telemetry.

---

### Clinical Reviewer Escalations (`/api/v1/escalations`)

#### `GET /api/v1/escalations`
- List open, assigned, and resolved clinical escalations.

#### `GET /api/v1/escalations/{id}`
- Comprehensive review package: conversation transcript, dual assessment side-by-side, protocol citations.

#### `POST /api/v1/escalations/{id}/action`
- Actions: `ASSIGN`, `IN_REVIEW`, `RESOLVE`, `CLOSE`. Requires `resolution_action` note when resolving.

---

### Mock EHR Integration (`/api/v1/ehr`)

#### `POST /api/v1/ehr/sync-documentation`
- Synchronizes call progress note to EHR as structured `Communication` and `Observation`.

#### `POST /api/v1/ehr/toggle-failure-mode`
- Enables/disables simulated EHR gateway timeout to verify error handling and recovery.

---

### Observability, Health & Audit (`/api/v1/health`, `/api/v1/audit`, `/api/v1/analytics`)

#### `GET /api/v1/health`
- Component readiness: database, queue scheduler, EHR gateway, AI pipeline.

#### `GET /api/v1/audit`
- Immutable append-only audit trail filterable by action, entity, user, and correlation ID.

#### `GET /api/v1/analytics/summary`
- Real-time contact rate, average attempts per case, outcome breakdown computed directly from DB.
