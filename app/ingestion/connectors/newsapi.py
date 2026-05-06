from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.ingestion.connectors.base import SourceConnector
from app.ingestion.schema import NormalizedRecord


class NewsAPIConnector(SourceConnector):
    name = "newsapi"

    async def fetch(self) -> list[NormalizedRecord]:
        if not settings.newsapi_key:
            return []

        params = {
            "q": "supply chain OR commodity OR conflict",
            "language": "en",
            "pageSize": 50,
            "sortBy": "publishedAt",
            "apiKey": settings.newsapi_key,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://newsapi.org/v2/everything", params=params)
            response.raise_for_status()
            data = response.json()

        records: list[NormalizedRecord] = []
        for article in data.get("articles", []):
            body_text = " ".join(
                [
                    article.get("title") or "",
                    article.get("description") or "",
                    article.get("content") or "",
                ]
            ).strip()
            if not body_text:
                continue

            ts_raw = article.get("publishedAt")
            timestamp = datetime.now(timezone.utc)
            if ts_raw:
                try:
                    timestamp = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    pass

            records.append(
                NormalizedRecord.with_defaults(
                    source=self.name,
                    source_id=article.get("url"),
                    text=body_text,
                    timestamp=timestamp,
                    location=article.get("source", {}).get("name"),
                    metadata={
                        "author": article.get("author"),
                        "url": article.get("url"),
                    },
                )
            )

        return records
