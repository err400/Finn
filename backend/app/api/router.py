from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from datetime import datetime, timedelta, timezone
from app.models.ingestion import IngestionRun, FilingEvent, FilingOrigin
from app.api.ingestion import local_data_access
from app.services.normalization import utc
from app.core.config import get_settings
from app.providers.llm import OpenAICompatibleModel
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.seed import DEMO_OWNER
from app.models.entities import Company, PortfolioHolding
from app.schemas.api import CompanyOut, ResearchRequest
from app.services.network import find_contacts
from app.services.rag import RagResearchService
from app.services.bootstrap import bootstrap_state
from app.providers.contracts import ProviderError
import threading

research_slot = threading.BoundedSemaphore(1)

router = APIRouter(prefix="/api/v1")

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    providers = {}
    for label, dataset in [("market", "prices"), ("filings", "filings"), ("fundamentals", "documents")]:
        latest = db.scalar(select(IngestionRun).where(IngestionRun.dataset == dataset).order_by(IngestionRun.id.desc()).limit(1))
        providers[label] = {"last_refresh_status": latest.status, "last_refresh_at": utc(latest.completed_at) if latest.completed_at else None} if latest else "not_connected"
    model = OpenAICompatibleModel(get_settings())
    providers["llm"] = {"configured": model.configured, "model": get_settings().llm_model if model.configured else None, "adapter": "openai_compatible"}
    return {"status": "ok", "database": "ok", "mode": "synthetic_network_demo", "providers": providers,
            "access_mode": get_settings().access_mode, "ephemeral_storage": get_settings().ephemeral_storage,
            "bootstrap": dict(bootstrap_state)}

@router.get("/portfolio", response_model=list[CompanyOut], dependencies=[Depends(local_data_access)])
def portfolio(db: Session = Depends(get_db)):
    return db.scalars(select(Company).join(PortfolioHolding).where(PortfolioHolding.owner_id == DEMO_OWNER).order_by(Company.ticker)).all()

@router.get("/companies", response_model=list[CompanyOut], dependencies=[Depends(local_data_access)])
def companies(q: str = Query(default="", max_length=100), db: Session = Depends(get_db)):
    query = select(Company)
    if q:
        query = query.where(Company.ticker.icontains(q, autoescape=True) | Company.name.icontains(q, autoescape=True))
    return db.scalars(query.order_by(Company.ticker)).all()

@router.get("/research/demo-companies", response_model=list[CompanyOut], dependencies=[Depends(local_data_access)])
def demos(db: Session = Depends(get_db)):
    return db.scalars(select(Company).where(Company.research_demo.is_(True))).all()

@router.post("/research", status_code=201, dependencies=[Depends(local_data_access)])
def research(body: ResearchRequest, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    if not research_slot.acquire(blocking=False):
        raise HTTPException(429, 'Another research request is running. Retry shortly.', headers={'Retry-After': '15'})
    try:
        return RagResearchService(db, DEMO_OWNER).research(body.ticker, body.question, body.workflow)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(422, str(exc)) from exc
    except ProviderError as exc:
        from fastapi import HTTPException
        raise HTTPException(422, str(exc)) from exc
    finally:
        research_slot.release()


@router.get("/network", dependencies=[Depends(local_data_access)])
def network(ticker: str | None = Query(default=None, max_length=40), db: Session = Depends(get_db)):
    return {"synthetic": True, "contacts": find_contacts(db, DEMO_OWNER, ticker)}

@router.get("/briefing", dependencies=[Depends(local_data_access)])
def briefing(db: Session = Depends(get_db)):
    last_run = db.scalar(select(IngestionRun).where(IngestionRun.dataset == "filings", IngestionRun.mode == "live").order_by(IngestionRun.id.desc()).limit(1))
    if last_run is None:
        return {"status": "sources_not_connected", "items": [], "message": "No live exchange RSS refresh has run. Historical replay is available separately through the data API."}
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    events = db.scalars(select(FilingEvent).join(Company, FilingEvent.company_id == Company.id).join(PortfolioHolding).where(
        PortfolioHolding.owner_id == DEMO_OWNER, FilingEvent.published_at >= since,
        FilingEvent.id.in_(select(FilingOrigin.filing_id).where(FilingOrigin.mode == "live"))).order_by(FilingEvent.published_at.desc())).all()
    return {"status": last_run.status, "items": [{"id": e.id, "title": e.title, "category": e.category, "published_at": utc(e.published_at),
            "document_id": e.document_id, "network": find_contacts(db, DEMO_OWNER, db.get(Company, e.company_id).ticker)} for e in events],
            "message": f"{len(events)} stored portfolio filing(s) published in the last 24 hours. RSS coverage is incomplete; see data refresh status for failures and freshness. No AI analysis generated."}
