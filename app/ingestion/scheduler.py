import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.ingestion.service import ingestion_service

scheduler = AsyncIOScheduler()
logger = logging.getLogger(__name__)


async def run_ingestion_job() -> dict:
    try:
        records, source_counts, errors = await asyncio.wait_for(
            ingestion_service.collect_with_stats(),
            timeout=settings.ingestion_job_timeout_seconds,
        )
    except TimeoutError:
        logger.warning("Ingestion collect timed out after %s seconds", settings.ingestion_job_timeout_seconds)
        return {
            "fetched_total": 0,
            "inserted": 0,
            "duplicates": 0,
            "fallback_saved": 0,
            "error_count": 1,
            "source_counts": {},
            "errors": [{"source": "scheduler", "error": "ingestion job timeout"}],
        }

    try:
        with SessionLocal() as db:
            save_result = ingestion_service.save(db, records)
    except Exception as exc:  # noqa: BLE001
        fallback_saved = ingestion_service.save_fallback(records, reason=f"db_session_error:{exc}")
        logger.exception("DB session failed during ingestion job", exc_info=exc)
        save_result = {
            "inserted": 0,
            "duplicates": 0,
            "fallback_saved": fallback_saved,
            "db_error": str(exc),
        }

    return {
        "fetched_total": len(records),
        "inserted": save_result["inserted"],
        "duplicates": save_result["duplicates"],
        "fallback_saved": save_result.get("fallback_saved", 0),
        "db_error": save_result.get("db_error"),
        "error_count": len(errors),
        "source_counts": source_counts,
        "errors": errors,
    }


def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        run_ingestion_job,
        trigger="interval",
        minutes=settings.ingestion_interval_minutes,
        id="ingestion_job",
        replace_existing=True,
    )
    scheduler.start()
