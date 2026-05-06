import hashlib
from datetime import timezone

from app.ingestion.schema import NormalizedRecord


def compute_content_hash(item: NormalizedRecord) -> str:
    ts = item.timestamp.astimezone(timezone.utc).isoformat()
    stable = "|".join(
        [
            item.source.lower().strip(),
            (item.source_id or "").strip(),
            ts,
            item.text.strip().lower(),
            (item.location or "").strip().lower(),
        ]
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()
