from datetime import date, datetime
from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.models.entities import now

class NetworkProfile(Base):
    __tablename__ = "network_profiles"
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), primary_key=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    bio: Mapped[str] = mapped_column(Text)
    last_contact_date: Mapped[date | None] = mapped_column(Date)

class Education(Base):
    __tablename__ = "network_education"
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    institution: Mapped[str] = mapped_column(String(150))
    qualification: Mapped[str] = mapped_column(String(150))
    start_year: Mapped[int] = mapped_column()
    end_year: Mapped[int] = mapped_column()

class RelationshipEdge(Base):
    __tablename__ = "network_edges"
    __table_args__ = (UniqueConstraint("owner_id", "source_key", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    source_key: Mapped[str] = mapped_column(String(64))  # investor or contact ID
    target_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    relationship: Mapped[str] = mapped_column(String(100))
    strength: Mapped[int] = mapped_column()  # synthetic ordinal 1-5, not probability
    provenance: Mapped[str] = mapped_column(Text)

class CompanyPeer(Base):
    __tablename__ = "network_company_peers"
    __table_args__ = (UniqueConstraint("company_id", "peer_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    peer_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    relationship: Mapped[str] = mapped_column(String(50))
    provenance: Mapped[str] = mapped_column(Text)

class AlertRule(Base):
    __tablename__ = "push_alert_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    ticker: Mapped[str | None] = mapped_column(String(40))
    threshold: Mapped[str | None] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(20), default="absolute")
    lookback: Mapped[int] = mapped_column(default=20)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AlertEvent(Base):
    __tablename__ = "push_alert_events"
    __table_args__ = (UniqueConstraint("rule_id", "observation_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("push_alert_rules.id"))
    observation_key: Mapped[str] = mapped_column(String(150))
    ticker: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(30))
    observed_date: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    mode: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[dict] = mapped_column(JSON)

class FilingInsight(Base):
    __tablename__ = "push_filing_insights"
    filing_id: Mapped[int] = mapped_column(ForeignKey("ingestion_filings.id"), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ResearchChunk(Base):
    __tablename__ = "research_chunks"
    __table_args__ = (UniqueConstraint("document_id", "page_number", "ordinal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("ingestion_documents.id"), index=True)
    page_number: Mapped[int] = mapped_column()
    ordinal: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    index_version: Mapped[str] = mapped_column(String(30), default="page-window-v1")

class ResearchCache(Base):
    __tablename__ = "research_answer_cache"
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
