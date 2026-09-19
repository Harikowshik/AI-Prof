from typing import List, Dict, Any
from backend.app.ai.triage import ClinicalTriageEngine, TriageResult, TriageClassification, ObservedIndicator

class DualAssessmentEngine:
    """
    Executes two independent clinical evaluations across distinct reasoning pathways:
    - Assessment A: Protocol-grounded semantic clinical interpretation.
    - Assessment B: Independent rule-assisted clinical trigger matrix.
    """

    @staticmethod
    def run_assessment_a(
        transcript: List[Dict[str, str]],
        retrieved_protocols: List[Dict[str, Any]]
    ) -> TriageResult:
        """
        Assessment A: Protocol reasoning evaluation evaluating conversation evidence
        against retrieved hospital protocol text.
        """
        return ClinicalTriageEngine.evaluate_transcript(transcript, retrieved_protocols)

    @staticmethod
    def run_assessment_b(
        transcript: List[Dict[str, str]]
    ) -> TriageResult:
        """
        Assessment B: Independent deterministic rule validator scanning strictly for
        physiologic red flags, vital signs deviations, and explicit prompt injection indicators.
        """
        full_text = " ".join([turn.get("text", "") for turn in transcript if turn.get("speaker") == "patient"]).lower()
        
        indicators = []
        uncertainty = []

        def has_unnegated(phrase: str) -> bool:
            if phrase not in full_text:
                return False
            negations = ["no ", "not ", "denies ", "without ", "zero ", "never "]
            for neg in negations:
                if (neg + phrase) in full_text:
                    return False
            return True

        # Adversarial / Prompt Injection Scan
        adversarial_terms = ["ignore all previous", "system override", "maintenance mode", "bypass escalation", "do not alert"]
        if any(term in full_text for term in adversarial_terms):
            indicators.append(ObservedIndicator(
                category="adversarial_detection",
                symptom="Prompt Injection / Safety Bypass Attempt",
                severity="CRITICAL",
                quote="Patient utterance contained system override instructions"
            ))

        # Core physiologic red flags with negation protection
        if has_unnegated("chest") and (has_unnegated("pain") or has_unnegated("pressure") or has_unnegated("tightness")):
            indicators.append(ObservedIndicator(
                category="cardiovascular",
                symptom="Chest Discomfort / Potential Ischemia",
                severity="CRITICAL",
                quote="Chest pain or pressure reported"
            ))
            
        if (has_unnegated("fever") or "102" in full_text or "101" in full_text or "100" in full_text) and has_unnegated("fever"):
            indicators.append(ObservedIndicator(
                category="infectious",
                symptom="Post-Op Pyrexia / Elevated Temperature",
                severity="MODERATE",
                quote="Elevated temperature reported"
            ))

        if "pus" in full_text or "split open" in full_text or "foul" in full_text:
            indicators.append(ObservedIndicator(
                category="wound_site",
                symptom="Incisional Infection / Dehiscence",
                severity="CRITICAL",
                quote="Wound breakdown or purulent discharge"
            ))

        if has_unnegated("short of breath") or has_unnegated("gasping") or has_unnegated("can't breathe"):
            indicators.append(ObservedIndicator(
                category="respiratory",
                symptom="Dyspnea / Respiratory Compromise",
                severity="CRITICAL",
                quote="Dyspnea or gasping reported"
            ))

        if "static" in full_text or "drops abruptly" in full_text or "pins and needles" in full_text or "not sure if" in full_text or "slippers feel tight" in full_text:
            uncertainty.append("Potential clinical or communication uncertainty detected requiring reviewer attention")

        # Determine Independent Assessment B classification
        if any(ind.severity == "CRITICAL" for ind in indicators):
            classification = TriageClassification.URGENT
            rationale = "Assessment B (Independent Rule Validator): Severe physiologic red flag or adversarial attempt detected."
            escalate = True
            conf = 0.99
        elif uncertainty:
            classification = TriageClassification.UNCERTAIN
            rationale = "Assessment B: " + "; ".join(uncertainty)
            escalate = True
            conf = 0.70
        elif indicators:
            classification = TriageClassification.CONCERNING
            rationale = "Assessment B: Moderate clinical flags identified requiring clinical review."
            escalate = True
            conf = 0.85
        else:
            classification = TriageClassification.ROUTINE
            rationale = "Assessment B: Zero clinical flags or safety violations triggered."
            escalate = False
            conf = 0.95

        return TriageResult(
            classification=classification,
            observed_indicators=indicators,
            conversation_evidence=[turn.get("text", "") for turn in transcript if turn.get("speaker") == "patient"][:2],
            protocol_references=["Independent Clinical Rule Validator (Assessment B)"],
            confidence=conf,
            uncertainty_reasons=uncertainty,
            escalation_recommended=escalate,
            clinical_rationale=rationale
        )
