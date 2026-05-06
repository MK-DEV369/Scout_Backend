from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import EventRecord, RiskRecord, Supplier
from app.db.session import get_db
from app.ingestion.scheduler import run_ingestion_job
from app.nlp.pipeline import build_structured_events
from app.risk.pipeline import score_events

router = APIRouter(tags=["phase3-6"])

ALERT_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}

LOCATION_COORDS = {
    "india": {"lat": 20.5937, "lng": 78.9629},
    "china": {"lat": 35.8617, "lng": 104.1954},
    "united states": {"lat": 37.0902, "lng": -95.7129},
    "usa": {"lat": 37.0902, "lng": -95.7129},
    "germany": {"lat": 51.1657, "lng": 10.4515},
    "singapore": {"lat": 1.3521, "lng": 103.8198},
    "shanghai": {"lat": 31.2304, "lng": 121.4737},
    "hamburg": {"lat": 53.5511, "lng": 9.9937},
    "rotterdam": {"lat": 51.9244, "lng": 4.4777},
    "long beach": {"lat": 33.7701, "lng": -118.1937},
    "los angeles": {"lat": 34.0522, "lng": -118.2437},
}


def _build_explanation(event: EventRecord, supplier: Supplier | None) -> str:
    supplier_name = supplier.name if supplier else "monitored supplier set"
    countries = []
    if isinstance(event.entities_json, dict):
        raw_countries = event.entities_json.get("countries", [])
        countries = raw_countries if isinstance(raw_countries, list) else []

    first_country = countries[0] if countries else None
    where = event.location or first_country or "upstream lane"
    return f"{event.category} disruption in {where} can impact {supplier_name} via dependency links"


def _coords_for_event(event: EventRecord) -> dict[str, float | None]:
    candidates = [
        event.location,
        *(event.entities_json.get("ports", [])[:1] if isinstance(event.entities_json, dict) else []),
        *(event.entities_json.get("countries", [])[:1] if isinstance(event.entities_json, dict) else []),
    ]
    for value in candidates:
        if not value:
            continue
        coord = LOCATION_COORDS.get(str(value).lower())
        if coord:
            return coord
    return {"lat": None, "lng": None}


@router.post("/ingest")
async def ingest_now() -> dict:
    return await run_ingestion_job()


@router.post("/events")
def process_events(limit: int = 100, db: Session = Depends(get_db)) -> dict:
    return build_structured_events(db, limit=limit)


@router.get("/events")
def list_events(limit: int = 100, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(EventRecord).order_by(desc(EventRecord.timestamp)).limit(limit)).scalars().all()
    items = [
        {
            "id": row.id,
            "unified_record_id": row.unified_record_id,
            "source": row.source,
            "timestamp": row.timestamp.isoformat(),
            "category": row.category,
            "summary": row.summary,
            "location": row.location,
            "severity": row.severity,
            "entities": row.entities_json,
        }
        for row in rows
    ]
    return {"items": items}


@router.post("/risk")
def run_risk(limit: int = 100, db: Session = Depends(get_db)) -> dict:
    return score_events(db, limit=limit)


@router.get("/risk")
def list_risk(limit: int = 100, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(RiskRecord).order_by(desc(RiskRecord.risk_score)).limit(limit)).scalars().all()
    items = [
        {
            "id": row.id,
            "event_id": row.event_id,
            "supplier_id": row.supplier_id,
            "risk_score": row.risk_score,
            "alert_level": row.alert_level,
            "features": row.feature_json,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
    return {"items": items}


@router.get("/alerts")
def list_alerts(min_level: str = "Medium", limit: int = 100, db: Session = Depends(get_db)) -> dict:
    threshold = ALERT_ORDER.get(min_level, 2)
    rows = db.execute(
        select(RiskRecord, EventRecord, Supplier)
        .join(EventRecord, EventRecord.id == RiskRecord.event_id)
        .outerjoin(Supplier, Supplier.id == RiskRecord.supplier_id)
        .order_by(desc(RiskRecord.risk_score))
        .limit(limit)
    ).all()
    filtered = [row for row in rows if ALERT_ORDER.get(row[0].alert_level, 0) >= threshold]

    return {
        "items": [
            {
                "risk_id": risk.id,
                "event_id": event.id,
                "event": event.summary,
                "supplier": supplier.name if supplier else None,
                "risk_score": risk.risk_score,
                "alert_level": risk.alert_level,
                "features": risk.feature_json,
                "explanation": _build_explanation(event, supplier),
            }
            for risk, event, supplier in filtered
        ]
    }


@router.get("/top-risks")
def top_risks(limit: int = 20, min_level: str = "Medium", db: Session = Depends(get_db)) -> dict:
    threshold = ALERT_ORDER.get(min_level, 2)
    rows = db.execute(
        select(RiskRecord, EventRecord, Supplier)
        .join(EventRecord, EventRecord.id == RiskRecord.event_id)
        .outerjoin(Supplier, Supplier.id == RiskRecord.supplier_id)
        .order_by(desc(RiskRecord.risk_score))
        .limit(limit)
    ).all()

    items = []
    for risk, event, supplier in rows:
        if ALERT_ORDER.get(risk.alert_level, 0) < threshold:
            continue
        items.append(
            {
                "risk_id": risk.id,
                "event_id": event.id,
                "level": risk.alert_level,
                "risk_score": risk.risk_score,
                "supplier": supplier.name if supplier else None,
                "category": event.category,
                "timestamp": event.timestamp.isoformat(),
                "explanation": _build_explanation(event, supplier),
            }
        )
    return {"items": items}


@router.get("/events/trends")
def event_trends(db: Session = Depends(get_db)) -> dict:
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)

    today_count = int(
        db.execute(
            select(func.count())
            .select_from(EventRecord)
            .where(EventRecord.timestamp >= today_start)
            .where(EventRecord.timestamp < tomorrow_start)
        ).scalar()
        or 0
    )

    day_bucket = func.date_trunc("day", EventRecord.timestamp)
    prior_rows = db.execute(
        select(day_bucket, func.count())
        .group_by(day_bucket)
        .order_by(desc(day_bucket))
        .offset(1)
        .limit(7)
    ).all()
    prior_avg = (sum(int(row[1]) for row in prior_rows) / len(prior_rows)) if prior_rows else 0.0
    trend = "stable"
    if prior_avg > 0 and today_count > prior_avg * 1.5:
        trend = "spike"
    elif prior_avg > 0 and today_count < prior_avg * 0.7:
        trend = "drop"

    yesterday_count = int(
        db.execute(
            select(func.count())
            .select_from(EventRecord)
            .where(EventRecord.timestamp >= yesterday_start)
            .where(EventRecord.timestamp < today_start)
        ).scalar()
        or 0
    )

    return {
        "today_event_count": today_count,
        "yesterday_event_count": yesterday_count,
        "prior_7_day_average": round(prior_avg, 2),
        "trend": trend,
    }


@router.get("/risk-map")
def risk_map(limit: int = 100, min_level: str = "Medium", db: Session = Depends(get_db)) -> dict:
    threshold = ALERT_ORDER.get(min_level, 2)
    rows = db.execute(
        select(RiskRecord, EventRecord)
        .join(EventRecord, EventRecord.id == RiskRecord.event_id)
        .order_by(desc(RiskRecord.risk_score))
        .limit(limit)
    ).all()

    points = []
    for risk, event in rows:
        if ALERT_ORDER.get(risk.alert_level, 0) < threshold:
            continue
        coords = _coords_for_event(event)
        points.append(
            {
                "event_id": event.id,
                "risk_id": risk.id,
                "risk": risk.risk_score,
                "level": risk.alert_level,
                "location": event.location,
                "lat": coords["lat"],
                "lng": coords["lng"],
            }
        )

    return {"items": points}


@router.post("/suppliers")
def upsert_supplier(
    name: str,
    country: str | None = None,
    importance: float = 0.5,
    db: Session = Depends(get_db),
) -> dict:
    existing = db.execute(select(Supplier).where(Supplier.name == name)).scalar_one_or_none()
    if existing:
        existing.country = country
        existing.importance = max(0.0, min(1.0, importance))
        db.commit()
        db.refresh(existing)
        return {
            "id": existing.id,
            "name": existing.name,
            "country": existing.country,
            "importance": existing.importance,
        }

    supplier = Supplier(
        name=name,
        country=country,
        importance=max(0.0, min(1.0, importance)),
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return {
        "id": supplier.id,
        "name": supplier.name,
        "country": supplier.country,
        "importance": supplier.importance,
    }


@router.get("/suppliers")
def list_suppliers(limit: int = 200, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(Supplier).order_by(Supplier.importance.desc()).limit(limit)).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "country": row.country,
                "importance": row.importance,
            }
            for row in rows
        ]
    }
