from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.ingestion.connectors.base import SourceConnector
from app.ingestion.schema import NormalizedRecord


class GDELTConnector(SourceConnector):
    name = "gdelt"

    async def fetch(self) -> list[NormalizedRecord]:
        params = {
            "query": "(supply chain OR shipping OR commodity)",
            "mode": "ArtList",
            "maxrecords": 50,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(settings.gdelt_base_url, params=params)
            response.raise_for_status()
            data = response.json()

        records: list[NormalizedRecord] = []
        for article in data.get("articles", []):
            text = article.get("title") or article.get("seendate") or ""
            if not text:
                continue
            dt_raw = article.get("seendate")
            timestamp = datetime.now(timezone.utc)
            if dt_raw:
                try:
                    timestamp = datetime.strptime(dt_raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            records.append(
                NormalizedRecord.with_defaults(
                    source=self.name,
                    source_id=article.get("url"),
                    text=f"{article.get('title', '')} {article.get('socialimage', '')}".strip(),
                    timestamp=timestamp,
                    location=article.get("sourcecountry"),
                    metadata={
                        "url": article.get("url"),
                        "language": article.get("language"),
                    },
                )
            )
        return records
