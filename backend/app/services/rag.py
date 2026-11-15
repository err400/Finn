import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.config import get_settings
from app.models.entities import Company, ResearchRun
from app.models.intelligence import ResearchCache
from app.providers.llm import OpenAICompatibleModel, validate_synthesis
from app.providers.contracts import ProviderError
from app.services.ingestion import IngestionService
from app.services.retrieval import retrieve
from app.services.financials import financial_comparisons
from app.services.network import NetworkIntelligence
from app.services.normalization import utc

class RagResearchService:
    def __init__(self,db,owner_id,model=None):
        self.db,self.owner_id=db,owner_id
        self.model=model or OpenAICompatibleModel(get_settings())

    def research(self,ticker,question,workflow='snapshot'):
        ticker,company=IngestionService(self.db,get_settings().data_dir).resolve(ticker)
        network=NetworkIntelligence(self.db,self.owner_id).recommend(ticker)['recommendations'] if company else []
        evidence,docs=retrieve(self.db,company.id,question,workflow) if company else ([],[])
        fingerprints=sorted(d.sha256 for d in docs)
        key=hashlib.sha256(json.dumps([self.owner_id,ticker,question.strip().casefold(),workflow,fingerprints,self.model.identity,'rag-v4']).encode()).hexdigest()
        cache=self.db.get(ResearchCache,key)
        if cache and utc(cache.generated_at)>datetime.now(timezone.utc)-timedelta(hours=6):
            payload=dict(cache.payload,cache_hit=True)
        else:
            kinds={d.kind for d in docs}
            limitations=[]
            if 'annual_report' not in kinds:limitations.append('No parsed annual report is available for this company.')
            if 'earnings_transcript' not in kinds:limitations.append('No parsed earnings-call transcript is available for this company.')
            if workflow=='guidance_vs_actual':limitations.append('Guidance versus actual requires an explicit earlier promise, matching metric/basis and a later realized period. No automated promise-to-outcome linkage is validated yet; absence of evidence is not evidence of a missed target.')
            if workflow=='trajectory':limitations.append('Multi-year trajectory is not asserted unless comparable period evidence is available. Extracted quarterly comparisons cover only their cited periods.')
            financials=financial_comparisons(self.db,company.id) if company else {'metrics':[],'method':'No primary company documents available.'}
            if financials.get('conflicting_periods'):
                limitations.append('Conflicting primary-source financial values were found. Affected periods and comparisons are withheld; inspect the source documents.')
            status='insufficient_evidence' if not evidence else 'evidence_only'
            synthesis=None;model_error=None
            if evidence and self.model.configured and {'annual_report','earnings_transcript'}.issubset(kinds):
                try:
                    raw=self.model.synthesize(question,workflow,evidence)
                    synthesis=validate_synthesis(raw,evidence)
                    status='completed' if synthesis['claims'] else 'insufficient_evidence'
                    limitations.extend(synthesis['model_limitations'])
                except ProviderError as exc:
                    status='synthesis_unavailable';model_error={'code':exc.code,'message':str(exc)}
            elif evidence:
                limitations.append('LLM synthesis requires both a parsed annual report and earnings transcript, plus a configured model; retrieved passages are evidence, not a generated research conclusion.')
            payload={'ticker':ticker,'workflow':workflow,'question':question,'status':status,'answer':synthesis,
                     'evidence':evidence,'citations':[{'chunk_id':e['chunk_id'],'document_id':e['document_id'],'page':e['page'],'url':e['url'],'sha256':e['sha256']} for e in evidence],
                     'financials':financials,'limitations':limitations,'model_error':model_error,'model':self.model.identity,
                     'document_coverage':[{'id':d.id,'title':d.title,'kind':d.kind,'period_end':str(d.period_end) if d.period_end else None,'published_date':str(d.published_date) if d.published_date else None} for d in docs],
                     'evidence_period_end':max((str(d.period_end) for d in docs if d.period_end),default=None),
                     'message':'Primary evidence and calculated values only; no synthesis generated.' if synthesis is None else 'All factual claims are checked against exact retrieved primary-source quotations.',
                     'cache_hit':False}
            if model_error is None:
                if cache:cache.payload,cache.generated_at=payload,datetime.now(timezone.utc)
                else:self.db.add(ResearchCache(cache_key=key,owner_id=self.owner_id,payload=payload))
                self.db.commit()
        run=ResearchRun(owner_id=self.owner_id,ticker=ticker,question=question,status=payload['status'],result=payload)
        self.db.add(run);self.db.commit();self.db.refresh(run)
        return dict(payload,id=run.id,network=network)
