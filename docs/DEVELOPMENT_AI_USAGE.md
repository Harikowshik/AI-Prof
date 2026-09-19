# Development AI Usage & Engineering Prompts

## Multi-Hospital Post-Discharge Outreach Platform (PRD v2.0)

As specified in Section 76 of the PRD, this document captures the important AI-assisted workflows, prompts, and architectural decisions utilized during the rapid development of this platform.

---

### 1. Architectural & Domain Modeling Workflows
- **Objective**: Design a clean FHIR-inspired relational schema that enforces multi-tenancy without treating patients as flat JSON objects.
- **Workflow**: Formulated structured entity relationships connecting `Hospital`, `User`, `Patient`, `Encounter`, `Discharge`, `Condition`, `Observation`, `Campaign`, `OutreachTask`, `Call`, `Escalation`, and `AuditLog`.
- **Key Prompt Pattern**:
  > *"Design a normalized relational schema for a multi-tenant hospital outreach platform. Ensure all clinical entities (Patient, Encounter, Discharge, Condition, Observation) carry explicit or relational tenant scoping. Model outreach task states explicitly with audit history and concurrency timestamps."*

---

### 2. Queue Prioritization & Concurrency Engineering
- **Objective**: Develop a continuous scoring function combining clinical risk with clinical deadline pressure and starvation prevention.
- **Workflow**: Derived the normalized mathematical formula balancing $S_{\text{risk}}$, $S_{\text{deadline}}$, $S_{\text{callback}}$, $S_{\text{retry}}$, and an aging coefficient $\alpha \cdot T_{\text{wait}}$.
- **Key Prompt Pattern**:
  > *"Derive an operational priority scoring algorithm where deadline urgency dynamically overtakes raw clinical risk when a patient's post-discharge window is about to expire, while incorporating an aging factor to guarantee starvation prevention for low-risk tasks."*

---

### 3. Dual-Assessment Clinical Safety & Consensus Arbiter
- **Objective**: Prevent single-model classification failure by pairing LLM protocol reasoning with independent rule-based verification.
- **Workflow**: Implemented the conservative consensus arbiter where any red flag, disagreement, or uncertainty triggers escalation.
- **Key Prompt Pattern**:
  > *"Formulate a conservative consensus arbiter for two clinical agents (Assessment A: LLM protocol reasoning; Assessment B: Rule-based indicator validator). Specify the exact truth table that guarantees zero false negatives on life-threatening red flags."*

---

### 4. Safety Evaluation Benchmark Generation
- **Objective**: Create 30 diverse, clinically authentic post-discharge dialogue scenarios with ground-truth classifications.
- **Workflow**: Generated structured test cases spanning routine recovery, wound infections, cardiovascular emergencies, medication confusion, and adversarial prompt injections.
