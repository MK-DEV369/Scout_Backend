from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.ingestion.connectors.base import SourceConnector
from app.ingestion.schema import NormalizedRecord


class FREDConnector(SourceConnector):
    name = "fred"

    async def fetch(self) -> list[NormalizedRecord]:
        if not settings.fred_api_key:
            return []

        series = ["CPIAUCSL", "UNRATE", "FEDFUNDS"]
        records: list[NormalizedRecord] = []

        async with httpx.AsyncClient(timeout=20) as client:
            for series_id in series:
                response = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": settings.fred_api_key,
                        "file_type": "json",
                        "limit": 10,
                        "sort_order": "desc",
                    },
                )
                response.raise_for_status()
                payload = response.json()

                for obs in payload.get("observations", []):
                    value = obs.get("value")
                    date = obs.get("date")
                    if not date or value in (None, "."):
                        continue

                    try:
                        timestamp = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        timestamp = datetime.now(timezone.utc)

                    records.append(
                        NormalizedRecord.with_defaults(
                            source=self.name,
                            source_id=f"{series_id}:{date}",
                            text=f"FRED {series_id} = {value} at {date}",
                            timestamp=timestamp,
                            location="US",
                            metadata={"series_id": series_id, "value": value, "date": date},
                        )
                    )

        return records
