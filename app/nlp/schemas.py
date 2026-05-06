from datetime import datetime

from pydantic import BaseModel, Field


class ExtractedEntities(BaseModel):
    companies: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    ports: list[str] = Field(default_factory=list)
    commodities: list[str] = Field(default_factory=list)


class StructuredEvent(BaseModel):
    source_record_id: int
    source: str
    timestamp: datetime
    text: str
    summary: str
    category: str
    severity: float
    location: str | None = None
    entities: ExtractedEntities
    metadata: dict = Field(default_factory=dict)
