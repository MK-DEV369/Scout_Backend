from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventRecord, UnifiedRecord
from app.nlp.entity_extractor import extract_entities
from app.nlp.event_classifier import classify_event
from app.nlp.schemas import ExtractedEntities, EntityWithConfidence
from app.nlp.summarizer import summarize_as_bullets


def filter_entities_by_confidence(entities: ExtractedEntities, min_confidence: float = 0.7) -> ExtractedEntities:
    """Filter entities to only include those with confidence >= min_confidence."""
    return ExtractedEntities(
        companies=[e for e in entities.companies if e.confidence >= min_confidence],
        countries=[e for e in entities.countries if e.confidence >= min_confidence],
        ports=[e for e in entities.ports if e.confidence >= min_confidence],
        commodities=[e for e in entities.commodities if e.confidence >= min_confidence],
    )


def build_structured_events(db: Session, limit: int = 100, entity_confidence_threshold: float = 0.7) -> dict[str, int]:
    processed_ids = {
        row[0]
        for row in db.execute(select(EventRecord.unified_record_id)).all()
    }

    candidates = db.execute(
        select(UnifiedRecord).order_by(UnifiedRecord.timestamp.desc()).limit(limit)
    ).scalars().all()

    created = 0
    skipped = 0

    for record in candidates:
        if record.id in processed_ids:
            skipped += 1
            continue

        entities = extract_entities(record.text)
        entities = filter_entities_by_confidence(entities, min_confidence=entity_confidence_threshold)
        category, confidence, classifier_model = classify_event(record.text)
        summary, summary_confidence = summarize_as_bullets(record.text)

        event = EventRecord(
            unified_record_id=record.id,
            source=record.source,
            timestamp=record.timestamp,
            category=category,
            summary=summary,
            summary_confidence=summary_confidence,
            location=record.location,
            severity=min(max(confidence, 0.0), 1.0),
            entities_json=entities.model_dump(),
            metadata_json=record.metadata_json,
            classifier_model=classifier_model,
            classifier_confidence=float(min(max(confidence, 0.0), 1.0)),
        )
        db.add(event)
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped}
