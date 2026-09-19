# Safety Evaluation & Clinical Guardrails Report

## Multi-Hospital Post-Discharge Outreach Platform (PRD v2.0)

### 1. Safety Philosophy & Threat Model
In automated healthcare outreach operations, **the asymmetric cost of clinical errors** dictates our engineering approach:
- **False Positive (Type I Error)**: A routine patient is marked concerning/urgent and escalated to a human nurse. Consequence: Minor operational overhead; patient safety is preserved.
- **False Negative (Type II Error)**: A patient experiencing acute post-discharge deterioration (e.g. surgical site infection, pulmonary embolism, congestive heart failure decompensation) is misclassified as routine and discarded from follow-up. Consequence: Severe patient harm, preventable readmission, or death.

**Mandate**: The system is tuned for ultra-low False Negative Rate ($FNR = \frac{FN}{FN + TP} \le 0.05$, aiming for $0.00$ on urgent red flags), with conservative disagreement consensus and human-in-the-loop escalation.

---

### 2. Evaluation Methodology & Reproducible Dataset
The benchmark uses a fixed, reproducible clinical evaluation dataset (`data/safety_cases.json`) comprising **30 diverse post-discharge patient interaction scenarios**:
- **Routine (10 cases)**: Stable recovery, vitals in normal range, clear discharge adherence, mild expected post-op soreness managed by prescribed Tylenol.
- **Concerning (6 cases)**: Moderate worsening of symptoms, unmanaged low-grade fever, missed medication doses due to nausea, mild mobility difficulty.
- **Urgent Red Flag (6 cases)**: Crushing chest pain, severe resting shortness of breath, sudden neurological deficits, purulent wound drainage with fever $>101.5^\circ\text{F}$, sudden weight gain $>3$ lbs in 24h with ankle edema.
- **Ambiguous & Incomplete (4 cases)**: Vague patient responses ("I feel strange", "something isn't right"), unanswered questions, partial connection.
- **Conflicting Information (2 cases)**: Patient claims they feel fine but reports severe shortness of breath or inability to walk to the bathroom.
- **Adversarial / Prompt Injection (2 cases)**: Malicious attempts to instruct the AI to ignore triage rules or suppress human escalation.

---

### 3. Confusion Matrix & Mathematical Formulations
- **True Positive (TP)**: Clinical case requiring escalation correctly escalated by consensus.
- **True Negative (TN)**: Routine case correctly classified without triggering unnecessary escalation.
- **False Positive (FP)**: Routine case conservatively escalated to human reviewer.
- **False Negative (FN)**: Dangerous case incorrectly classified as routine and NOT escalated.

$$\text{FNR} = \frac{\text{FN}}{\text{FN} + \text{TP}}$$
$$\text{Recall / Sensitivity} = \frac{\text{TP}}{\text{TP} + \text{FN}} = 1 - \text{FNR}$$
$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}$$

---

### 4. Running the Repeatable Evaluation
Evaluators can run the benchmark at any time using:
```bash
python scripts/evaluate_safety.py
```
This produces an automated markdown and JSON audit trail logging:
- Case-by-case comparison (Ground Truth vs Assessment A vs Assessment B vs Consensus)
- Disagreement rates between Assessment A and Assessment B
- Confusion Matrix (TP, TN, FP, FN) and final FNR
- Prompt injection resilience status.
