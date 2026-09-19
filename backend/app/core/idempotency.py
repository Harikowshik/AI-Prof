import hashlib
from typing import Optional

def generate_idempotency_key(*parts: str) -> str:
    """Generates a deterministic hash from arbitrary key components."""
    combined = ":".join(str(p) for p in parts if p is not None)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

class IdempotencyRecordManager:
    """In-memory or database-backed tracking of processed operation keys."""
    def __init__(self):
        self._processed_keys = set()

    def is_processed(self, key: str) -> bool:
        return key in self._processed_keys

    def record_key(self, key: str):
        self._processed_keys.add(key)

idempotency_manager = IdempotencyRecordManager()
