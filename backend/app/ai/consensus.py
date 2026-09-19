from typing import Dict, Any, List
from pydantic import BaseModel
from backend.app.ai.triage import TriageResult, TriageClassification

class ConsensusEvaluation(BaseModel):
    final_classification: TriageClassification
    escalation_required: bool
    disagreement_detected: bool
    assessment_a_classification: TriageClassification
    assessment_b_classification: TriageClassification
    consensus_decision_basis: str
    combined_indicators: List[Dict[str, Any]]
    combined_evidence: List[str]

class ConsensusArbiter:
    """
    Conservative Clinical Consensus Arbiter.
    Never relies on a single model or agent output to determine patient escalation.
    Any red flag, clinical uncertainty, or inter-assessment disagreement triggers escalation.
    """

    @staticmethod
    def arbitrate(
        assessment_a: TriageResult, 
        assessment_b: TriageResult
    ) -> ConsensusEvaluation:
        a_cls = assessment_a.classification
        b_cls = assessment_b.classification
        is_disagreement = (a_cls != b_cls)

        # Merge indicators and evidence
        indicators = [ind.model_dump() for ind in assessment_a.observed_indicators]
        for ind in assessment_b.observed_indicators:
            if ind.model_dump() not in indicators:
                indicators.append(ind.model_dump())
                
        evidence = list(set(assessment_a.conversation_evidence + assessment_b.conversation_evidence))

        # Rule 1: Conservative Red Flag Escalation
        if a_cls == TriageClassification.URGENT or b_cls == TriageClassification.URGENT:
            return ConsensusEvaluation(
                final_classification=TriageClassification.URGENT,
                escalation_required=True,
                disagreement_detected=is_disagreement,
                assessment_a_classification=a_cls,
                assessment_b_classification=b_cls,
                consensus_decision_basis="Urgent protocol red flag identified by one or both clinical assessments.",
                combined_indicators=indicators,
                combined_evidence=evidence
            )

        # Rule 2: Precautionary Uncertainty Escalation
        if a_cls == TriageClassification.UNCERTAIN or b_cls == TriageClassification.UNCERTAIN:
            return ConsensusEvaluation(
                final_classification=TriageClassification.UNCERTAIN,
                escalation_required=True,
                disagreement_detected=True,
                assessment_a_classification=a_cls,
                assessment_b_classification=b_cls,
                consensus_decision_basis="Meaningful clinical uncertainty or incomplete interaction triggers conservative escalation.",
                combined_indicators=indicators,
                combined_evidence=evidence
            )

        # Rule 3: Disagreement Precaution
        if is_disagreement:
            return ConsensusEvaluation(
                final_classification=TriageClassification.CONCERNING,
                escalation_required=True,
                disagreement_detected=True,
                assessment_a_classification=a_cls,
                assessment_b_classification=b_cls,
                consensus_decision_basis=f"Inter-assessment disagreement ({a_cls} vs {b_cls}) triggers conservative escalation for clinical review.",
                combined_indicators=indicators,
                combined_evidence=evidence
            )

        # Rule 4: Concordant Routine or Concerning
        return ConsensusEvaluation(
            final_classification=a_cls,
            escalation_required=(a_cls == TriageClassification.CONCERNING),
            disagreement_detected=False,
            assessment_a_classification=a_cls,
            assessment_b_classification=b_cls,
            consensus_decision_basis=f"Both independent assessments agree on '{a_cls}'.",
            combined_indicators=indicators,
            combined_evidence=evidence
        )
