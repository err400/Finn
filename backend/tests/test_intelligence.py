"""Connected workflows; all prices/PDFs here are synthetic in-memory test fixtures."""
import json
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
import httpx
import pytest
from sqlalchemy import select,func
from app.core.config import Settings
from app.db.seed import DEMO_OWNER
from app.models.entities import Company,Contact
from app.models.ingestion import DocumentAsset,DocumentPage,RawSnapshot,EodPrice,FilingEvent
from app.models.intelligence import AlertRule,AlertEvent,NetworkProfile,RelationshipEdge,ResearchChunk
from app.providers.contracts import PrimaryDocument,ProviderError
from app.providers.llm import validate_synthesis,OpenAICompatibleModel
from app.services.ingestion import IngestionService
from app.services.push import PushService
from app.services.network import NetworkIntelligence
from app.services.retrieval import retrieve,chunk_page,normalize_text
from app.services.financials import change,extract_table
from app.services.rag import RagResearchService
from test_ingestion import pdf,fetcher,PDF_URL

STAMP=datetime(2025,7,29,12,tzinfo=timezone.utc)

def filing(db,path,title):
    svc=IngestionService(db,path,fetcher=fetcher(db,path,lambda r:httpx.Response(200,content=pdf('RELIANCE '+title))))
    company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
    candidate=PrimaryDocument('RELIANCE',title,'exchange_filing',PDF_URL,PDF_URL,'synthetic test')
    doc=svc.store_document(company,candidate,svc.fetcher.get(PDF_URL,0,True))
    svc._store_filing(company,title,PDF_URL+f'?fixture={doc.id}','test',str(doc.id),STAMP,STAMP.date(),'replay',doc,None)
    return db.scalar(select(FilingEvent).where(FilingEvent.document_id==doc.id))

def primary(db,company_id,kind,text,tag):
    snap=RawSnapshot(url='https://www.ril.com/sites/default/files/'+tag+'.pdf',final_url='https://www.ril.com/sites/default/files/'+tag+'.pdf',sha256=tag,media_type='application/pdf',byte_count=len(text),response_headers={})
    db.add(snap);db.flush()
    doc=DocumentAsset(company_id=company_id,sha256=tag,snapshot_id=snap.id,kind=kind,title='Synthetic '+kind,publisher='synthetic test',discovery_url=snap.url,date_basis='Unknown; test fixture',page_count=1,extraction_status='extracted')
    db.add(doc);db.flush();db.add(DocumentPage(document_id=doc.id,page_number=1,text=text));db.commit();return doc

def test_event_to_person_digest_and_routine_collapse(client,tmp_path):
    c,factory=client
    with factory() as db:
        material=filing(db,tmp_path,'Joint operating agreement for upstream energy project')
        filing(db,tmp_path,'ESOP allotment compliance certificate')
        svc=PushService(db);r=svc.digest(STAMP-timedelta(hours=1),STAMP+timedelta(hours=1),'replay')
        assert len(r['important'])==1 and len(r['routine'])==1
        item=r['important'][0];assert item['network'][0]['name']=='Priya Demo Menon' and item['network'][0]['degree']==2
        assert item['network'][0]['synthetic'] and 'Aarav Demo Mehta' in item['network'][0]['reason']
        assert item['citation']['page']==1 and '#page=1' in item['citation']['url']
        source=db.scalar(select(DocumentPage).where(DocumentPage.document_id==material.document_id))
        assert normalize_text(item['citation']['quote']) in normalize_text(source.text)
        assert svc.digest(STAMP-timedelta(hours=1),STAMP+timedelta(hours=1),'replay')['important'][0]['cache_hit']
        assert svc.digest(STAMP-timedelta(days=3),STAMP-timedelta(days=2),'replay')['total_available']==0
    r=c.get('/api/v1/push/digest',params={'mode':'replay','start':'2025-07-29T00:00:00Z','end':'2025-07-30T00:00:00Z'})
    assert r.status_code==200 and r.json()['routine_collapsed_by_default']
    assert c.get('/api/v1/push/digest?start=2025-07-29T00:00:00').status_code==422

def test_network_matching_peers_and_owner_isolation(client):
    c,factory=client
    with factory() as db:
        svc=NetworkIntelligence(db,DEMO_OWNER)
        assert svc.recommend('Reliance Industries Limited')['ticker']=='RELIANCE'
        assert any('peer_experience' in p['score_components'] for p in svc.recommend('INFY',limit=10)['recommendations'])
        match=svc.match_person('Priya Menon')['matches'][0];assert match['education'] and match['degree']==2
        assert svc.match_person('Savithri Parekh')['matches']==[]
        assert NetworkIntelligence(db,'other').recommend('RELIANCE')['recommendations']==[]
        other=Contact(owner_id='other',name='Private synthetic contact',expertise=['energy'],synthetic=True,provenance='test');db.add(other);db.flush()
        db.add(RelationshipEdge(owner_id=DEMO_OWNER,source_key='investor',target_id=other.id,relationship='poison test edge',strength=5,provenance='test'));db.commit()
        assert svc.profile(other.id) is None and other.id not in svc.paths()
        person=Contact(owner_id=DEMO_OWNER,name='Second Synthetic Priya',expertise=[],synthetic=True,provenance='test');db.add(person);db.flush()
        db.add(NetworkProfile(contact_id=person.id,aliases=['Priya Menon'],bio='test'));db.commit()
        assert svc.match_person('Priya Menon')['ambiguous']
    assert c.get('/api/v1/network/recommendations?company=INFY').status_code==200

def test_numeric_alert_math_baseline_dedup_and_staleness(client):
    _,factory=client
    with factory() as db:
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
        snap=RawSnapshot(url='https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS',final_url='https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS',sha256='test',media_type='application/json',byte_count=10,response_headers={});db.add(snap);db.flush()
        for i,n in enumerate([24,27,28,29,30,31]):db.add(EodPrice(company_id=company.id,trading_date=date(2025,1,n),close='110' if i==5 else '100',volume=300 if i==5 else 100,currency='INR',provider='yahoo_chart',snapshot_id=snap.id))
        db.add_all([AlertRule(owner_id=DEMO_OWNER,name='price',kind='price_move',ticker='RELIANCE',threshold='10',direction='absolute',lookback=5,categories=[]),AlertRule(owner_id=DEMO_OWNER,name='volume',kind='volume_spike',ticker='RELIANCE',threshold='2',lookback=5,categories=[])])
        db.commit();svc=PushService(db)
        assert svc.evaluate(date(2025,1,31),'replay')['new_alert_count']==2
        rows=db.scalars(select(AlertEvent).order_by(AlertEvent.id)).all()
        assert rows[0].evidence['triggering_value']=='10.0000'
        assert rows[1].evidence['triggering_value']=='3.0000' and rows[1].evidence['average_volume']=='100.0000'
        assert len(rows[1].evidence['baseline_volumes'])==5 and svc.evaluate(date(2025,1,31),'replay')['new_alert_count']==0
        assert svc.evaluate(date(2026,1,31),'live')['skipped']

def test_category_alert_and_rule_api(client,tmp_path):
    c,factory=client
    with factory() as db:filing(db,tmp_path,'Acquisition of upstream company')
    r=c.post('/api/v1/push/rules',json={'name':'Acquisitions','kind':'announcement_category','ticker':'RELIANCE','categories':['M&A']})
    assert r.status_code==201;rule_id=r.json()['id']
    assert c.post('/api/v1/push/evaluate',json={'as_of':'2025-07-29','mode':'replay'}).json()['new_alert_count']==1
    alert=c.get('/api/v1/push/alerts').json()[0];assert alert['evidence']['triggering_value']=='M&A' and alert['evidence']['sources'] and alert['evidence']['network']
    assert not c.patch(f'/api/v1/push/rules/{rule_id}',json={'enabled':False}).json()['enabled']
    assert c.post('/api/v1/push/rules',json={'name':'bad','kind':'volume_spike','threshold':0}).status_code==422
    assert c.post('/api/v1/push/rules',json={'name':'bad','kind':'announcement_category','categories':['fake']}).status_code==422

def test_retrieval_chunks_primary_filter_and_company_boundaries(client):
    _,factory=client
    chunks=list(chunk_page('Business segments and financial performance. '*100));assert len(chunks)>1 and all(len(c)<=1200 for c in chunks)
    with factory() as db:
        ril=db.scalar(select(Company).where(Company.ticker=='RELIANCE'));tcs=db.scalar(select(Company).where(Company.ticker=='TCS'))
        primary(db,ril.id,'annual_report','Synthetic business segments include energy and retail. Revenue and cash flow appear in the financial statements.','ar')
        primary(db,ril.id,'earnings_transcript','Synthetic management guidance discusses energy growth and operating performance. No target is provided.','call')
        primary(db,ril.id,'broker_note','Secondary broker revenue forecast and fabricated opinion.','broker')
        primary(db,tcs.id,'annual_report','Other company revenue discussion, not relevant to this issuer.','other')
        hits,docs=retrieve(db,ril.id,'What are the business segments and revenue?','snapshot')
        assert hits and all(h['document_id'] in {d.id for d in docs} and h['page']==1 and h['url'].endswith('#page=1') and h['kind']!='broker_note' and 'Other company' not in h['text'] for h in hits)
        count=db.scalar(select(func.count()).select_from(ResearchChunk));retrieve(db,ril.id,'Business segments?','snapshot')
        assert db.scalar(select(func.count()).select_from(ResearchChunk))==count

def test_grounding_rejects_invented_values_and_citations():
    evidence=[{'chunk_id':1,'document_id':10,'page':2,'url':'https://example.org/a.pdf#page=2','sha256':'hash','text':'Revenue was 100 crore for this synthetic test quarter.'}]
    raw={'claims':[{'text':evidence[0]['text'],'kind':'source_quote','citations':[{'chunk_id':1,'quote':evidence[0]['text']}]}],'limitations':[]}
    assert validate_synthesis(raw,evidence)['claims'][0]['citations'][0]['page']==2
    raw['claims'][0]['text']='Revenue was 999 crore, an invented value.'
    with pytest.raises(ProviderError):validate_synthesis(raw,evidence)
    raw['claims'][0]['citations'][0]['chunk_id']=999
    with pytest.raises(ProviderError):validate_synthesis(raw,evidence)

def test_numeric_extraction_accuracy_and_unsupported_layout():
    table='CONSOLIDATED FINANCIAL HIGHLIGHTS\n(₹ in crore)\n4Q FY25 3Q FY25 4Q FY24 % chg. Y-o-Y FY25 FY24\n1 Gross Revenue 110 100 80 37.5 410 300\n2 EBITDA 30 25 20 50 100 90\n'
    assert change('110','100')=='10.00' and change('80','100')=='-20.00' and change('5','0') is None
    facts=extract_table(table);assert len(facts)==6 and facts[0]['value']=='110' and facts[0]['period_end']=='2025-03-31'
    assert facts[1]['period_end']=='2024-12-31' and extract_table(table.replace('₹ in crore','USD million'))==[]
    assert extract_table('Unstructured commentary with 100 and 200.')==[]

def test_rag_missing_model_errors_and_grounded_path(client):
    _,factory=client
    with factory() as db:
        off=SimpleNamespace(identity='disabled-test',configured=False)
        empty=RagResearchService(db,DEMO_OWNER,off).research('UNSEEN','What is the business?')
        assert empty['status']=='insufficient_evidence' and empty['answer'] is None and not empty['citations']
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
        primary(db,company.id,'annual_report','Synthetic business segments include energy and retail. Revenue and operating performance are reviewed annually.','test-ar')
        primary(db,company.id,'earnings_transcript','Synthetic management guidance discusses business growth. No financial targets are provided in this test.','test-call')
        class ValidModel:
            configured=True;identity='test-model'
            def synthesize(self,question,workflow,evidence):
                e=evidence[0];return {'claims':[{'text':e['text'],'kind':'source_quote','citations':[{'chunk_id':e['chunk_id'],'quote':e['text']}]}],'limitations':[]}
        good=RagResearchService(db,DEMO_OWNER,ValidModel()).research('RELIANCE','What are the business segments?')
        assert good['status']=='completed' and good['answer']['claims'] and good['network']
        assert RagResearchService(db,DEMO_OWNER,ValidModel()).research('RELIANCE','What are the business segments?')['cache_hit']
        class BadModel(ValidModel):
            identity='bad-model'
            def synthesize(self,*args):raise ProviderError('test_error','Synthetic provider failure')
        bad=RagResearchService(db,DEMO_OWNER,BadModel()).research('RELIANCE','What are the business segments?')
        assert bad['status']=='synthesis_unavailable' and bad['answer'] is None and bad['evidence']
        guidance=RagResearchService(db,DEMO_OWNER,off).research('RELIANCE','What did management promise?','guidance_vs_actual')
        assert any('No automated promise-to-outcome' in l for l in guidance['limitations'])

def test_hyde_environment_and_safe_selection(monkeypatch):
    monkeypatch.setenv('HYDE_INFERENCE_API_KEY','synthetic-test-secret');monkeypatch.setenv('HYDE_BASE_URL','https://inference.example.org/v1');monkeypatch.setenv('HYDE_MODEL','test-model')
    settings=Settings(_env_file=None)
    assert settings.llm_api_key.get_secret_value()=='synthetic-test-secret' and settings.llm_model=='test-model' and 'synthetic-test-secret' not in repr(settings)
    evidence=[{'chunk_id':1,'document_id':1,'kind':'annual_report','title':'Synthetic annual report','page':1,'url':'https://example.org/a.pdf#page=1','sha256':'test','text':'Synthetic business segments include energy and retail.'}]
    def handler(request):
        assert 'primary_evidence' in json.loads(request.content)['messages'][1]['content']
        assert 'Priya' not in request.content.decode()
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'selected_passages':[{'chunk_id':1,'sentence_index':0}],'limitations':[]})}}]})
    model=OpenAICompatibleModel(settings,httpx.Client(transport=httpx.MockTransport(handler)))
    assert validate_synthesis(model.synthesize('Segments?','snapshot',evidence),evidence)['claims']

def test_portfolio_overview_missing_data_is_not_zero_price(client):
    c,_=client
    r=c.get('/api/v1/portfolio/overview')
    assert r.status_code==200
    data=r.json()
    assert data['summary']['companies']==18 and data['summary']['price_coverage']==0
    assert all(row['price'] is None and row['source_state']=='missing' for row in data['items'])
    assert data['replay_window'] is None

def test_portfolio_overview_uses_comparable_prices_and_exposes_failed_refresh(client):
    c,factory=client
    from app.models.ingestion import IngestionRun
    with factory() as db:
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
        s=RawSnapshot(url='https://example.org/fixture',final_url='https://example.org/fixture',sha256='overview-test',media_type='application/json',byte_count=2,response_headers={})
        db.add(s);db.flush()
        for day,close in [(date(2025,1,30),'100'),(date(2025,1,31),'110')]:
            db.add(EodPrice(company_id=company.id,trading_date=day,close=close,volume=100,currency='INR',provider='synthetic-test',snapshot_id=s.id))
        db.add(IngestionRun(ticker='RELIANCE',dataset='prices',mode='live',status='failed',details={'error_code':'network_error'}));db.commit()
    row=next(r for r in c.get('/api/v1/portfolio/overview').json()['items'] if r['ticker']=='RELIANCE')
    assert row['price']['change_percent']=='10.00' and row['price']['previous_trading_date']=='2025-01-30'
    assert row['source_state']=='stale' and 'failed' in row['source_note']

def test_source_refresh_requests_share_one_background_job():
    import asyncio
    from app.services.source_refresh import SourceRefreshManager
    async def scenario():
        gate=asyncio.Event();calls=[]
        async def worker(automatic):
            calls.append(automatic);await gate.wait();return {'runs':[{'status':'success'}]}
        manager=SourceRefreshManager(worker);manager.recent_check=lambda:False
        assert (await manager.request())['status']=='running'
        assert (await manager.request())['status']=='running'
        await asyncio.sleep(0);assert len(calls)==1
        gate.set();await manager.task
        assert manager.status()['status']=='success'
        manager.recent_check=lambda:True
        assert (await manager.request())['status']=='recently_checked' and len(calls)==1
    asyncio.run(scenario())

def test_source_refresh_failure_is_not_reported_as_success():
    import asyncio
    from app.services.source_refresh import SourceRefreshManager
    async def scenario():
        async def worker(automatic):raise RuntimeError('Synthetic test error')
        manager=SourceRefreshManager(worker);manager.recent_check=lambda:False
        await manager.request();await manager.task
        assert manager.status()['status']=='failed'
        assert 'Synthetic test error' not in manager.status()['message']
    asyncio.run(scenario())

def test_broad_custom_archive_includes_verified_historical_records_without_relabeling_live(client,tmp_path):
    c,factory=client
    with factory() as db:filing(db,tmp_path,'Joint operating agreement for upstream energy project')
    params={'start':'2016-01-16T00:00:00+05:30','end':'2026-11-16T00:00:00+05:30'}
    live=c.get('/api/v1/push/digest',params={**params,'mode':'live'}).json()
    assert live['total_available']==0
    archive=c.get('/api/v1/push/digest',params={**params,'mode':'all'}).json()
    assert archive['total_available']==1 and archive['important'][0]['mode']=='replay'
    assert archive['important'][0]['published_date']=='2025-07-29'
    assert archive['archive_coverage']['stored_filings']==1 and archive['archive_coverage']['exhaustive'] is False

    assert archive['archive_coverage']['companies_with_filings']==1
    assert sum(c['stored_filings'] for c in archive['archive_coverage']['by_company'])==1
