"""Rebuild an ephemeral review workspace from reviewed real sources; never call an LLM."""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.seed import DEMO_OWNER
from app.models.entities import Company, PortfolioHolding
from app.services.ingestion import IngestionService, refresh_lock
from app.services.normalization import IST

bootstrap_state = {'status': 'disabled', 'completed_jobs': 0, 'failed_jobs': 0}

def rebuild():
    settings = get_settings()
    bootstrap_state.update(status='running', completed_jobs=0, failed_jobs=0)
    with SessionLocal() as db:
        symbols = db.scalars(select(Company.ticker).join(PortfolioHolding).where(PortfolioHolding.owner_id == DEMO_OWNER).order_by(Company.ticker)).all()
    jobs = [(t, 'prices', 'live') for t in symbols]
    jobs += [('RELIANCE', 'documents', 'live'), ('TCS', 'documents', 'live'), ('PIDILITIND', 'documents', 'live'), ('RELIANCE', 'filings', 'replay'), ('PIDILITIND', 'filings', 'replay')]
    end = datetime.now(IST).date()
    for ticker, dataset, mode in jobs:
        try:
            with refresh_lock(settings.data_dir), SessionLocal() as db:
                run = IngestionService(db, settings.data_dir).refresh(ticker, dataset, mode, end-timedelta(days=120), end)
                if run.status in {'failed', 'partial', 'stale', 'no_data'}:
                    bootstrap_state['failed_jobs'] += 1
        except Exception:
            bootstrap_state['failed_jobs'] += 1
        bootstrap_state['completed_jobs'] += 1
    bootstrap_state.update(status='partial' if bootstrap_state['failed_jobs'] else 'complete', completed_at=datetime.now(timezone.utc).isoformat())

async def start_bootstrap():
    await asyncio.to_thread(rebuild)
