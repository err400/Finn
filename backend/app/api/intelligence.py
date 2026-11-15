from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.seed import DEMO_OWNER
from app.api.ingestion import local_data_access
from app.models.entities import Company, PortfolioHolding
from app.models.ingestion import FilingEvent
from app.models.intelligence import AlertRule, AlertEvent
from app.services.push import PushService, CATEGORIES
from app.services.network import NetworkIntelligence
from app.services.normalization import normalize_symbol, utc, IST

router=APIRouter(prefix='/api/v1',tags=['PUSH and NETWORK'],dependencies=[Depends(local_data_access)])

@router.get('/push/digest')
def digest(start:datetime|None=None,end:datetime|None=None,mode:Literal['live','replay','all']='live',db:Session=Depends(get_db)):
    if any(d is not None and d.tzinfo is None for d in [start,end]):raise HTTPException(422,'Include timezone offsets in custom datetime windows')
    try:return PushService(db).digest(start,end,mode)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

class RuleRequest(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    kind:Literal['price_move','volume_spike','announcement_category']
    ticker:str|None=None
    threshold:Decimal|None=Field(default=None,gt=0,le=10000)
    direction:Literal['absolute','up','down']='absolute'
    lookback:int=Field(default=20,ge=5,le=60)
    categories:list[str]=Field(default_factory=list,max_length=17)
    @model_validator(mode='after')
    def validate_rule(self):
        self.name=self.name.strip()
        if not self.name:raise ValueError('Name cannot be blank')
        if self.ticker:
            exchange,symbol=normalize_symbol(self.ticker)
            if exchange!='NSE':raise ValueError('Use the canonical NSE ticker in alert rules')
            self.ticker=symbol
        if self.kind=='announcement_category':
            if not self.categories or not set(self.categories)<=CATEGORIES:raise ValueError('Select supported announcement categories')
        elif self.threshold is None:raise ValueError('Numeric alert rules require a threshold')
        return self

def rule_out(r):return {'id':r.id,'name':r.name,'kind':r.kind,'ticker':r.ticker,'threshold':r.threshold,'direction':r.direction,'lookback':r.lookback,'categories':r.categories,'enabled':r.enabled}

@router.get('/push/rules')
def rules(db:Session=Depends(get_db)):
    return [rule_out(r) for r in db.scalars(select(AlertRule).where(AlertRule.owner_id==DEMO_OWNER).order_by(AlertRule.id))]

@router.post('/push/rules',status_code=201)
def create_rule(body:RuleRequest,db:Session=Depends(get_db)):
    if len(db.scalars(select(AlertRule.id).where(AlertRule.owner_id==DEMO_OWNER)).all())>=100:
        raise HTTPException(409,'Demo workspace supports at most 100 saved rules')
    if body.ticker and not db.scalar(select(Company.id).join(PortfolioHolding).where(PortfolioHolding.owner_id==DEMO_OWNER,Company.ticker==body.ticker)):
        raise HTTPException(422,'Alert ticker must be in the demo portfolio')
    rule=AlertRule(owner_id=DEMO_OWNER,name=body.name,kind=body.kind,ticker=body.ticker,threshold=str(body.threshold) if body.threshold is not None else None,
                   direction=body.direction,lookback=body.lookback,categories=sorted(set(body.categories)))
    db.add(rule);db.commit();db.refresh(rule);return rule_out(rule)

class ToggleRule(BaseModel):enabled:bool

@router.patch('/push/rules/{rule_id}')
def toggle_rule(rule_id:int,body:ToggleRule,db:Session=Depends(get_db)):
    rule=db.scalar(select(AlertRule).where(AlertRule.id==rule_id,AlertRule.owner_id==DEMO_OWNER))
    if not rule:raise HTTPException(404,'Rule not found')
    rule.enabled=body.enabled;db.commit();return rule_out(rule)

class EvaluateRequest(BaseModel):
    as_of:date=Field(default_factory=lambda:datetime.now(IST).date())
    mode:Literal['live','replay']='live'
    @model_validator(mode='after')
    def validate_date(self):
        if self.as_of>datetime.now(IST).date():raise ValueError('Future evaluation is unsupported')
        return self

@router.post('/push/evaluate')
def evaluate(body:EvaluateRequest,db:Session=Depends(get_db)):
    return PushService(db).evaluate(body.as_of,body.mode)

@router.get('/push/alerts')
def alerts(limit:int=Query(100,ge=1,le=500),db:Session=Depends(get_db)):
    return [{'id':a.id,'rule_id':a.rule_id,'ticker':a.ticker,'kind':a.kind,'observed_date':a.observed_date,
             'observed_at':utc(a.observed_at) if a.observed_at else None,'triggered_at':utc(a.triggered_at),'mode':a.mode,'evidence':a.evidence}
            for a in db.scalars(select(AlertEvent).where(AlertEvent.owner_id==DEMO_OWNER).order_by(AlertEvent.id.desc()).limit(limit))]

@router.get('/network/recommendations')
def recommendations(company:str=Query(min_length=1,max_length=200),filing_id:int|None=None,limit:int=Query(3,ge=1,le=10),db:Session=Depends(get_db)):
    service=NetworkIntelligence(db,DEMO_OWNER)
    category=None;title=''
    if filing_id:
        event=db.get(FilingEvent,filing_id)
        if not event:raise HTTPException(404,'Filing not found')
        try:resolved=service.resolve_company(company)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        if event.company_id!=resolved.id:raise HTTPException(422,'Filing does not belong to the selected company')
        category=event.category;title=event.title
    try:return service.recommend(company,category=category,event_title=title,limit=limit)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@router.get('/network/search')
def search_person(person:str=Query(min_length=2,max_length=150),db:Session=Depends(get_db)):
    return NetworkIntelligence(db,DEMO_OWNER).match_person(person)

@router.get('/network/people/{contact_id}')
def profile(contact_id:int,db:Session=Depends(get_db)):
    result=NetworkIntelligence(db,DEMO_OWNER).profile(contact_id)
    if result is None:raise HTTPException(404,'Profile not found')
    return result


@router.post('/push/refresh',status_code=202)
async def refresh_sources():
    from app.services.source_refresh import source_refresh
    return await source_refresh.request()

@router.get('/push/refresh-status')
def refresh_status():
    from app.services.source_refresh import source_refresh
    from app.core.config import get_settings
    return dict(source_refresh.status(),automatic_refresh=get_settings().auto_refresh_enabled,interval_seconds=get_settings().source_refresh_seconds)
