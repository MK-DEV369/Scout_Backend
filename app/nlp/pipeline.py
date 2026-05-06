from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventRecord, UnifiedRecord
from app.nlp.entity_extractor import extract_entities
from app.nlp.event_classifier import classify_event
from app.nlp.summarizer import summarize_as_bullets


def build_structured_events(db: Session, limit: int = 100) -> dict[str, int]:
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
        category, confidence, classifier_model = classify_event(record.text)
        summary = summarize_as_bullets(record.text)

        event = EventRecord(
            unified_record_id=record.id,
            source=record.source,
            timestamp=record.timestamp,
            category=category,
            summary=summary,
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
