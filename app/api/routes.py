from fastapi import APIRouter, Depends
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.db.models import UnifiedRecord
from app.db.session import engine, get_db
from app.graph.neo4j_client import graph_service
from app.ingestion.service import ingestion_service
from app.ingestion.scheduler import run_ingestion_job

router = APIRouter()


@router.get("/health")
def health() -> dict:
    db_status = "disconnected"
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)

    neo4j_status = "disabled"
    neo4j_error = None
    if graph_service.enabled and graph_service.driver is not None:
        try:
            with graph_service.driver.session(database=graph_service.database) as session:
                session.run("RETURN 1 AS ok").single()
            neo4j_status = "connected"
        except Exception as exc:  # noqa: BLE001
            neo4j_status = "disconnected"
            neo4j_error = str(exc)

    ingestion_ready = db_status == "connected" or ingestion_service.fallback_path.parent.exists()

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "db": db_status,
        "neo4j": neo4j_status,
        "ingestion": "ready" if ingestion_ready else "not_ready",
        "errors": {
            "db": db_error,
            "neo4j": neo4j_error,
        },
    }


@router.post("/ingestion/run")
async def run_ingestion() -> dict:
    return await run_ingestion_job()


@router.get("/records")
def list_records(limit: int = 100, db: Session = Depends(get_db)) -> dict[str, list[dict]]:
    query = select(UnifiedRecord).order_by(desc(UnifiedRecord.timestamp)).limit(limit)
    rows = db.execute(query).scalars().all()
    payload = [
        {
            "id": row.id,
            "source": row.source,
            "timestamp": row.timestamp.isoformat(),
            "text": row.text,
            "location": row.location,
            "metadata": row.metadata_json,
            "content_hash": row.content_hash,
        }
        for row in rows
    ]
    return {"items": payload}
