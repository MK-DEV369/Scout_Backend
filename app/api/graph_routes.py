from fastapi import APIRouter, Query

from app.graph.neo4j_client import graph_service

router = APIRouter(tags=["graph"])


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
