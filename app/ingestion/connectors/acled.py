from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.ingestion.connectors.base import SourceConnector
from app.ingestion.schema import NormalizedRecord


class ACLEDConnector(SourceConnector):
    name = "acled"

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def _get_access_token(self, client: httpx.AsyncClient) -> str | None:
        # Explicit token from env takes precedence.
        if settings.acled_access_token:
            return settings.acled_access_token

        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return self._access_token

        if not settings.acled_username or not settings.acled_password:
            return None

        response = await client.post(
            settings.acled_auth_url,
            data={
                "username": settings.acled_username,
                "password": settings.acled_password,
                "grant_type": "password",
                "client_id": settings.acled_client_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            return None

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not access_token:
            return None

        self._access_token = access_token
        # Renew one minute earlier to avoid edge expiries.
        buffer_seconds = 60 if expires_in > 60 else 0
        self._token_expires_at = now + timedelta(seconds=max(expires_in - buffer_seconds, 0))
        return self._access_token

    async def fetch(self) -> list[NormalizedRecord]:
        params = {"limit": 100, "event_date_where": ">=", "event_date": "2025-01-01"}
        async with httpx.AsyncClient(timeout=20) as client:
            token = await self._get_access_token(client)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            response = await client.get(settings.acled_base_url, params=params, headers=headers)
            if response.status_code >= 400:
                return []
            payload = response.json()

        records: list[NormalizedRecord] = []
        for event in payload.get("data", []):
            event_date = event.get("event_date")
            timestamp = datetime.now(timezone.utc)
            if event_date:
                try:
                    timestamp = datetime.strptime(event_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            text = " ".join(
                [
                    event.get("event_type") or "",
                    event.get("sub_event_type") or "",
                    event.get("notes") or "",
                ]
            ).strip()
            if not text:
                continue

            records.append(
                NormalizedRecord.with_defaults(
                    source=self.name,
                    source_id=event.get("event_id_cnty"),
                    text=text,
                    timestamp=timestamp,
                    location=event.get("location") or event.get("country"),
                    metadata=event,
                )
            )
        return records
