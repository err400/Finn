"""Read-only product view over existing verified records; never fetches or invents data."""
from datetime import datetime,timedelta,timezone
from collections import defaultdict
from decimal import Decimal
from fastapi import APIRouter,Depends
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.api.ingestion import local_data_access
from app.db.session import get_db
from app.db.seed import DEMO_OWNER
from app.models.entities import Company,PortfolioHolding
from app.models.ingestion import EodPrice,RawSnapshot,DocumentAsset,IngestionRun,FilingEvent,FilingOrigin
from app.services.normalization import utc,IST

router=APIRouter(prefix='/api/v1/portfolio',tags=['Portfolio'],dependencies=[Depends(local_data_access)])

@router.get('/overview')
def overview(db:Session=Depends(get_db)):
    now=datetime.now(timezone.utc);today=now.astimezone(IST).date()
    companies=db.scalars(select(Company).join(PortfolioHolding).where(PortfolioHolding.owner_id==DEMO_OWNER).order_by(Company.ticker)).all()
    ids=[c.id for c in companies]
    prices=defaultdict(list)
    for row in db.scalars(select(EodPrice).where(EodPrice.company_id.in_(ids)).order_by(EodPrice.trading_date.desc(),EodPrice.updated_at.desc())):
        prices[row.company_id].append(row)
    sources={r.id:r for r in db.scalars(select(RawSnapshot).where(RawSnapshot.id.in_({rows[0].snapshot_id for rows in prices.values() if rows})))}
    latest_runs={}
    for run in db.scalars(select(IngestionRun).where(IngestionRun.ticker.in_([c.ticker for c in companies]),IngestionRun.dataset=='prices').order_by(IngestionRun.id.desc())):
        latest_runs.setdefault(run.ticker,run)
    document_counts=dict(db.execute(select(DocumentAsset.company_id,func.count()).where(DocumentAsset.company_id.in_(ids),DocumentAsset.kind.in_(['annual_report','earnings_transcript','quarterly_results']),DocumentAsset.extraction_status.in_(['extracted','partial'])).group_by(DocumentAsset.company_id)).all())
    items=[]
    for company in companies:
        rows=prices[company.id]
        # Never compare prices from different providers or duplicate dates.
        latest=rows[0] if rows else None
        previous=next((r for r in rows[1:] if r.provider==latest.provider and r.trading_date<latest.trading_date),None) if latest else None
        run=latest_runs.get(company.ticker)
        price=None;state='missing';note='No verified EOD prices stored.'
        if latest:
            source=sources[latest.snapshot_id]
            comparable=previous and 0<(latest.trading_date-previous.trading_date).days<=7 and Decimal(previous.close)>0
            change=format(((Decimal(latest.close)/Decimal(previous.close)-1)*100).quantize(Decimal('0.01')),'f') if comparable else None
            price={'close':latest.close,'currency':latest.currency,'volume':latest.volume,'trading_date':str(latest.trading_date),'change_percent':change,
                   'previous_trading_date':str(previous.trading_date) if comparable else None,'provider':latest.provider,
                   'source_url':source.final_url,'fetched_at':utc(source.fetched_at).isoformat()}
            state='available';note='Latest stored completed trading observation; not a live quote.'
            if (today-latest.trading_date).days>5:
                state='historical';note='The last stored trading observation is more than five calendar days old.'
            elif now-utc(source.fetched_at)>timedelta(hours=24):
                state='stale';note='Price source has not been refreshed within the last 24 hours.'
            if run and run.status in {'failed','stale','partial'}:
                state='stale';note='Latest refresh was '+run.status+'; showing previously stored observations.'
        docs=document_counts.get(company.id,0)
        items.append({'ticker':company.ticker,'name':company.name,'sector':company.sector,'exchange':company.exchange,'research_demo':company.research_demo,
                      'price':price,'source_state':state,'source_note':note,'primary_document_count':docs})
    replay=db.scalars(select(FilingEvent).where(FilingEvent.company_id.in_([c.id for c in companies]),FilingEvent.id.in_(select(FilingOrigin.filing_id).where(FilingOrigin.mode=='replay')))).all()
    dates=[i['price']['trading_date'] for i in items if i['price']]
    return {'items':items,'summary':{'companies':len(items),'sectors':len({i['sector'] for i in items}),'price_coverage':len(dates),
              'primary_source_coverage':sum(i['primary_document_count']>0 for i in items),'latest_trade_date':max(dates) if dates else None,'oldest_trade_date':min(dates) if dates else None},
            'replay_window':{'start':min(e.published_date for e in replay).isoformat(),'end_exclusive':(max(e.published_date for e in replay)+timedelta(days=1)).isoformat()} if replay else None,
            'generated_at':now.isoformat(),'ownership':'Mock portfolio; no quantities or valuations are claimed.'}
