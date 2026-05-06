from abc import ABC, abstractmethod

from app.ingestion.schema import NormalizedRecord


class SourceConnector(ABC):
    name: str

    @abstractmethod
    async def fetch(self) -> list[NormalizedRecord]:
        raise NotImplementedError
