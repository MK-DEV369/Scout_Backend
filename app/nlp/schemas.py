from datetime import datetime

from pydantic import BaseModel, Field


class EntityWithConfidence(BaseModel):
    text: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ExtractedEntities(BaseModel):
    companies: list[EntityWithConfidence] = Field(default_factory=list)
    countries: list[EntityWithConfidence] = Field(default_factory=list)
    ports: list[EntityWithConfidence] = Field(default_factory=list)
    commodities: list[EntityWithConfidence] = Field(default_factory=list)


class StructuredEvent(BaseModel):
    source_record_id: int
    source: str
    timestamp: datetime
    text: str
    summary: str
    summary_confidence: float | None = Field(ge=0.0, le=1.0, default=None)
    category: str
    severity: float
    location: str | None = None
    entities: ExtractedEntities
    metadata: dict = Field(default_factory=dict)
