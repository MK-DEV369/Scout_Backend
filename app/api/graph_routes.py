from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventRecord, RiskRecord, Supplier
from app.db.session import get_db
from app.graph.neo4j_client import graph_service

router = APIRouter(tags=["graph"])


def _rows_from_relational(db: Session, limit: int) -> list[dict]:
    rows = db.execute(
        select(RiskRecord, EventRecord, Supplier)
        .join(EventRecord, EventRecord.id == RiskRecord.event_id)
        .outerjoin(Supplier, Supplier.id == RiskRecord.supplier_id)
        .order_by(RiskRecord.risk_score.desc())
        .limit(limit)
    ).all()

    payload: list[dict] = []
    for risk, event, supplier in rows:
        features = risk.feature_json or {}
        entities = event.entities_json or {}
        countries = entities.get("countries", []) if isinstance(entities, dict) else []
        ports = entities.get("ports", []) if isinstance(entities, dict) else []
        commodities = entities.get("commodities", []) if isinstance(entities, dict) else []

        payload.append(
            {
                "event_id": event.id,
                "event_type": event.category,
                "severity": float(event.severity),
                "timestamp": event.timestamp.isoformat(),
                "headline": (event.summary or event.category)[:240],
                "base_risk_score": float(features.get("base_risk_score", risk.risk_score)),
                "composite_risk_score": float(risk.risk_score),
                "country": countries[0] if countries else event.location,
                "port": ports[0] if ports else None,
                "commodity": commodities[0] if commodities else None,
                "supplier_id": supplier.id if supplier else None,
                "supplier_name": supplier.name if supplier else None,
                "supplier_country": supplier.country if supplier else None,
                "supplier_criticality": float(features.get("supplier_criticality", supplier.importance if supplier else 1.0)),
                "manufacturer_id": "default_manufacturer",
                "manufacturer_name": "SCOUT Manufacturer",
                "risk_exposure_score": float(features.get("risk_exposure_score", risk.risk_score)),
                "path_weight": float(features.get("path_weight", 1.0)),
                "affects_country_weight": 0.7,
                "affects_port_weight": 0.9,
                "affects_commodity_weight": 0.8,
                "located_in_weight": 0.7,
                "ships_through_weight": 0.8,
                "provides_weight": 0.8,
            }
        )

    return payload


@router.get("/impact/{event_id}")
def get_impact(event_id: int, manufacturer_id: str = Query(...), limit: int = 25) -> dict:
    if not graph_service.enabled:
        return {"enabled": False, "items": []}

    items = graph_service.get_impact(
        event_id=event_id,
        manufacturer_id=manufacturer_id,
        limit=limit,
    )
    return {"enabled": True, "items": items}


@router.get("/supplier-risk/{supplier_id}")
def get_supplier_risk(supplier_id: int, limit: int = 10) -> dict:
    if not graph_service.enabled:
        return {"enabled": False, "summary": {}, "events": []}

    result = graph_service.get_supplier_risk(supplier_id=supplier_id, limit=limit)
    result["enabled"] = True
    return result


@router.get("/graph-summary")
def graph_summary() -> dict:
    return graph_service.get_graph_summary()


@router.post("/sync")
def sync_graph(clear_existing: bool = False, limit: int = 1000, db: Session = Depends(get_db)) -> dict:
    if not graph_service.enabled:
        return {"enabled": False, "synced": 0, "message": "Neo4j is not configured"}

    if clear_existing:
        graph_service.clear_graph()

    rows = _rows_from_relational(db, limit=limit)
    if rows:
        graph_service.upsert_risk_paths_batch(rows)

    return {
        "enabled": True,
        "synced": len(rows),
        "cleared": clear_existing,
    }
