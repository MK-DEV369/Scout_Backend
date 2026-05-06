from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import EventRecord, RiskRecord, Supplier
from app.graph.neo4j_client import graph_service
from app.risk.engine import compute_risk_score


def _supplier_for_event(db: Session, event: EventRecord) -> Supplier | None:
    company_names = event.entities_json.get("companies", [])
    if company_names:
        company = company_names[0]
        supplier = db.execute(select(Supplier).where(Supplier.name == company)).scalar_one_or_none()
        if supplier:
            return supplier
        supplier = Supplier(
            name=company,
            country=event.location or (event.entities_json.get("countries", [None])[0]),
            importance=0.5,
        )
        db.add(supplier)
        db.flush()
        return supplier
    return None


def _alert_level(score: float) -> str:
    if score < 0.4:
        return "Low"
    if score < 0.6:
        return "Medium"
    if score < 0.8:
        return "High"
    return "Critical"


def score_events(db: Session, limit: int = 100) -> dict[str, int]:
    scored_ids = {row[0] for row in db.execute(select(RiskRecord.event_id)).all()}
    events = db.execute(select(EventRecord).order_by(desc(EventRecord.timestamp)).limit(limit)).scalars().all()

    created = 0
    skipped = 0
    graph_rows: list[dict] = []

    for event in events:
        if event.id in scored_ids:
            skipped += 1
            continue

        supplier = _supplier_for_event(db, event)

        relevance = 0.8 if event.location else 0.5
        supplier_importance = supplier.importance if supplier else 0.5

        risk = compute_risk_score(
            category=event.category,
            timestamp=event.timestamp,
            source=event.source,
            relevance=relevance,
            supplier_importance=supplier_importance,
            severity_override=event.severity,
        )

        countries = event.entities_json.get("countries", [])
        ports = event.entities_json.get("ports", [])
        commodities = event.entities_json.get("commodities", [])
        supplier_criticality = round((supplier.importance * 1.5) + 0.5, 4) if supplier else 1.0

        path_weight = 1.0
        if graph_service.enabled and supplier:
            path_weight = graph_service.estimate_path_weight(event_id=event.id, supplier_id=supplier.id)

        base_risk_score = float(risk["risk_score"])
        composite_risk_score = min(1.0, base_risk_score * path_weight * supplier_criticality)
        composite_alert_level = _alert_level(composite_risk_score)

        graph_rows.append(
            {
                "event_id": event.id,
                "event_type": event.category,
                "severity": float(event.severity),
                "timestamp": event.timestamp.isoformat(),
                "headline": event.summary[:240],
                "base_risk_score": base_risk_score,
                "composite_risk_score": composite_risk_score,
                "country": countries[0] if countries else event.location,
                "port": ports[0] if ports else None,
                "commodity": commodities[0] if commodities else None,
                "supplier_id": supplier.id if supplier else None,
                "supplier_name": supplier.name if supplier else None,
                "supplier_country": supplier.country if supplier else None,
                "supplier_criticality": supplier_criticality,
                "manufacturer_id": "default_manufacturer",
                "manufacturer_name": "SCOUT Manufacturer",
                "risk_exposure_score": composite_risk_score,
                "path_weight": path_weight,
                "affects_country_weight": 0.7,
                "affects_port_weight": 0.9,
                "affects_commodity_weight": 0.8,
                "located_in_weight": 0.7,
                "ships_through_weight": 0.8,
                "provides_weight": 0.8,
            }
        )

        item = RiskRecord(
            event_id=event.id,
            supplier_id=supplier.id if supplier else None,
            risk_score=composite_risk_score,
            alert_level=composite_alert_level,
            feature_json={
                "base_risk_score": base_risk_score,
                "path_weight": path_weight,
                "supplier_criticality": supplier_criticality,
                "risk_exposure_score": composite_risk_score,
                "severity": risk["severity"],
                "recency": risk["recency"],
                "credibility": risk["credibility"],
                "relevance": risk["relevance"],
                "supplier_importance": risk["supplier_importance"],
            },
        )
        db.add(item)
        created += 1

    if graph_rows and graph_service.enabled:
        graph_service.upsert_risk_paths_batch(graph_rows)

    db.commit()
    return {"created": created, "skipped": skipped}
