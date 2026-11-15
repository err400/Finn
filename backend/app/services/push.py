"""Deterministic PUSH. Extractive filing summaries; no invented company analysis."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.seed import DEMO_OWNER
from app.models.entities import Company, PortfolioHolding
from app.models.ingestion import FilingEvent, FilingOrigin, DocumentAsset, DocumentPage, RawSnapshot, EodPrice, IngestionRun, FetchCache
from app.models.intelligence import FilingInsight, AlertRule, AlertEvent
from app.services.network import NetworkIntelligence
from app.services.normalization import category_for, utc, IST

CATEGORIES={'results','M&A','fund_raise','management_change','litigation','insider_trading','earnings_call','investor_meetings','credit_rating','dividend','bonus_split','capex','press_release','postal_ballot','agm_egm','pledging','unclassified'}
WHY={
 'results':'Published results can update the operating and earnings picture. Check period, reporting basis and comparable figures before drawing conclusions.',
 'M&A':'A transaction can change capital allocation and business exposure. Check consideration, conditions, funding and integration responsibilities.',
 'management_change':'A leadership change can affect execution and oversight. Verify the role, effective date and disclosed succession arrangements.',
 'litigation':'Legal or regulatory proceedings can create uncertainty. Check the disclosed stage, quantified exposure and next milestones.',
 'capex':'Investment plans can affect funding and execution. Check the amount, timeline, capacity assumptions and approvals.',
 'credit_rating':'A rating action can be relevant to financing. Distinguish a downgrade from a routine reaffirmation.',
 'fund_raise':'Financing can affect funding costs or shareholder ownership. Check instrument, terms and approvals.',
 'pledging':'Changes to pledged promoter holdings can be relevant to financing risk. Check the disclosed scale and direction.',
 'press_release':'A commercial announcement may warrant follow-up. Check contractual responsibilities, conditions and whether financial commitments are actually disclosed.',
}

def rounded(value):return format(value.quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'f')

def priority(title,category):
    t=title.casefold()
    if any(w in t for w in ['downgrade','default on','insolvency','fraud']):return 95,'potentially_material','Risk-related disclosure deserves a closer look.'
    if 'joint operating agreement' in t:return 85,'potentially_material','Operating agreement: review responsibilities and commitments.'
    if any(w in t for w in ['newspaper','advertisement','trading window','loss of share','compliance certificate','esop allotment']):return 15,'routine','Administrative or publication-related disclosure; kept available below.'
    if any(w in t for w in ['board meeting intimation','intimation of board meeting']):return 30,'routine','Meeting notice, not the results themselves.'
    if category in {'results','M&A','management_change','litigation','capex','fund_raise','pledging'}:return 80,'potentially_material',f'{category.replace("_"," ")} disclosure merits review.'
    if category in {'postal_ballot','agm_egm','investor_meetings'}:return 25,'routine','Routine governance or meeting update unless the filing says otherwise.'
    return 45,'review','Priority is uncertain; FINN has kept this visible for review.'

class PushService:
    def __init__(self,db:Session,owner_id=DEMO_OWNER):self.db,self.owner_id=db,owner_id

    def holdings(self):
        return self.db.scalars(select(Company).join(PortfolioHolding).where(PortfolioHolding.owner_id==self.owner_id)).all()

    def insight(self,event):
        doc=self.db.get(DocumentAsset,event.document_id) if event.document_id else None
        fingerprint=hashlib.sha256(f'extractive-v3|{event.title}|{doc.sha256 if doc else "none"}'.encode()).hexdigest()
        cached=self.db.get(FilingInsight,event.id)
        if cached and cached.fingerprint==fingerprint:return dict(cached.payload,cache_hit=True)
        category=category_for(event.title);rank,materiality,reason=priority(event.title,category)
        excerpt=None;page_number=None
        if doc:
            pages=self.db.scalars(select(DocumentPage).where(DocumentPage.document_id==doc.id).order_by(DocumentPage.page_number).limit(5)).all()
            keywords=set(re.findall(r'[a-z]{4,}',event.title.casefold()))-{'limited','industries','company','release','media','under','regulation'}
            choices=[]
            for p in pages:
                clean=re.sub(r'\s+',' ',p.text).strip()
                markers=[clean.find(m) for m in ['Please find attached','We hereby','Pursuant to','We wish to inform'] if m in clean]
                if markers:clean=clean[min(markers):]
                for sentence in re.split(r'(?<=[.!?])\s+',clean):
                    if len(sentence)<60:continue
                    score=sum(1 for w in keywords if w in sentence.casefold())
                    if 'please find attached' in sentence.casefold() or 'we hereby' in sentence.casefold():score+=2
                    choices.append((score,-p.page_number,sentence,p.page_number))
            if choices:
                _,_,text,page_number=max(choices)
                if len(text)>500:
                    pos=text.rfind(' ',0,500);text=text[:pos if pos>0 else 500]
                excerpt=text
        origins=self.db.scalars(select(FilingOrigin).where(FilingOrigin.filing_id==event.id)).all()
        url=origins[0].source_url if origins else None
        if doc:url=self.db.get(RawSnapshot,doc.snapshot_id).final_url
        payload={'category':category,'priority':rank,'materiality':materiality,'priority_reason':reason,
                 'summary':excerpt or event.title,'summary_method':'extractive_primary_filing' if excerpt else 'source_title_only',
                 'summary_limitation':None if excerpt else 'Attachment text unavailable; this is the source headline, not an analysis.',
                 'why_it_may_matter':WHY.get(category,'Review the original disclosure for relevance to your investment question.'),
                 'explanation_type':'General category-based review prompt, not a claim of financial impact.',
                 'citation':{'document_id':doc.id if doc else None,'page':page_number,'url':url+(f'#page={page_number}' if page_number and url else ''),'quote':excerpt,'source_url':url}}
        if not cached:cached=FilingInsight(filing_id=event.id,fingerprint=fingerprint,payload=payload);self.db.add(cached)
        else:cached.fingerprint,cached.payload=fingerprint,payload
        self.db.commit()
        return dict(payload,cache_hit=False)

    def digest(self,start=None,end=None,mode='live'):
        end=utc(end) if end else datetime.now(timezone.utc)
        start=utc(start) if start else end-timedelta(hours=24)
        if start>=end:raise ValueError('Start must be before end')
        companies={c.id:c for c in self.holdings()}
        origins_query=select(FilingOrigin.filing_id)
        if mode!='all':origins_query=origins_query.where(FilingOrigin.mode==mode)
        query=select(FilingEvent).where(FilingEvent.company_id.in_(companies),FilingEvent.id.in_(origins_query))
        events=self.db.scalars(query).all()
        archive=self.db.scalars(select(FilingEvent).where(FilingEvent.company_id.in_(companies))).all()
        archive_coverage={'stored_filings':len(archive),'earliest_publication_date':min((str(e.published_date) for e in archive),default=None),
            'latest_publication_date':max((str(e.published_date) for e in archive),default=None),'exhaustive':False,
            'companies_with_filings':len({e.company_id for e in archive}), 'portfolio_companies':len(companies),
            'by_company':[{'ticker':c.ticker,'stored_filings':sum(e.company_id==c.id for e in archive)} for c in sorted(companies.values(),key=lambda c:c.ticker)]}

        selected=[]
        for e in events:
            if e.published_at:
                if not start<=utc(e.published_at)<end:continue
            else:
                # Date-only disclosures overlap a local day; never invent a publication time.
                day=datetime.combine(e.published_date,datetime.min.time(),IST)
                if not utc(day)<end or not utc(day+timedelta(days=1))>start:continue
            selected.append(e)
        selected.sort(key=lambda e:(-priority(e.title,category_for(e.title))[0],-e.published_date.toordinal(),-e.id))
        items=[]
        for event in selected[:500]:
            company=companies[event.company_id];insight=self.insight(event)
            recommendations=NetworkIntelligence(self.db,self.owner_id).recommend(company.ticker,category=insight['category'],event_title=event.title)['recommendations'] if insight['materiality']=='potentially_material' else []
            origin_query=select(FilingOrigin).where(FilingOrigin.filing_id==event.id)
            if mode!='all':origin_query=origin_query.where(FilingOrigin.mode==mode)
            origins=self.db.scalars(origin_query).all()
            item_mode='live' if any(o.mode=='live' for o in origins) else 'replay'
            items.append({'id':event.id,'ticker':company.ticker,'company':company.name,'title':event.title,'published_at':utc(event.published_at).isoformat() if event.published_at else None,
                          'published_date':event.published_date.isoformat(),'publication_precision':event.publication_precision,'mode':item_mode,
                          'source_urls':[o.source_url for o in origins],**insight,'network':recommendations})
        latest=[]
        for company in companies.values():
            run_query=select(IngestionRun).where(IngestionRun.ticker==company.ticker,IngestionRun.dataset=='filings')
            if mode!='all':run_query=run_query.where(IngestionRun.mode==mode)
            run=self.db.scalar(run_query.order_by(IngestionRun.id.desc()).limit(1))
            latest.append({'ticker':company.ticker,'status':run.status if run else 'not_refreshed','completed_at':utc(run.completed_at).isoformat() if run and run.completed_at else None})
        source_checks=[]
        if mode!='replay':
            for cache in self.db.scalars(select(FetchCache).where(FetchCache.url.in_([
                'https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml',
                'https://www.bseindia.com/data/xml/announcements.xml']))):
                source_checks.append({'url':cache.url,'last_checked_at':utc(cache.last_checked_at).isoformat() if cache.last_checked_at else None,
                    'expires_at':utc(cache.expires_at).isoformat() if cache.expires_at else None,'last_error':cache.last_error,
                    'overdue':not cache.expires_at or utc(cache.expires_at)<datetime.now(timezone.utc)})
        return {'archive_coverage':archive_coverage,'source_checks':source_checks,'mode':mode,'label':'Historical filing replay' if mode=='replay' else 'Stored portfolio filing archive' if mode=='all' else 'Portfolio digest — recent RSS observations',
                'start':start.isoformat(),'end_exclusive':end.isoformat(),'total_available':len(selected),'truncated':len(selected)>500,
                'important':[i for i in items if i['materiality']!='routine'],'routine':[i for i in items if i['materiality']=='routine'],
                'routine_collapsed_by_default':True,'coverage':'All stored matching portfolio disclosures are considered. Public RSS windows are incomplete; no matches does not mean no announcements.',
                'refresh_status':latest,'summary_engine':'Deterministic extractive summaries; no LLM is used for PUSH.'}

    def evaluate(self,as_of:date,mode='live'):
        rules=self.db.scalars(select(AlertRule).where(AlertRule.owner_id==self.owner_id,AlertRule.enabled.is_(True))).all()
        companies=self.holdings();inserted=[];skipped=[]
        for rule in rules:
            targets=[c for c in companies if rule.ticker is None or c.ticker==rule.ticker]
            for c in targets:
                if rule.kind=='announcement_category':
                    events=self.db.scalars(select(FilingEvent).where(FilingEvent.company_id==c.id,FilingEvent.published_date==as_of,
                        FilingEvent.id.in_(select(FilingOrigin.filing_id).where(FilingOrigin.mode==mode)))).all()
                    for e in events:
                        category=category_for(e.title)
                        if category not in rule.categories:continue
                        origins=self.db.scalars(select(FilingOrigin).where(FilingOrigin.filing_id==e.id,FilingOrigin.mode==mode)).all()
                        evidence={'filing_id':e.id,'title':e.title,'triggering_value':category,'threshold':rule.categories,'comparison':'category_in_selection',
                                  'sources':[{'url':o.source_url,'raw_published':o.raw_published,'mode':o.mode} for o in origins],
                                  'publication_precision':e.publication_precision,'network':NetworkIntelligence(self.db,self.owner_id).recommend(c.ticker,category=category,event_title=e.title)['recommendations']}
                        item=self._alert(rule,c,f'filing:{e.id}',as_of,e.published_at,mode,evidence)
                        if item:inserted.append(item)
                    continue
                rows=self.db.scalars(select(EodPrice).where(EodPrice.company_id==c.id,EodPrice.provider=='yahoo_chart',EodPrice.trading_date<=as_of).order_by(EodPrice.trading_date.desc()).limit(rule.lookback+1)).all()
                if not rows or (as_of-rows[0].trading_date).days>5:
                    skipped.append({'rule_id':rule.id,'ticker':c.ticker,'reason':'No sufficiently recent completed EOD observation for this evaluation date.'});continue
                current=rows[0];threshold=Decimal(rule.threshold)
                if rule.kind=='price_move':
                    if len(rows)<2 or (current.trading_date-rows[1].trading_date).days>7 or Decimal(rows[1].close)<=0:
                        skipped.append({'rule_id':rule.id,'ticker':c.ticker,'reason':'Comparable previous trading observation is unavailable.'});continue
                    previous=rows[1];value=(Decimal(current.close)/Decimal(previous.close)-1)*100
                    trigger=(value>=threshold if rule.direction=='up' else value<=-threshold if rule.direction=='down' else abs(value)>=threshold)
                    baseline={'previous_close':previous.close,'previous_trading_date':str(previous.trading_date)}
                    calculation='(close / previous_available_trading_close - 1) * 100';comparison=rule.direction+' movement >= threshold percent'
                    used=[current,previous]
                else:
                    history=rows[1:rule.lookback+1]
                    if len(history)<rule.lookback or (current.trading_date-history[-1].trading_date).days>rule.lookback*4:
                        skipped.append({'rule_id':rule.id,'ticker':c.ticker,'reason':f'Need {rule.lookback} recent preceding trading observations; target day is excluded from the average.'});continue
                    average=sum(Decimal(p.volume) for p in history)/Decimal(len(history))
                    if average<=0:
                        skipped.append({'rule_id':rule.id,'ticker':c.ticker,'reason':'Baseline volume is zero; ratio is undefined.'});continue
                    value=Decimal(current.volume)/average;trigger=value>threshold
                    baseline={'average_volume':rounded(average),'lookback_observations':len(history),'baseline_volumes':[{'date':str(p.trading_date),'volume':p.volume} for p in history]}
                    calculation='target_day_volume / mean(previous N stored trading-day volumes)';comparison='volume ratio > threshold';used=[current]+history
                if not trigger:continue
                sources=[]
                for source_id in sorted({p.snapshot_id for p in used}):
                    s=self.db.get(RawSnapshot,source_id);sources.append({'snapshot_id':s.id,'url':s.final_url,'sha256':s.sha256,'retrieved_at':utc(s.fetched_at).isoformat()})
                evidence={'triggering_value':rounded(value),'threshold':rule.threshold,'comparison':comparison,'calculation':calculation,
                          'close':current.close,'volume':current.volume,**baseline,'sources':sources,'monitoring':'End-of-day data; not real-time monitoring.',
                          'corporate_action_limit':'Provider daily closes can be affected by corporate actions; no split/dividend normalization is inferred.'}
                item=self._alert(rule,c,f'{rule.kind}:{current.trading_date}',current.trading_date,None,mode,evidence)
                if item:inserted.append(item)
        self.db.commit()
        return {'as_of':str(as_of),'mode':mode,'label':'Historical EOD/replay evaluation' if mode=='replay' else 'EOD evaluation — not real-time',
                'new_alert_ids':inserted,'new_alert_count':len(inserted),'skipped':skipped,'delivery':'Persistent in-app inbox. Evaluation is explicit or scheduled by the local CLI; no email, SMS or browser notifications.'}

    def _alert(self,rule,company,key,day,stamp,mode,evidence):
        key=f'{mode}:{company.ticker}:{key}'
        if self.db.scalar(select(AlertEvent).where(AlertEvent.rule_id==rule.id,AlertEvent.observation_key==key)):return None
        item=AlertEvent(owner_id=self.owner_id,rule_id=rule.id,observation_key=key,ticker=company.ticker,kind=rule.kind,
                        observed_date=day,observed_at=stamp,mode=mode,evidence=evidence)
        self.db.add(item);self.db.flush();return item.id
