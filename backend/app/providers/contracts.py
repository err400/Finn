from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

@dataclass
class Payload:
    snapshot_id: int
    body: bytes
    url: str
    sha256: str
    fetched_at: datetime
    cache_status: str
    warning: str | None = None

class Fetcher(Protocol):
    def get(self, url: str, ttl_seconds: int, force: bool = False) -> Payload: ...

@dataclass
class PricePoint:
    trading_date: date
    open: str | None
    high: str | None
    low: str | None
    close: str
    adjusted_close: str | None
    volume: int

@dataclass
class PriceBatch:
    symbol: str
    company_name: str
    currency: str
    points: list[PricePoint]
    payload: Payload
    skipped: int = 0

class EodProvider(Protocol):
    name: str
    def history(self, ticker: str, start: date, end: date, force: bool = False) -> PriceBatch: ...

@dataclass
class FilingCandidate:
    company_name: str
    title: str
    url: str
    raw_published: str
    published_at: datetime
    bse_code: str | None = None

@dataclass
class FilingBatch:
    items: list[FilingCandidate]
    payload: Payload
    rejected: int = 0

class FilingProvider(Protocol):
    name: str
    def latest(self, force: bool = False) -> FilingBatch: ...

@dataclass
class PrimaryDocument:
    ticker: str
    title: str
    kind: str
    url: str
    discovery_url: str
    publisher: str
    published_date: date | None = None
    date_basis: str = "Publication date unknown; not inferred from the reporting period or HTTP headers."
    period_end: date | None = None
    event_date: date | None = None
    replay_announcement: bool = False
    expected_text: list[str] = field(default_factory=list)

class DocumentProvider(Protocol):
    def discover(self, ticker: str) -> list[PrimaryDocument]: ...
