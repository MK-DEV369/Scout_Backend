from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.ingestion.connectors.base import SourceConnector
from app.ingestion.schema import NormalizedRecord


class FreightosConnector(SourceConnector):
    """Connector for Freightos APIs (CO2 calculator).

    Uses `x-apikey` header for authentication and supports:
    - GET https://api.freightos.com/api/v1/co2hc (health/info)
    - POST https://api.freightos.com/api/v1/co2calc (calculate emissions)
    """

    name = "freightos"
    base_url = "https://api.freightos.com/api/v1"

    def _auth_headers(self) -> dict:
        if not settings.freightos_api_key:
            raise RuntimeError("FREIGHTOS_API_KEY is not configured")
        return {"x-apikey": settings.freightos_api_key, "Content-Type": "application/json"}

    async def fetch(self) -> list[NormalizedRecord]:
        """Fetch basic Freightos CO2 service info from `/co2hc` and return as records."""
        headers = self._auth_headers()
        url = f"{self.base_url}/co2hc"

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        entries = payload if isinstance(payload, list) else [payload]
        records: list[NormalizedRecord] = []
        now = datetime.now(timezone.utc)

        for i, item in enumerate(entries[:10]):
            text = f"Freightos CO2 service info: {item.get('message') or item.get('status') or 'info'}"
            records.append(
                NormalizedRecord.with_defaults(
                    source=self.name,
                    source_id=str(item.get("id", i)),
                    text=text,
                    timestamp=now,
                    location=None,
                    metadata=item,
                )
            )

        return records

    async def calculate_emissions(self, shipment: dict) -> dict:
        """Call Freightos `/co2calc` endpoint with a shipment payload and return the API response.

        Example payloads (FCL / LCL) are supported as provided in the API docs.
        """
        headers = self._auth_headers()
        url = f"{self.base_url}/co2calc"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=shipment)
            response.raise_for_status()
            return response.json()
