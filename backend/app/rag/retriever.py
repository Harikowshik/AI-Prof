import math
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.knowledge import ProtocolDocument, ProtocolChunk

class ProtocolRetriever:
    """
    Tenant-Isolated Clinical Protocol Retriever.
    Enforces strict tenant scoping (WHERE hospital_id = :tenant_id).
    Hospital A will NEVER retrieve Hospital B guidelines.
    """

    @staticmethod
    def search_protocol_chunks(
        db: Session,
        hospital_id: str,
        query: str,
        protocol_type: str = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieves most relevant protocol chunks for the hospital tenant,
        preserving source references, section titles, and text evidence.
        """
        db_query = db.query(ProtocolChunk).filter(
            ProtocolChunk.hospital_id == hospital_id
        )

        if protocol_type:
            db_query = db_query.join(ProtocolDocument).filter(
                ProtocolDocument.protocol_type == protocol_type.upper()
            )

        chunks = db_query.all()
        if not chunks:
            # If no chunks found for specific type, fallback to all hospital chunks
            chunks = db.query(ProtocolChunk).filter(
                ProtocolChunk.hospital_id == hospital_id
            ).all()

        query_terms = set(query.lower().split())

        # Lexical-semantic scoring with term overlap
        scored = []
        for ch in chunks:
            chunk_words = ch.chunk_text.lower().split()
            overlap = sum(1 for w in query_terms if w in chunk_words or any(w in cw for cw in chunk_words))
            
            # Additional score for critical red-flag keywords
            red_flag_bonus = 0.0
            critical_keywords = ["chest", "pain", "fever", "pus", "drainage", "weight", "shortness", "breath", "dyspnea", "syncope", "calf", "swelling"]
            for ck in critical_keywords:
                if ck in query.lower() and ck in ch.chunk_text.lower():
                    red_flag_bonus += 0.5

            total_score = overlap + red_flag_bonus
            scored.append((total_score, ch))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_results = scored[:top_k]

        formatted = []
        for score, ch in top_results:
            formatted.append({
                "chunk_id": ch.id,
                "protocol_id": ch.protocol_id,
                "protocol_title": ch.protocol.title if ch.protocol else "Hospital Protocol",
                "hospital_id": ch.hospital_id,
                "section_title": ch.section_title,
                "chunk_text": ch.chunk_text,
                "relevance_score": round(score, 2)
            })

        return formatted
