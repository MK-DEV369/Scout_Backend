from datetime import datetime, timezone
import httpx
from app.core.config import settings
from app.ingestion.connectors.base import SourceConnector
from app.ingestion.schema import NormalizedRecord


class WorldBankConnector(SourceConnector):
    name = "worldbank"

    async def fetch(self) -> list[NormalizedRecord]:
        indicators = ["CM.MKT.CRUD.WTI", "CM.MKT.MAIZ.CB", "CM.MKT.WHEA.US"]
        records: list[NormalizedRecord] = []

        async with httpx.AsyncClient(timeout=20) as client:
            for indicator in indicators:
                url = f"{settings.world_bank_base_url}/country/WLD/indicator/{indicator}"
                response = await client.get(url, params={"format": "json", "per_page": 5})
                response.raise_for_status()
                payload = response.json()
                points = payload[1] if isinstance(payload, list) and len(payload) > 1 else []

                for point in points:
                    value = point.get("value")
                    date = point.get("date")
                    if value is None or not date:
                        continue
                    try:
                        timestamp = datetime(int(date), 1, 1, tzinfo=timezone.utc)
                    except ValueError:
                        timestamp = datetime.now(timezone.utc)

                    records.append(
                        NormalizedRecord.with_defaults(
                            source=self.name,
                            source_id=f"{indicator}:{date}",
                            text=f"Commodity {indicator} price/value {value} in {date}",
                            timestamp=timestamp,
                            location="Global",
                            metadata={"indicator": indicator, "value": value, "date": date},
                        )
                    )

        return records
