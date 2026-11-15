"""Provider contracts: implementations must return provenance, never inferred observations."""
from dataclasses import dataclass
from typing import Protocol
from datetime import date

@dataclass(frozen=True)
class DocumentCandidate:
    url: str
    kind: str
    publisher: str

@dataclass(frozen=True)
class PriceObservation:
    trading_date: date
    close_decimal: str
    volume: int
    provider: str

class MarketDataProvider(Protocol):
    async def history(self, ticker: str, start: date, end: date) -> list[PriceObservation]: ...

class PrimarySourceProvider(Protocol):
    async def discover(self, ticker: str) -> list[DocumentCandidate]: ...

class AnalysisModel(Protocol):
    async def analyze(self, question: str, evidence: list[dict]) -> dict: ...

class ResearchRepository(Protocol):
    def create_unavailable(self, owner_id: str, ticker: str, question: str) -> int: ...
