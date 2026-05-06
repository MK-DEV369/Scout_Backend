from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class NormalizedRecord(BaseModel):
    source: str
    timestamp: datetime
    text: str = Field(min_length=1)
    location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None

    @classmethod
    def with_defaults(
        cls,
        *,
        source: str,
        text: str,
        timestamp: datetime | None = None,
        location: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> "NormalizedRecord":
        ts = timestamp or datetime.now(timezone.utc)
        return cls(
            source=source,
            text=text.strip(),
            timestamp=ts,
            location=location,
            metadata=metadata or {},
            source_id=source_id,
        )
