import hmac
import ipaddress
from datetime import date, datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Company
from app.models.ingestion import EodPrice, RawSnapshot, DocumentAsset, DocumentPage, FilingEvent, FilingOrigin, IngestionRun
from app.providers.http import CachedHttpFetcher
from app.providers.contracts import ProviderError
from app.services.ingestion import IngestionService, refresh_lock
from app.services.normalization import utc, IST, normalize_symbol


from app.core.access import workspace_access as local_data_access

router = APIRouter(prefix="/api/v1/data", tags=["Financial ingestion"], dependencies=[Depends(local_data_access)])

class RefreshRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=45)
    dataset: Literal["prices", "filings", "documents"]
    mode: Literal["live", "replay"] = "live"
    start: date = Field(default_factory=lambda: datetime.now(IST).date() - timedelta(days=90))
    end: date = Field(default_factory=lambda: datetime.now(IST).date())
    force: bool = False

    @model_validator(mode="after")
    def validate_request(self):
        normalize_symbol(self.ticker)
        if self.start >= self.end or (self.end - self.start).days > 3660:
            raise ValueError("Date range must be positive and at most ten years; end is exclusive")
        if self.end > datetime.now(IST).date(): raise ValueError("Future end dates are not supported")
        if self.mode == "replay" and self.dataset != "filings": raise ValueError("Replay mode is only for historical filings")
        return self

def authorize_refresh(x_finn_ingest_token: str | None = Header(default=None)):
    token = get_settings().ingest_token
    if not token or not token.get_secret_value(): raise HTTPException(503, "Set FINN_INGEST_TOKEN on the backend to enable API refresh; the local CLI also supports refresh")
    if not x_finn_ingest_token or not hmac.compare_digest(x_finn_ingest_token.encode(), token.get_secret_value().encode()):
        raise HTTPException(401, "Invalid ingestion token")

def service(db: Session = Depends(get_db)):
    return IngestionService(db, get_settings().data_dir)

def company_for(value: str, svc: IngestionService):
    try: _, company = svc.resolve(value)
    except (ValueError, ProviderError) as exc: raise HTTPException(422, str(exc)) from exc
    if company is None: raise HTTPException(404, "Unknown company; ingest a verified NSE price identity first")
    return company

def run_out(run):
    return {"id": run.id, "ticker": run.ticker, "dataset": run.dataset, "mode": run.mode, "status": run.status,
            "started_at": utc(run.started_at), "completed_at": utc(run.completed_at) if run.completed_at else None, "details": run.details}

def snapshot_out(s):
    return {"snapshot_id": s.id, "requested_url": s.url, "source_url": s.final_url, "sha256": s.sha256,
            "fetched_at": utc(s.fetched_at), "byte_count": s.byte_count, "media_type": s.media_type}

@router.post("/refresh", dependencies=[Depends(authorize_refresh)])
def refresh(body: RefreshRequest, svc: IngestionService = Depends(service)):
    try:
        with refresh_lock(get_settings().data_dir):
            return run_out(svc.refresh(body.ticker, body.dataset, body.mode, body.start, body.end, body.force))
    except (ValueError, ProviderError) as exc:
        raise HTTPException(409 if getattr(exc, "code", "") == "busy" else 422, str(exc)) from exc

@router.get("/runs")
def runs(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    return [run_out(r) for r in db.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit))]

@router.get("/companies/{ticker}/prices")
def prices(ticker: str, start: date | None = None, end: date | None = None, limit: int = Query(1000, ge=1, le=4000), svc: IngestionService = Depends(service)):
    company = company_for(ticker, svc)
    query = select(EodPrice, RawSnapshot).join(RawSnapshot, EodPrice.snapshot_id == RawSnapshot.id).where(EodPrice.company_id == company.id)
    if start: query = query.where(EodPrice.trading_date >= start)
    if end: query = query.where(EodPrice.trading_date < end)
    rows = svc.db.execute(query.order_by(EodPrice.trading_date.desc()).limit(limit)).all()
    return {"ticker": company.ticker, "count": len(rows), "end_exclusive": end, "coverage": "Stored observations only; gaps are not filled or inferred.",
            "items": [{"trading_date": r.trading_date, "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                       "adjusted_close": r.adjusted_close, "volume": r.volume, "currency": r.currency, "provider": r.provider,
                       "provenance": snapshot_out(s)} for r, s in rows]}

@router.get("/companies/{ticker}/documents")
def documents(ticker: str, kind: Literal["annual_report", "quarterly_results", "earnings_transcript", "exchange_filing"] | None = None, svc: IngestionService = Depends(service)):
    company = company_for(ticker, svc)
    query = select(DocumentAsset, RawSnapshot).join(RawSnapshot, DocumentAsset.snapshot_id == RawSnapshot.id).where(DocumentAsset.company_id == company.id)
    if kind: query = query.where(DocumentAsset.kind == kind)
    rows = svc.db.execute(query.order_by(DocumentAsset.id.desc())).all()
    return {"ticker": company.ticker, "count": len(rows), "coverage": "Retrieved documents only. Reviewed catalog and matched RSS attachments are not a complete company archive.",
            "items": [{"id": d.id, "title": d.title, "kind": d.kind, "publisher": d.publisher, "discovery_url": d.discovery_url,
                       "published_date": d.published_date, "date_basis": d.date_basis, "period_end": d.period_end, "event_date": d.event_date,
                       "page_count": d.page_count, "extraction_status": d.extraction_status, "extraction_error": d.extraction_error,
                       "provenance": snapshot_out(s)} for d, s in rows]}

@router.get("/documents/{document_id}/pages/{page_number}")
def page(document_id: int, page_number: int, db: Session = Depends(get_db)):
    if get_settings().access_mode != 'local':
        raise HTTPException(403, 'Full source-page export is disabled in the public demo; open the original citation')
    row = db.scalar(select(DocumentPage).where(DocumentPage.document_id == document_id, DocumentPage.page_number == page_number))
    if row is None: raise HTTPException(404, "Page not found or text extraction unavailable")
    doc = db.get(DocumentAsset, document_id)
    return {"document_id": document_id, "page": page_number, "text": row.text, "provenance": snapshot_out(db.get(RawSnapshot, doc.snapshot_id)),
            "note": "Deterministic PDF text extraction; no AI analysis. Tables may require layout-aware extraction before numeric analysis."}

@router.get("/documents/{document_id}/file")
def file(document_id: int, db: Session = Depends(get_db)):
    if get_settings().access_mode != 'local':
        raise HTTPException(403, 'Raw PDF redistribution is disabled; open the original issuer citation')
    doc = db.get(DocumentAsset, document_id)
    if doc is None: raise HTTPException(404, "Document not found")
    snapshot = db.get(RawSnapshot, doc.snapshot_id)
    try: body = CachedHttpFetcher(db, get_settings().data_dir).body(snapshot)
    except ProviderError as exc: raise HTTPException(503, str(exc)) from exc
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="document-{document_id}.pdf"', "X-Content-SHA256": doc.sha256, "Cache-Control": "private, max-age=3600"})

@router.get("/companies/{ticker}/filings")
def filings(ticker: str, mode: Literal["live", "replay"] = "live", start: date | None = None, end: date | None = None,
            limit: int = Query(100, ge=1, le=500), svc: IngestionService = Depends(service)):
    company = company_for(ticker, svc)
    query = select(FilingEvent).where(FilingEvent.company_id == company.id,
        FilingEvent.id.in_(select(FilingOrigin.filing_id).where(FilingOrigin.mode == mode)))
    if start: query = query.where(FilingEvent.published_date >= start)
    if end: query = query.where(FilingEvent.published_date < end)
    events = svc.db.scalars(query.order_by(FilingEvent.published_date.desc(), FilingEvent.id.desc()).limit(limit)).all()
    return {"ticker": company.ticker, "mode": mode, "label": "Historical replay" if mode == "replay" else "Recent public RSS observations",
            "coverage": "Incomplete source windows; no matches does not mean no announcements.", "count": len(events),
            "items": [{"id": e.id, "title": e.title, "category": e.category, "classification_basis": e.classification_basis,
                       "published_at": utc(e.published_at) if e.published_at else None, "published_date": e.published_date,
                       "publication_precision": e.publication_precision, "document_id": e.document_id,
                       "origins": [{"provider": o.provider, "source_url": o.source_url, "raw_published": o.raw_published,
                                    "mode": o.mode, "feed_snapshot_id": o.feed_snapshot_id, "retrieved_at": utc(o.retrieved_at)}
                                   for o in svc.db.scalars(select(FilingOrigin).where(FilingOrigin.filing_id == e.id))]}
                      for e in events]}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    latest = {}
    for run in db.scalars(select(IngestionRun).order_by(IngestionRun.id.desc())):
        latest.setdefault(f"{run.ticker}:{run.dataset}:{run.mode}", run_out(run))
    return {"usage": "restricted educational review; no public raw-source redistribution", "llm": "configured" if get_settings().llm_enabled and get_settings().llm_model and get_settings().llm_api_key else "not_configured",
            "counts": {name: db.scalar(select(func.count()).select_from(model)) for name, model in
                       [("prices", EodPrice), ("documents", DocumentAsset), ("filings", FilingEvent), ("raw_snapshots", RawSnapshot)]},
            "latest_runs": list(latest.values()), "coverage": "RSS is a limited recent window. Primary-source catalog coverage is explicit and incomplete."}
