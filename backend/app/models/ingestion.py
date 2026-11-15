"""Canonical ingestion tables. Additive to the original unpopulated foundation models."""
from datetime import date, datetime
from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.models.entities import now

class RawSnapshot(Base):
    __tablename__ = "ingestion_snapshots"
    __table_args__ = (UniqueConstraint("url", "sha256"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(100))
    byte_count: Mapped[int] = mapped_column()
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    response_headers: Mapped[dict] = mapped_column(JSON, default=dict)

class FetchCache(Base):
    __tablename__ = "ingestion_cache"
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_snapshots.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

class HostThrottle(Base):
    __tablename__ = "ingestion_host_throttle"
    host: Mapped[str] = mapped_column(String(200), primary_key=True)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SecurityIdentifier(Base):
    __tablename__ = "ingestion_identifiers"
    __table_args__ = (UniqueConstraint("namespace", "value"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    namespace: Mapped[str] = mapped_column(String(30))
    value: Mapped[str] = mapped_column(String(200))
    evidence_url: Mapped[str] = mapped_column(Text)

class EodPrice(Base):
    __tablename__ = "ingestion_eod_prices"
    __table_args__ = (UniqueConstraint("company_id", "trading_date", "provider"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    trading_date: Mapped[date] = mapped_column(Date)
    open: Mapped[str | None] = mapped_column(String(50))
    high: Mapped[str | None] = mapped_column(String(50))
    low: Mapped[str | None] = mapped_column(String(50))
    close: Mapped[str] = mapped_column(String(50))
    adjusted_close: Mapped[str | None] = mapped_column(String(50))
    volume: Mapped[int] = mapped_column()
    currency: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(50))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("ingestion_snapshots.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DocumentAsset(Base):
    __tablename__ = "ingestion_documents"
    __table_args__ = (UniqueConstraint("company_id", "sha256"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("ingestion_snapshots.id"))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(150))
    discovery_url: Mapped[str] = mapped_column(Text)
    published_date: Mapped[date | None] = mapped_column(Date)
    date_basis: Mapped[str] = mapped_column(Text)
    period_end: Mapped[date | None] = mapped_column(Date)
    event_date: Mapped[date | None] = mapped_column(Date)
    page_count: Mapped[int] = mapped_column(default=0)
    extraction_status: Mapped[str] = mapped_column(String(40), default="pending")
    extraction_error: Mapped[str | None] = mapped_column(Text)

class DocumentPage(Base):
    __tablename__ = "ingestion_document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("ingestion_documents.id"), index=True)
    page_number: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)

class FilingEvent(Base):
    __tablename__ = "ingestion_filings"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_documents.id"))
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    classification_basis: Mapped[str] = mapped_column(String(100), default="deterministic title rules; not materiality analysis")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_date: Mapped[date] = mapped_column(Date)
    publication_precision: Mapped[str] = mapped_column(String(20))

class FilingOrigin(Base):
    __tablename__ = "ingestion_filing_origins"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("ingestion_filings.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    feed_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_snapshots.id"))
    raw_published: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(40), index=True)
    dataset: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
