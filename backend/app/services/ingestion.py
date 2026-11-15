import hashlib
import logging
from datetime import date, datetime, timezone
from io import BytesIO
from contextlib import contextmanager
import fcntl
from pathlib import Path
from pypdf import PdfReader
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session
from app.models.entities import Company
from app.models.ingestion import (RawSnapshot, SecurityIdentifier, EodPrice, DocumentAsset,
                                  DocumentPage, FilingEvent, FilingOrigin, IngestionRun)
from app.providers.contracts import ProviderError, PrimaryDocument, Payload
from app.providers.http import CachedHttpFetcher
from app.providers.yahoo import YahooChartProvider
from app.providers.exchange_rss import ExchangeRssProvider
from app.providers.catalog import ReviewedCatalogProvider
from app.services.normalization import normalize_symbol, normalize_name, canonical_url, category_for, utc, IST

logger = logging.getLogger(__name__)

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

@contextmanager
def refresh_lock(data_dir: Path):
    """One SQLite ingester across local API/CLI processes; crash-safe OS lock."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "refresh.lock").open("a") as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProviderError("busy", "Another ingestion refresh is running; retry later") from exc
        try: yield
        finally: fcntl.flock(handle, fcntl.LOCK_UN)

class IngestionService:
    def __init__(self, db: Session, data_dir: Path, *, fetcher=None, prices=None, feeds=None, documents=None):
        self.db = db
        self.fetcher = fetcher or CachedHttpFetcher(db, data_dir)
        self.prices = prices or YahooChartProvider(self.fetcher)
        self.feeds = feeds if feeds is not None else [ExchangeRssProvider(name, self.fetcher) for name in ("nse_rss", "bse_rss")]
        from app.core.config import get_settings
        catalog_path = get_settings().primary_catalog_path
        self.documents = documents or (ReviewedCatalogProvider(catalog_path) if catalog_path else ReviewedCatalogProvider())

    def resolve(self, value: str) -> tuple[str, Company | None]:
        exchange, symbol = normalize_symbol(value)
        if exchange == "BSE":
            identifier = self.db.scalar(select(SecurityIdentifier).where(SecurityIdentifier.namespace == "bse", SecurityIdentifier.value == symbol))
            if not identifier: raise ProviderError("unmapped_bse", "BSE code has no verified NSE company mapping; no mapping was guessed")
            company = self.db.get(Company, identifier.company_id)
            return company.ticker, company
        company = self.db.scalar(select(Company).where(Company.ticker == symbol))
        return symbol, company

    def refresh(self, value: str, dataset: str, mode: str, start: date, end: date, force=False) -> IngestionRun:
        ticker, company = self.resolve(value)
        run = IngestionRun(ticker=ticker, dataset=dataset, mode=mode, status="running")
        self.db.add(run); self.db.commit(); self.db.refresh(run)
        run_id = run.id
        try:
            if dataset == "prices":
                if mode != "live": raise ProviderError("invalid_mode", "Price refresh uses live retrieval of historical daily observations")
                status, details = self.refresh_prices(ticker, company, start, end, force)
            elif dataset == "documents":
                if mode != "live": raise ProviderError("invalid_mode", "Use live document retrieval; historical documents keep their original dates")
                if not company: raise ProviderError("unknown_company", "Retrieve verified price identity first for an unregistered NSE company")
                status, details = self.refresh_documents(company, force)
            elif dataset == "filings":
                if not company: raise ProviderError("unknown_company", "Company identity must be registered before matching exchange filings")
                status, details = self.refresh_filings(company, mode, force)
            else: raise ProviderError("invalid_dataset", "Unknown dataset")
        except (ProviderError, ValueError) as exc:
            self.db.rollback()
            status, details = "failed", {"error_code": getattr(exc, "code", "invalid_input"), "message": str(exc)}
        except Exception:
            self.db.rollback()
            logger.exception("Ingestion failed for %s/%s", ticker, dataset)
            status, details = "failed", {"error_code": "internal_error", "message": "Ingestion failed; previous verified data has been retained. See server logs."}
        run = self.db.get(IngestionRun, run_id)
        run.status, run.details, run.completed_at = status, details, datetime.now(timezone.utc)
        self.db.commit(); self.db.refresh(run)
        return run

    def refresh_prices(self, ticker, company, start, end, force):
        batch = self.prices.history(ticker, start, end, force)
        if not batch.points:
            return "no_data", {"message": "No completed trading-day observations returned; existing records retained.", "skipped": batch.skipped,
                               "snapshot_id": batch.payload.snapshot_id, "source_url": batch.payload.url, "cache_status": batch.payload.cache_status}
        if company is None:
            company = Company(ticker=ticker, name=batch.company_name, sector="Unclassified", exchange="NSE", research_demo=False)
            self.db.add(company); self.db.flush()
        self._identifier(company.id, "yahoo", batch.symbol, batch.payload.url)
        inserted, updated = 0, 0
        for point in batch.points:
            row = self.db.scalar(select(EodPrice).where(EodPrice.company_id == company.id, EodPrice.trading_date == point.trading_date, EodPrice.provider == self.prices.name))
            if row is None:
                row = EodPrice(company_id=company.id, trading_date=point.trading_date, provider=self.prices.name)
                self.db.add(row); inserted += 1
            else: updated += 1
            for key in ("open", "high", "low", "close", "adjusted_close", "volume"): setattr(row, key, getattr(point, key))
            row.currency, row.snapshot_id, row.updated_at = batch.currency, batch.payload.snapshot_id, utc(batch.payload.fetched_at)
        self.db.commit()
        return ("stale" if batch.payload.cache_status == "stale" else "partial" if batch.skipped else "success"), {
            "provider": self.prices.name, "inserted": inserted, "updated": updated, "returned": len(batch.points), "skipped": batch.skipped,
            "start": start.isoformat(), "end_exclusive": end.isoformat(), "source_url": batch.payload.url,
            "snapshot_id": batch.payload.snapshot_id, "cache_status": batch.payload.cache_status, "warning": batch.payload.warning,
            "price_basis": "Provider daily OHLC (not total-return adjusted); adjusted close is stored separately; Yahoo may restate history for corporate actions."}

    def _identifier(self, company_id, namespace, value, evidence_url):
        old = self.db.scalar(select(SecurityIdentifier).where(SecurityIdentifier.namespace == namespace, SecurityIdentifier.value == value))
        if old and old.company_id != company_id: raise ProviderError("identity_conflict", "Identifier belongs to another company")
        if not old: self.db.add(SecurityIdentifier(company_id=company_id, namespace=namespace, value=value, evidence_url=evidence_url))

    def store_document(self, company: Company, candidate: PrimaryDocument, payload: Payload) -> DocumentAsset:
        if not payload.body.startswith(b"%PDF-"):
            raise ProviderError("not_pdf", "Source returned HTML or non-PDF content, not a primary PDF")
        old = self.db.scalar(select(DocumentAsset).where(DocumentAsset.company_id == company.id, DocumentAsset.sha256 == payload.sha256))
        if old: return old
        try:
            reader = PdfReader(BytesIO(payload.body))
            if reader.is_encrypted: raise ValueError("Encrypted PDF")
            if len(reader.pages) > 700: raise ValueError("PDF exceeds the 700-page parsing limit")
            pages, errors = [], []
            for i, page in enumerate(reader.pages, 1):
                try: pages.append((i, (page.extract_text() or "")[:200000]))
                except Exception: errors.append(i)
        except Exception as exc:
            raise ProviderError("pdf_parse_error", "Downloaded PDF could not be parsed safely") from exc
        text = " ".join(t for _, t in pages).casefold()
        if candidate.expected_text and not all(token.casefold() in text for token in candidate.expected_text):
            raise ProviderError("document_identity_mismatch", "Document did not contain the expected issuer/title identifiers")
        status = "partial" if errors else "extracted" if text.strip() else "needs_ocr"
        doc = DocumentAsset(company_id=company.id, sha256=payload.sha256, snapshot_id=payload.snapshot_id, kind=candidate.kind,
                            title=candidate.title, publisher=candidate.publisher, discovery_url=candidate.discovery_url,
                            published_date=candidate.published_date, date_basis=candidate.date_basis, period_end=candidate.period_end,
                            event_date=candidate.event_date, page_count=len(reader.pages), extraction_status=status,
                            extraction_error=f"Failed pages: {errors}" if errors else None)
        self.db.add(doc); self.db.flush()
        self.db.add_all([DocumentPage(document_id=doc.id, page_number=i, text=t) for i, t in pages])
        self.db.commit(); self.db.refresh(doc)
        # These identifiers must be explicitly printed in the actual retrieved PDF.
        if company.ticker == "RELIANCE" and "500325" in text and "reliance" in text:
            self._identifier(company.id, "bse", "500325", payload.url)
        if company.ticker == "TCS" and "532540" in text and "tata consultancy" in text:
            self._identifier(company.id, "bse", "532540", payload.url)
        self.db.commit()
        return doc

    def refresh_documents(self, company, force):
        candidates = self.documents.discover(company.ticker)
        if not candidates: return "no_data", {"message": "No reviewed primary-source URLs registered for this company. No URL or document was guessed.", "documents": []}
        results, errors, stale = [], [], False
        for candidate in candidates:
            try:
                payload = self.fetcher.get(candidate.url, 7 * 86400, force)
                doc = self.store_document(company, candidate, payload)
                stale |= payload.cache_status == "stale"
                results.append({"id": doc.id, "kind": doc.kind, "sha256": doc.sha256, "source_url": payload.url,
                                "cache_status": payload.cache_status, "warning": payload.warning, "extraction_status": doc.extraction_status})
            except ProviderError as exc:
                self.db.rollback()
                errors.append({"url": candidate.url, "error_code": exc.code, "message": str(exc)})
        return ("partial" if errors and results else "failed" if errors else "stale" if stale else "success"), {"documents": results, "errors": errors, "discovery": "reviewed exact issuer URLs; not exhaustive coverage"}

    def _store_filing(self, company, title, url, provider, raw_date, published_at, published_date, mode, document, feed_snapshot_id):
        external_id = digest(f"{company.id}|{canonical_url(url)}|{raw_date}")
        origin = self.db.scalar(select(FilingOrigin).where(FilingOrigin.provider == provider, FilingOrigin.external_id == external_id))
        if origin:
            # Promote link-only metadata if its attachment was unavailable on an earlier attempt.
            event = self.db.get(FilingEvent, origin.filing_id)
            if document and event.document_id != document.id:
                key = digest(f"{company.id}|{document.sha256}|{published_date}")
                target = self.db.scalar(select(FilingEvent).where(FilingEvent.dedup_key == key))
                if target and target.id != event.id:
                    self.db.execute(update(FilingOrigin).where(FilingOrigin.filing_id == event.id).values(filing_id=target.id))
                    self.db.delete(event)
                else:
                    event.document_id = document.id
                    event.dedup_key = key
            self.db.commit()
            return False
        identity = document.sha256 if document else canonical_url(url)
        key = digest(f"{company.id}|{identity}|{published_date}")
        event = self.db.scalar(select(FilingEvent).where(FilingEvent.dedup_key == key))
        if event and published_at and (event.published_at is None or utc(published_at) < utc(event.published_at)):
            event.published_at = published_at
            event.publication_precision = "second"
        if event is None:
            event = FilingEvent(company_id=company.id, dedup_key=key, document_id=document.id if document else None,
                                title=title, category=category_for(title), published_at=published_at, published_date=published_date,
                                publication_precision="second" if published_at else "date")
            self.db.add(event); self.db.flush()
        self.db.add(FilingOrigin(filing_id=event.id, provider=provider, external_id=external_id, source_url=canonical_url(url),
                                feed_snapshot_id=feed_snapshot_id, raw_published=raw_date, mode=mode))
        self.db.commit()
        return True

    def refresh_filings(self, company, mode, force):
        if mode == "replay":
            candidates = [c for c in self.documents.discover(company.ticker) if c.replay_announcement and c.published_date]
            results, errors = [], []
            for c in candidates:
                try:
                    p = self.fetcher.get(c.url, 7 * 86400, force)
                    doc = self.store_document(company, c, p)
                    inserted = self._store_filing(company, c.title, c.url, "issuer_archive", c.published_date.isoformat(), None, c.published_date, "replay", doc, None)
                    results.append({"document_id": doc.id, "inserted_origin": inserted, "source_url": p.url, "cache_status": p.cache_status})
                except ProviderError as exc:
                    self.db.rollback(); errors.append({"url": c.url, "error_code": exc.code, "message": str(exc)})
            return ("partial" if errors and results else "failed" if errors else "success" if results else "no_data"), {
                "mode": "replay", "label": "Historical replay — genuinely retrieved issuer-hosted exchange disclosures; original publication dates retained.",
                "items": results, "errors": errors, "coverage": "Selected historical records only; not a live feed or complete archive."}
        results, errors, warnings = [], [], []
        for provider in self.feeds:
            try:
                batch = provider.latest(force)
                matched, inserted = 0, 0
                for c in batch.items:
                    if c.bse_code:
                        mapped = self.db.scalar(select(SecurityIdentifier).where(SecurityIdentifier.namespace == "bse", SecurityIdentifier.value == c.bse_code))
                        matches = mapped.company_id == company.id if mapped else normalize_name(c.company_name) == normalize_name(company.name)
                        if matches and not mapped:
                            self._identifier(company.id, "bse", c.bse_code, batch.payload.url)
                            self.db.commit()
                    else: matches = normalize_name(c.company_name) == normalize_name(company.name)
                    if not matches: continue
                    matched += 1
                    published_date = c.published_at.astimezone(IST).date()
                    candidate = PrimaryDocument(company.ticker, c.title, self._document_kind(c.title), c.url, batch.payload.url, provider.name,
                                                published_date, "Exchange RSS pubDate (IST when offset absent).")
                    doc = None
                    try:
                        payload = self.fetcher.get(c.url, 7 * 86400, force)
                        doc = self.store_document(company, candidate, payload)
                    except ProviderError as exc:
                        self.db.rollback(); warnings.append({"url": c.url, "error_code": exc.code, "message": str(exc)})
                    inserted += self._store_filing(company, c.title, c.url, provider.name, c.raw_published, c.published_at, published_date,
                                                   "live", doc, batch.payload.snapshot_id)
                results.append({"provider": provider.name, "source_url": batch.payload.url, "snapshot_id": batch.payload.snapshot_id,
                                "cache_status": batch.payload.cache_status, "warning": batch.payload.warning,
                                "feed_items": len(batch.items), "matched": matched, "inserted_origins": inserted, "rejected": batch.rejected})
            except ProviderError as exc:
                self.db.rollback(); errors.append({"provider": provider.name, "error_code": exc.code, "message": str(exc)})
        status = "failed" if not results else "partial" if errors or warnings or any(r["rejected"] for r in results) else "stale" if any(r["cache_status"] == "stale" for r in results) else "success"
        return status, {"mode": "live", "providers": results, "errors": errors, "attachment_warnings": warnings,
                        "coverage": "Only items currently in the public RSS windows. Zero matches does not establish absence of announcements; no historical completeness guarantee."}

    @staticmethod
    def _document_kind(title):
        category = category_for(title)
        if "transcript" in title.casefold(): return "earnings_transcript"
        if category == "results": return "quarterly_results"
        if "annual report" in title.casefold(): return "annual_report"
        return "exchange_filing"
