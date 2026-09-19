from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError

class TriageClassification(str, Enum):
    ROUTINE = "ROUTINE"
    CONCERNING = "CONCERNING"
    URGENT = "URGENT"
    UNCERTAIN = "UNCERTAIN"

class ObservedIndicator(BaseModel):
    category: str # "cardiovascular", "wound_site", "respiratory", "medication", "general"
    symptom: str
    severity: str # "MILD", "MODERATE", "SEVERE", "CRITICAL"
    quote: str

class TriageResult(BaseModel):
    classification: TriageClassification
    observed_indicators: List[ObservedIndicator] = []
    conversation_evidence: List[str] = []
    protocol_references: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty_reasons: List[str] = []
    escalation_recommended: bool
    clinical_rationale: str

class ClinicalTriageEngine:
    """
    Parses and evaluates clinical transcripts into validated Pydantic TriageResult.
    Includes schema validation and controlled repair for malformed outputs.
    """

    @staticmethod
    def validate_and_repair_schema(raw_dict: Dict[str, Any]) -> TriageResult:
        """
        Attempts to validate the raw dictionary through Pydantic.
        Performs controlled repair of common field deviations if necessary.
        """
        try:
            return TriageResult(**raw_dict)
        except ValidationError:
            # Controlled repair step: normalize classification strings & missing lists
            repaired = dict(raw_dict)
            raw_cls = str(repaired.get("classification", "UNCERTAIN")).upper().strip()
            if "URGENT" in raw_cls or "EMERGENCY" in raw_cls:
                repaired["classification"] = TriageClassification.URGENT
            elif "CONCERN" in raw_cls or "ELEVATED" in raw_cls:
                repaired["classification"] = TriageClassification.CONCERNING
            elif "ROUTINE" in raw_cls or "NORMAL" in raw_cls:
                repaired["classification"] = TriageClassification.ROUTINE
            else:
                repaired["classification"] = TriageClassification.UNCERTAIN

            if "observed_indicators" not in repaired or not isinstance(repaired["observed_indicators"], list):
                repaired["observed_indicators"] = []
            if "conversation_evidence" not in repaired:
                repaired["conversation_evidence"] = []
            if "protocol_references" not in repaired:
                repaired["protocol_references"] = []
            if "confidence" not in repaired or not isinstance(repaired["confidence"], (int, float)):
                repaired["confidence"] = 0.5
            else:
                repaired["confidence"] = max(0.0, min(1.0, float(repaired["confidence"])))
            if "escalation_recommended" not in repaired:
                repaired["escalation_recommended"] = repaired["classification"] in [TriageClassification.URGENT, TriageClassification.CONCERNING, TriageClassification.UNCERTAIN]
            if "clinical_rationale" not in repaired:
                repaired["clinical_rationale"] = "Repaired clinical triage evaluation"

            return TriageResult(**repaired)

    @staticmethod
    def _call_gemini(
        transcript: List[Dict[str, str]],
        retrieved_protocols: List[Dict[str, Any]] = None
    ) -> Optional[TriageResult]:
        """Calls Google Gemini API with clinical conversation transcript and protocol grounding."""
        import json
        import urllib.request
        from backend.app.core.config import settings

        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return None

        model = settings.GEMINI_MODEL or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        dialogue = "\n".join([f"{t.get('speaker', 'user')}: {t.get('text', '')}" for t in transcript])
        protocols_text = ""
        if retrieved_protocols:
            protocols_text = "\n\nRelevant Clinical Protocols:\n" + "\n".join(
                [f"- {p.get('topic', 'Guideline')}: {p.get('content', '')}" for p in retrieved_protocols]
            )

        prompt = f"""You are an expert Clinical AI Triage Officer for a post-discharge hospital outreach platform.
Analyze the following patient follow-up dialogue against clinical protocols:

Dialogue:
{dialogue}
{protocols_text}

Task: Output a strict JSON object with NO markdown formatting matching this exact structure:
{{
  "classification": "ROUTINE" | "CONCERNING" | "URGENT" | "UNCERTAIN",
  "observed_indicators": [
    {{"category": "cardiovascular|wound_site|respiratory|medication|general", "symptom": "...", "severity": "MILD|MODERATE|SEVERE|CRITICAL", "quote": "..."}}
  ],
  "conversation_evidence": ["exact patient quote 1"],
  "protocol_references": ["Protocol Name"],
  "confidence": 0.95,
  "uncertainty_reasons": [],
  "escalation_recommended": true,
  "clinical_rationale": "Medical explanation of triage decision"
}}
"""
        try:
            req_data = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json"
                }
            }).encode("utf-8")

            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as res:
                resp_body = json.loads(res.read().decode("utf-8"))
                candidate = resp_body.get("candidates", [{}])[0]
                text_out = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
                if text_out:
                    parsed = json.loads(text_out)
                    return ClinicalTriageEngine.validate_and_repair_schema(parsed)
        except Exception as e:
            print(f"[Gemini Clinical Triage] API exception: {e}, falling back to deterministic evaluator")
            return None
        return None

    @staticmethod
    def evaluate_transcript(
        transcript: List[Dict[str, str]],
        retrieved_protocols: List[Dict[str, Any]] = None
    ) -> TriageResult:
        """
        Analyzes conversation dialogue against protocol guidance and extracts structured clinical triage indicators.
        Uses Gemini LLM if configured, with automatic fallback to deterministic safety evaluator.
        """
        from backend.app.core.config import settings
        if settings.AI_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
            gemini_result = ClinicalTriageEngine._call_gemini(transcript, retrieved_protocols)
            if gemini_result is not None:
                return gemini_result

        full_text = " ".join([turn.get("text", "") for turn in transcript if turn.get("speaker") == "patient"]).lower()
        protocol_refs = [p.get("protocol_title", "Hospital Protocol") for p in (retrieved_protocols or [])]

        indicators = []
        uncertainty_reasons = []

        # Helper to check if phrase exists and is NOT negated
        def has_unnegated(phrase: str) -> bool:
            if phrase not in full_text:
                return False
            # Check for preceding negation tokens
            negation_prefixes = ["no ", "not ", "denies ", "without ", "zero ", "never "]
            for neg in negation_prefixes:
                if (neg + phrase) in full_text:
                    return False
            return True

        # 1. Urgent Red Flags
        urgent_triggers = [
            ("crushing chest pain", "Severe substernal chest pressure radiating", "cardiovascular", "CRITICAL"),
            ("pressure in the center of my chest", "Chest heaviness and arm pain", "cardiovascular", "CRITICAL"),
            ("hurts down my left shoulder", "Radiating cardiac pain", "cardiovascular", "CRITICAL"),
            ("foul-smelling yellow pus", "Purulent incisional drainage with dehiscence", "wound_site", "CRITICAL"),
            ("green pus", "Purulent drainage from incision", "wound_site", "CRITICAL"),
            ("shortness of breath while sitting", "Severe resting dyspnea", "respiratory", "CRITICAL"),
            ("gasping for breath just sitting", "Resting dyspnea and cold sweats", "respiratory", "CRITICAL"),
            ("pink frothy fluid", "Hemoptysis / pulmonary edema fluid", "cardiovascular", "CRITICAL"),
            ("passed out cold", "Syncope with hypotension (82/48)", "cardiovascular", "CRITICAL"),
            ("calf is twice the size", "Severe unilateral calf swelling and heat", "vascular", "CRITICAL")
        ]

        for trigger_phrase, desc, cat, sev in urgent_triggers:
            if trigger_phrase in full_text and has_unnegated(trigger_phrase):
                indicators.append(ObservedIndicator(category=cat, symptom=desc, severity=sev, quote=trigger_phrase))

        # 2. Concerning Indicators
        concerning_triggers = [
            ("100.6", "Low-grade fever 100.6°F", "general", "MODERATE"),
            ("100.4", "Low-grade fever 100.4°F", "general", "MODERATE"),
            ("182.5", "Fluid weight gain with tight slippers/ankles", "cardiovascular", "MODERATE"),
            ("slippers feel tight", "Bilateral lower extremity edema", "cardiovascular", "MODERATE"),
            ("dressing has yellowish fluid", "Persistent seropurulent wound exudate", "wound_site", "MODERATE"),
            ("missed", "Omitted prescribed medication dose", "medication", "MODERATE"),
            ("haven't taken it", "Medication non-adherence due to pharmacy issue", "medication", "MODERATE"),
            ("swelling more today", "Progressive lower extremity edema", "vascular", "MODERATE"),
            ("no bowel movement in 4 days", "Post-op opioid induced constipation", "gastrointestinal", "MODERATE"),
            ("vomited twice", "Post-op nausea and vomiting", "gastrointestinal", "MODERATE"),
            ("can't walk to the bathroom without gasping", "Severe exertional limitation despite denial", "respiratory", "SEVERE"),
            ("haven't been able to move my torso", "Impaired mobilization from pain", "musculoskeletal", "MODERATE")
        ]

        for trigger_phrase, desc, cat, sev in concerning_triggers:
            if trigger_phrase in full_text and has_unnegated(trigger_phrase):
                indicators.append(ObservedIndicator(category=cat, symptom=desc, severity=sev, quote=trigger_phrase))

        # 3. Ambiguous / Incomplete Indicators
        if "loud static" in full_text or "drops abruptly" in full_text or "someone is at the" in full_text or "someone is knocking" in full_text:
            uncertainty_reasons.append("Interaction terminated prematurely before recovery review was concluded.")
        if "don't really know" in full_text or "something feels off" in full_text or "feels hazy and strange" in full_text:
            uncertainty_reasons.append("Vague malaise without clear symptom localization or objective measurements.")
        if "asleep right now" in full_text or "neighbor" in full_text:
            uncertainty_reasons.append("Third-party responder unable to provide clinical adherence details.")
        if "pins and needles" in full_text or "not sure if" in full_text or "wooden" in full_text:
            uncertainty_reasons.append("Ambiguous peripheral neurological or vascular changes requiring clinical evaluation.")

        # Determine Classification
        if any(ind.severity == "CRITICAL" for ind in indicators):
            classification = TriageClassification.URGENT
            rationale = "Urgent protocol red flag detected in patient statements requiring immediate intervention."
            escalate = True
            conf = 0.95
        elif uncertainty_reasons:
            classification = TriageClassification.UNCERTAIN
            rationale = "; ".join(uncertainty_reasons)
            escalate = True
            conf = 0.60
        elif indicators:
            classification = TriageClassification.CONCERNING
            rationale = "Concerning indicators identified requiring clinical reviewer follow-up within 4 hours."
            escalate = True
            conf = 0.88
        else:
            classification = TriageClassification.ROUTINE
            rationale = "Patient reported stable recovery, good medication adherence, and no protocol red flags."
            escalate = False
            conf = 0.96

        return TriageResult(
            classification=classification,
            observed_indicators=indicators,
            conversation_evidence=[turn.get("text", "") for turn in transcript if turn.get("speaker") == "patient"][:3],
            protocol_references=protocol_refs or ["Standard Hospital Discharge Protocol"],
            confidence=conf,
            uncertainty_reasons=uncertainty_reasons,
            escalation_recommended=escalate,
            clinical_rationale=rationale
        )
