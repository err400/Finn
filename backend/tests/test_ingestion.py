"""Offline tests: generated prices and PDFs are synthetic test inputs, never demo data."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, func
from app.main import app
from app.api.ingestion import service, RefreshRequest
from app.core.config import get_settings
from app.models.entities import Company
from app.models.ingestion import RawSnapshot, EodPrice, FilingEvent, FilingOrigin, FetchCache, HostThrottle
from app.providers.contracts import ProviderError, PrimaryDocument
from app.providers.http import CachedHttpFetcher
from app.providers.yahoo import YahooChartProvider
from app.providers.exchange_rss import ExchangeRssProvider
from app.services.ingestion import IngestionService, refresh_lock
from app.services.normalization import normalize_symbol, canonical_url, filing_datetime, category_for

NOW=datetime(2025,2,1,tzinfo=timezone.utc)
URL='https://query1.finance.yahoo.com/v8/finance/chart/INFY.NS'
PDF_URL='https://www.ril.com/sites/default/files/test-fixture.pdf'
START,END=date(2025,1,1),date(2025,2,1)

def pdf(text='SYNTHETIC TEST DOCUMENT RELIANCE 500325'):
    stream=f'BT /F1 12 Tf 30 700 Td ({text}) Tj ET'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    body=bytearray(b'%PDF-1.4\n');offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(body));body.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(body);body.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:body.extend(f'{offset:010d} 00000 n \n'.encode())
    body.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    return bytes(body)

def chart(symbol='INFY.NS',missing=False):
    return {'chart':{'error':None,'result':[{'meta':{'symbol':symbol,'currency':'INR','exchangeTimezoneName':'Asia/Kolkata','instrumentType':'EQUITY','longName':'Synthetic test issuer'},
      'timestamp':[1735799100,1735885500], 'indicators':{'quote':[{'open':[10,11],'high':[12,13],'low':[9,10],'close':[11,None if missing else 12],'volume':[100,200]}],'adjclose':[{'adjclose':[10.5,11.5]}]}}]}}

class Clock:
    def __init__(self):self.value=NOW
    def __call__(self):return self.value
    def sleep(self,seconds):self.value+=timedelta(seconds=seconds)

def fetcher(db,path,handler,clock=None):
    clock=clock or Clock()
    return CachedHttpFetcher(db,path,client=httpx.Client(transport=httpx.MockTransport(handler)),min_interval=0,clock=clock,sleeper=clock.sleep)

@pytest.mark.parametrize('raw,expected',[('infy.ns',('NSE','INFY')),('NSE:M&M',('NSE','M&M')),('BSE:500325',('BSE','500325')),('500325.BO',('BSE','500325'))])
def test_symbols(raw,expected):assert normalize_symbol(raw)==expected

@pytest.mark.parametrize('raw',['../INFY','https://bad','INFY;DROP','BSE:INFY.NS',''])
def test_bad_symbols(raw):
    with pytest.raises(ValueError):normalize_symbol(raw)

def test_normalization():
    assert canonical_url('http://WWW.RIL.COM/sites/default/files/a%20b.pdf?utm_source=x#page=2')=='https://www.ril.com/sites/default/files/a%20b.pdf'
    assert filing_datetime('16-Nov-2026 00:28:42').isoformat()=='2026-11-15T18:58:42+00:00'
    assert filing_datetime('Mon, 16 Nov 2026 00:28:42 +0530').isoformat()=='2026-11-15T18:58:42+00:00'
    assert category_for('Earnings Call Transcript')=='earnings_call'
    assert category_for('Financial results for quarter')=='results'
    assert category_for('Unknown disclosure')=='unclassified'

@pytest.mark.parametrize('url',['http://127.0.0.1/secret','https://example.com/doc.pdf','https://www.ril.com@127.0.0.1/sites/default/files/x.pdf'])
def test_source_allowlist(client,tmp_path,url):
    _,factory=client
    with factory() as db:
        f=fetcher(db,tmp_path,lambda r:pytest.fail('Network should not be called'))
        with pytest.raises(ProviderError):f.get(url,10)

def test_cache_revalidation_stale_integrity(client,tmp_path):
    _,factory=client;requests=[];clock=Clock()
    responses=[httpx.Response(200,json=chart(),headers={'etag':'v1'}),httpx.Response(304),httpx.Response(503),httpx.Response(503)]
    def handler(r):requests.append(r);return responses.pop(0)
    with factory() as db:
        f=fetcher(db,tmp_path,handler,clock)
        first=f.get(URL,10);assert first.cache_status=='network'
        assert f.get(URL,10).cache_status=='cache' and len(requests)==1
        clock.sleep(11);assert f.get(URL,10).cache_status=='revalidated'
        assert requests[1].headers['if-none-match']=='v1'
        clock.sleep(11);stale=f.get(URL,10)
        assert stale.cache_status=='stale' and '503' in stale.warning and stale.fetched_at==first.fetched_at
        (tmp_path/'blobs'/first.sha256).write_bytes(b'tampered')
        with pytest.raises(ProviderError,match='integrity'):f.body(db.get(RawSnapshot,first.snapshot_id))

def test_retry_after_and_redirect(client,tmp_path):
    _,factory=client;requests=[]
    def handler(r):requests.append(r);return httpx.Response(429,headers={'retry-after':'120'})
    with factory() as db:
        f=fetcher(db,tmp_path,handler)
        with pytest.raises(ProviderError) as e:f.get(URL,60)
        assert e.value.code=='rate_limited'
        with pytest.raises(ProviderError) as e:f.get(URL,60,True)
        assert e.value.code=='cooldown' and len(requests)==1
        db.execute(__import__('sqlalchemy').delete(HostThrottle));db.commit()
        clock=Clock();clock.sleep(121)
        f=fetcher(db,tmp_path,lambda r:httpx.Response(302,headers={'location':'http://127.0.0.1/private'}),clock)
        with pytest.raises(ProviderError) as e:f.get(URL,60)
        assert e.value.code=='source_not_allowed'

def test_bad_html_does_not_replace_pdf(client,tmp_path):
    _,factory=client;responses=[httpx.Response(200,content=pdf()),httpx.Response(200,text='<html>Access denied</html>')]
    with factory() as db:
        f=fetcher(db,tmp_path,lambda r:responses.pop(0));good=f.get(PDF_URL,60);stale=f.get(PDF_URL,60,True)
        assert stale.cache_status=='stale' and stale.sha256==good.sha256
        assert db.scalar(select(func.count()).select_from(RawSnapshot))==1

def test_prices_idempotency_and_identity(client,tmp_path):
    _,factory=client
    with factory() as db:
        f=fetcher(db,tmp_path,lambda r:httpx.Response(200,json=chart()));svc=IngestionService(db,tmp_path,fetcher=f)
        first=svc.refresh('INFY.NS','prices','live',START,END);assert first.status=='success' and first.details['inserted']==2
        second=svc.refresh('INFY','prices','live',START,END);assert second.status=='success' and second.details['inserted']==0
        assert db.scalar(select(func.count()).select_from(EodPrice))==2
        point=db.scalar(select(EodPrice));assert point.volume==100 and point.close=='11' and point.adjusted_close=='10.5'
        bad=fetcher(db,tmp_path,lambda r:httpx.Response(200,json=chart('WRONG.NS')))
        with pytest.raises(ProviderError,match='unexpected'):YahooChartProvider(bad).history('INFY',START,END,True)
        assert db.scalar(select(func.count()).select_from(EodPrice))==2

def test_missing_rows_and_new_ticker(client,tmp_path):
    _,factory=client
    with factory() as db:
        svc=IngestionService(db,tmp_path,fetcher=fetcher(db,tmp_path,lambda r:httpx.Response(200,json=chart('OTHER.NS',True))))
        run=svc.refresh('OTHER','prices','live',START,END)
        assert run.status=='partial' and run.details['skipped']==1
        assert db.scalar(select(Company).where(Company.ticker=='OTHER')).name=='Synthetic test issuer'
        assert db.scalar(select(func.count()).select_from(EodPrice))==1

def test_network_failure_audited(client,tmp_path):
    _,factory=client
    with factory() as db:
        def timeout(r):raise httpx.ReadTimeout('timeout')
        svc=IngestionService(db,tmp_path,fetcher=fetcher(db,tmp_path,timeout));run=svc.refresh('INFY','prices','live',START,END)
        assert run.status=='failed' and run.details['error_code']=='network_error' and run.completed_at
        assert db.scalar(select(func.count()).select_from(Company))==18

def test_rss_schema_dates_html(client,tmp_path):
    _,factory=client
    xml=b'<rss><channel><item><title>Reliance Industries Limited (500325)</title><scripcode>500325</scripcode><description>Financial results</description><link>https://www.bseindia.com/xml-data/corpfiling/x.pdf</link><pubDate>29-Jul-2025 18:30:00</pubDate></item><item><title>Missing date</title></item></channel></rss>'
    with factory() as db:
        batch=ExchangeRssProvider('bse_rss',fetcher(db,tmp_path,lambda r:httpx.Response(200,content=xml))).latest()
        assert len(batch.items)==1 and batch.rejected==1 and batch.items[0].bse_code=='500325' and batch.items[0].published_at.hour==13
        with pytest.raises(ProviderError):ExchangeRssProvider('nse_rss',fetcher(db,tmp_path,lambda r:httpx.Response(200,text='<html>blocked</html>'))).latest()

def test_documents_and_replay_preserve_date_precision(client,tmp_path):
    _,factory=client
    c=PrimaryDocument('RELIANCE','Synthetic replay test','exchange_filing',PDF_URL,PDF_URL,'test',date(2025,7,29),'Synthetic test metadata',replay_announcement=True,expected_text=['RELIANCE'])
    catalog=SimpleNamespace(discover=lambda t:[c] if t=='RELIANCE' else [])
    with factory() as db:
        svc=IngestionService(db,tmp_path,fetcher=fetcher(db,tmp_path,lambda r:httpx.Response(200,content=pdf())),documents=catalog)
        for _ in range(2):assert svc.refresh('RELIANCE','filings','replay',START,END).status=='success'
        assert db.scalar(select(func.count()).select_from(FilingEvent))==1
        assert db.scalar(select(func.count()).select_from(FilingOrigin))==1
        event=db.scalar(select(FilingEvent));assert event.published_at is None and event.publication_precision=='date' and event.published_date==date(2025,7,29)
        assert svc.resolve('500325.BO')[0]=='RELIANCE'
        assert svc.refresh('INFY','documents','live',START,END).status=='no_data'
        assert 'Historical replay' in svc.refresh('RELIANCE','filings','replay',START,END).details['label']

def test_cross_exchange_dedup_and_late_attachment(client,tmp_path):
    _,factory=client
    with factory() as db:
        f=fetcher(db,tmp_path,lambda r:httpx.Response(200,content=pdf()));svc=IngestionService(db,tmp_path,fetcher=f)
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'));candidate=PrimaryDocument('RELIANCE','Synthetic','exchange_filing',PDF_URL,PDF_URL,'test')
        doc=svc.store_document(company,candidate,f.get(PDF_URL,60));day=date(2025,7,29);stamp=datetime(2025,7,29,12,tzinfo=timezone.utc)
        svc._store_filing(company,'Financial results',PDF_URL,'nse_rss','29-Jul-2025 17:30:00',stamp,day,'live',None,doc.snapshot_id)
        svc._store_filing(company,'Financial results','https://www.bseindia.com/xml-data/corpfiling/other.pdf','bse_rss','29-Jul-2025 17:31:00',stamp,day,'live',doc,doc.snapshot_id)
        svc._store_filing(company,'Financial results',PDF_URL,'nse_rss','29-Jul-2025 17:30:00',stamp,day,'live',doc,doc.snapshot_id)
        assert db.scalar(select(func.count()).select_from(FilingEvent))==1
        assert db.scalar(select(func.count()).select_from(FilingOrigin))==2

def test_api_auth_reads_validation_and_remote_restriction(client,tmp_path,monkeypatch):
    c,factory=client;settings=get_settings();monkeypatch.setattr(settings,'ingest_token',SecretStr('test-only-token'));monkeypatch.setattr(settings,'data_dir',tmp_path)
    assert c.get('/api/v1/data/companies/INFY/prices').json()['items']==[]
    assert c.get('/api/v1/data/companies/NOPE/prices').status_code==404
    assert c.get('/api/v1/data/companies/500325.BO/prices').status_code==422
    assert c.post('/api/v1/data/refresh',json={'ticker':'INFY','dataset':'prices'}).status_code==401
    headers={'x-finn-ingest-token':'test-only-token'}
    assert c.post('/api/v1/data/refresh',headers=headers,json={'ticker':'../bad','dataset':'prices'}).status_code==422
    with factory() as db:
        svc=IngestionService(db,tmp_path,fetcher=fetcher(db,tmp_path,lambda r:httpx.Response(200,json=chart())))
        app.dependency_overrides[service]=lambda:svc
        r=c.post('/api/v1/data/refresh',headers=headers,json={'ticker':'INFY','dataset':'prices','start':'2025-01-01','end':'2025-02-01'})
        assert r.status_code==200 and r.json()['status']=='success'
        assert c.get('/api/v1/data/companies/INFY/prices').json()['count']==2
        assert c.get('/api/v1/data/status').json()['counts']['prices']==2
        assert len(c.get('/api/v1/data/runs').json())==1
    assert TestClient(app,client=('203.0.113.10',1234)).get('/api/v1/data/status').status_code==403

def test_refresh_lock_and_modes(tmp_path):
    with refresh_lock(tmp_path):
        with pytest.raises(ProviderError,match='Another'):
            with refresh_lock(tmp_path):pass
    with pytest.raises(ValueError):RefreshRequest(ticker='INFY',dataset='prices',mode='replay')

def test_failed_sources_are_negative_cached_to_avoid_repeated_requests(client,tmp_path):
    _,factory=client;clock=Clock();calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls)<=2 else httpx.Response(200,json=chart())
    with factory() as db:
        f=fetcher(db,tmp_path,handler,clock)
        with pytest.raises(ProviderError):f.get(URL,60)
        assert len(calls)==2
        with pytest.raises(ProviderError) as exc:f.get(URL,60)
        assert exc.value.code=='cooldown' and len(calls)==2
        clock.sleep(61)
        assert f.get(URL,60).cache_status=='network' and len(calls)==3
