"""Release regressions: private demo boundary, durable storage, grounding and edge cases."""
import hashlib
import os
from types import SimpleNamespace
import httpx
import pytest
from sqlalchemy import select, text
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.core import access
from app.providers.storage import SupabaseBlobStore
from app.providers.contracts import ProviderError
from app.providers.llm import validate_synthesis
from app.services.financials import financial_comparisons
from app.models.entities import Company
from test_intelligence import primary


def test_public_demo_requires_durable_configuration_and_accepts_legacy_mode():
    with pytest.raises(ValueError):Settings(_env_file=None,access_mode='public_demo')
    cfg=Settings(_env_file=None,access_mode='reviewer',ephemeral_storage=True)
    assert cfg.access_mode=='public_demo' and cfg.reviewer_token is None


def test_public_demo_opens_without_code_but_protects_operator_and_raw_sources(client,monkeypatch):
    c,_=client
    cfg=Settings(_env_file=None,access_mode='public_demo',ephemeral_storage=True)
    monkeypatch.setattr(access,'get_settings',lambda:cfg)
    import app.api.ingestion as ingestion
    monkeypatch.setattr(ingestion,'get_settings',lambda:cfg)
    access._windows.clear()
    assert c.get('/api/v1/network').status_code==200
    assert c.get('/api/v1/portfolio').status_code==200
    assert c.get('/api/v1/portfolio/overview').status_code==200
    assert c.get('/api/v1/network',headers={'Origin':'https://evil.example'}).status_code==403
    assert c.get('/api/v1/data/documents/1/file').status_code==403
    assert c.get('/api/v1/data/documents/1/pages/1').status_code==403
    assert c.post('/api/v1/data/refresh',json={'ticker':'RELIANCE','dataset':'filings'}).status_code==503
    assert c.get('/api/v1/portfolio').headers['cache-control']=='no-store'
    access._windows.clear()


def test_reviewer_budget_and_non_finite_thresholds(client):
    access._windows.clear()
    access.check_budget('test',1,60)
    with pytest.raises(Exception) as caught:access.check_budget('test',1,60)
    assert caught.value.status_code==429
    access._windows.clear()
    c,_=client
    for value in ['NaN','Infinity','-Infinity','0','-2','10001']:
        assert c.post('/api/v1/push/rules',json={'name':'Invalid','kind':'price_move','threshold':value}).status_code==422
    assert c.post('/api/v1/research',json={'ticker':'123456.BO','question':'What is the business?'}).status_code==422


def test_empty_digest_missing_documents_and_no_network(client):
    c,factory=client
    result=c.get('/api/v1/push/digest').json()
    assert result['total_available']==0 and result['important']==[]
    research=c.post('/api/v1/research',json={'ticker':'UNSUPPORTED','question':'What is the business?'}).json()
    assert research['status']=='insufficient_evidence' and not research['evidence'] and research['answer'] is None
    assert c.get('/api/v1/network/recommendations?company=CERA').json()['recommendations']==[]


def test_conflicting_newest_financial_values_are_withheld(client):
    _,factory=client
    table='CONSOLIDATED FINANCIAL HIGHLIGHTS\n(₹ in crore)\n4Q FY25 3Q FY25 4Q FY24 % chg. Y-o-Y FY25 FY24\n1 Gross Revenue {value} 100 80 37.5 410 300\n'
    with factory() as db:
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
        primary(db,company.id,'quarterly_results',table.format(value=110),'conflict-one')
        primary(db,company.id,'quarterly_results',table.format(value=120),'conflict-two')
        result=financial_comparisons(db,company.id)
        assert result['metrics']==[] and result['conflicting_periods']==[{'metric':'gross_revenue','period_end':'2025-03-31'}]


def test_uncited_model_limitation_cannot_smuggle_financial_claims():
    result=validate_synthesis({'claims':[],'limitations':['Revenue was an invented 999 crore.']},[])
    assert '999' not in str(result)


def test_private_storage_round_trip_idempotency_and_safe_failure():
    body=b'%PDF-synthetic storage test';sha=hashlib.sha256(body).hexdigest();objects={}
    settings=SimpleNamespace(storage_url='https://test.supabase.co',storage_bucket='finn-private',storage_key=SimpleNamespace(get_secret_value=lambda:'synthetic-storage-key'))
    def handler(request):
        assert request.headers['authorization']=='Bearer synthetic-storage-key'
        if request.method=='POST':objects[sha]=request.content;return httpx.Response(200,json={'Key':sha})
        assert '/object/authenticated/finn-private/' in request.url.path
        return httpx.Response(200,content=objects[sha])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        store=SupabaseBlobStore(settings,client);store.put(sha,body);store.put(sha,body)
        assert store.get(sha)==body
        with pytest.raises(ProviderError):store.put(sha,b'corrupt')
        with pytest.raises(ProviderError):store.get('../private')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(403,text='sensitive provider detail'))) as client:
        with pytest.raises(ProviderError) as caught:SupabaseBlobStore(settings,client).get(sha)
        assert 'sensitive' not in str(caught.value) and 'synthetic-storage-key' not in str(caught.value)


@pytest.mark.skipif(not os.getenv('FINN_TEST_POSTGRES_URL'),reason='Dedicated Postgres integration URL not configured')
def test_postgres_persistence_retrieval_and_sqlite_migration(tmp_path):
    from sqlalchemy.orm import Session
    from app.db.session import Base,make_engine
    from app.db.initialize import initialize_database
    from app.db.seed import seed_demo,DEMO_OWNER
    from app.db.network_seed import seed_network
    from app.services.retrieval import retrieve
    from app.migrate_local import copy_database
    url=os.environ['FINN_TEST_POSTGRES_URL']
    assert url.split('?')[0].endswith('/finn_audit'),'Use a dedicated test database named finn_audit'
    target=make_engine(url)
    Base.metadata.drop_all(target);initialize_database(target)
    source=make_engine('sqlite:///'+str(tmp_path/'source.db'));Base.metadata.create_all(source)
    with Session(source) as db:
        seed_demo(db);seed_network(db)
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
        primary(db,company.id,'annual_report','Synthetic business segments include energy and retail. Operating cash flow is discussed.','durable-ar')
    counts=copy_database(source,target)
    assert counts['companies']==18
    target.dispose()  # Simulate API restart: establish a fresh connection pool.
    target=make_engine(url)
    with Session(target) as db:
        company=db.scalar(select(Company).where(Company.ticker=='RELIANCE'))
        hits,docs=retrieve(db,company.id,'business segments','snapshot')
        assert hits and hits[0]['page']==1 and hits[0]['url'].endswith('#page=1')
        assert db.scalar(text("SELECT relrowsecurity FROM pg_class WHERE relname='companies'")) is True
        # Sequence reset after copy must allow subsequent inserts.
        db.add(Company(ticker='TESTNEW',name='Synthetic test company',sector='test',exchange='NSE'));db.commit()
    with pytest.raises(ValueError):copy_database(source,target)
    Base.metadata.drop_all(target);target.dispose();source.dispose()


def test_concurrent_research_is_bounded_without_duplicate_model_requests(client):
    from app.api.router import research_slot
    c,_=client
    assert research_slot.acquire(blocking=False)
    try:
        r=c.post('/api/v1/research',json={'ticker':'TCS','question':'What is the business?'})
        assert r.status_code==429 and r.headers['retry-after']=='15'
    finally:research_slot.release()


@pytest.mark.parametrize('status,body,expected',[
    (401,{'error':'secret error body'},'storage_auth'),
    (403,{'error':'secret error body'},'storage_auth'),
    (404,{},'bucket_missing'),
    (200,{'public':True},'bucket_public'),
])
def test_import_bucket_diagnostics_do_not_reveal_upstream_errors(status,body,expected):
    from app.cloud_import import check_private_bucket,ImportFailure,MESSAGES
    settings=SimpleNamespace(storage_url='https://test.supabase.co',storage_bucket='finn-private',storage_key=SimpleNamespace(get_secret_value=lambda:'synthetic-test-key'))
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(status,json=body))) as client:
        with pytest.raises(ImportFailure) as caught:check_private_bucket(settings,client)
    assert caught.value.code==expected
    assert 'secret error body' not in MESSAGES[expected] and 'synthetic-test-key' not in MESSAGES[expected]


def test_import_database_error_classification_and_new_secret_key_transport():
    from app.cloud_import import database_error_code,check_private_bucket
    assert database_error_code(SimpleNamespace(orig=SimpleNamespace(sqlstate='28P01')))=='database_auth'
    assert database_error_code(Exception('Tenant or user not found private details'))=='database_tenant'
    assert database_error_code(Exception('connection timed out private host'))=='database_network'
    assert database_error_code(Exception('certificate verify failed private value'))=='database_tls'
    settings=SimpleNamespace(storage_url='https://test.supabase.co',storage_bucket='finn-private',storage_key=SimpleNamespace(get_secret_value=lambda:'sb_secret_synthetic_test'))
    body=b'Synthetic blob';sha=hashlib.sha256(body).hexdigest()
    def handler(request):
        assert request.headers['apikey']=='sb_secret_synthetic_test'
        assert 'authorization' not in request.headers
        return httpx.Response(200,json={'public':False})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        check_private_bucket(settings,client)
        SupabaseBlobStore(settings,client).put(sha,body)


def test_import_helper_encodes_separately_entered_password_and_prints_only_safe_errors(monkeypatch,capsys):
    import importlib.util
    import sys
    from pathlib import Path
    script=Path(__file__).resolve().parents[2]/'scripts/import_cloud_data.py'
    spec=importlib.util.spec_from_file_location('finn_import_helper_test',script)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    uri='postgresql://postgres.test:[YOUR-PASSWORD]@aws-0-region.pooler.supabase.com:5432/postgres'
    password='Synthetic@password?#% /'
    prompts=iter([uri,password,'synthetic-service-key'])
    monkeypatch.setattr(helper.getpass,'getpass',lambda _:next(prompts))
    monkeypatch.setattr('builtins.input',lambda _:'')
    monkeypatch.setattr(sys,'argv',['import_cloud_data.py','--check-only'])
    def worker(command,**kwargs):
        from sqlalchemy.engine import make_url
        parsed=make_url(kwargs['env']['FINN_DATABASE_URL'])
        assert parsed.password==password and parsed.query['sslmode']=='require'
        assert '--check-only' in command and password not in ' '.join(command)
        return SimpleNamespace(stdout=iter(['{"status":"failed","code":"database_auth","message":"upstream invented secret must not print"}\n']),wait=lambda:1)
    monkeypatch.setattr(helper.subprocess,'Popen',worker)
    with pytest.raises(SystemExit) as caught:helper.main()
    assert caught.value.code==1
    output=capsys.readouterr().out
    assert 'database_auth' in output and password not in output and 'synthetic-service-key' not in output
    assert 'upstream invented secret' not in output


def test_storage_import_preflight_retries_transient_connection_failure(monkeypatch):
    from app.cloud_import import check_private_bucket
    import app.cloud_import as importer
    monkeypatch.setattr(importer.time,'sleep',lambda _:None)
    settings=SimpleNamespace(storage_url='https://test.supabase.co',storage_bucket='finn-private',storage_key=SimpleNamespace(get_secret_value=lambda:'synthetic-service-key'))
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:raise httpx.ConnectError('Synthetic transient transport failure',request=request)
        return httpx.Response(200,json={'public':False})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:check_private_bucket(settings,client)
    assert len(calls)==2


def test_model_kill_switch_disables_even_present_credentials():
    from app.providers.llm import OpenAICompatibleModel
    cfg=Settings(_env_file=None,llm_enabled=False,llm_model='synthetic-model',llm_api_key='synthetic-key')
    model=OpenAICompatibleModel(cfg)
    assert not model.configured and model.identity=='disabled'
    with pytest.raises(ProviderError):model.synthesize('Question','snapshot',[])


def test_snapshot_refresh_does_not_fetch_sources(monkeypatch):
    import asyncio
    from app.services.source_refresh import SourceRefreshManager
    import app.core.config as config
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(snapshot_mode=True))
    async def scenario():
        async def forbidden(_):raise AssertionError('Snapshot must not fetch')
        manager=SourceRefreshManager(forbidden)
        assert (await manager.request())['status']=='snapshot' and manager.task is None
    asyncio.run(scenario())


@pytest.mark.parametrize('prefix',['postgresql://','postgres://','postgresql+psycopg://'])
def test_supabase_database_uri_accepts_dashboard_formats_without_secret_output(prefix):
    from sqlalchemy.engine import make_url
    raw=prefix+'postgres.synthetic:synthetic%40password@aws-0-region.pooler.supabase.com:5432/postgres'
    cfg=Settings(_env_file=None,database_url=' "'+raw+'" ')
    uri=make_url(cfg.database_url)
    assert uri.drivername=='postgresql+psycopg' and uri.password=='synthetic@password'
    assert uri.query['sslmode']=='require'
    assert 'synthetic@password' not in repr(cfg) and 'synthetic%40password' not in repr(cfg)


def test_database_placeholder_rejected_without_printing_connection_details():
    with pytest.raises(ValueError) as caught:
        Settings(_env_file=None,database_url='postgresql://postgres.test:[YOUR-PASSWORD]@private-host.supabase.co:5432/postgres')
    assert 'Replace the database password placeholder' in str(caught.value)
    assert 'private-host' not in str(caught.value)


def test_render_separate_database_password_is_encoded_without_ambiguity():
    from sqlalchemy.engine import make_url
    password='Synthetic@4number#?/:%'
    cfg=Settings(_env_file=None,database_password=password,database_url='postgresql://postgres.synthetic:[YOUR-PASSWORD]@aws-0-region.pooler.supabase.com:5432/postgres')
    parsed=make_url(cfg.database_url)
    assert parsed.password==password and parsed.host=='aws-0-region.pooler.supabase.com'
    assert password not in repr(cfg) and parsed.query['sslmode']=='require'


def test_malformed_password_cannot_leak_into_dns_hostname():
    with pytest.raises(ValueError) as caught:
        Settings(_env_file=None,database_url='postgresql://postgres.synthetic:fake@4secret@aws-0-region.pooler.supabase.com:5432/postgres')
    assert 'FINN_DATABASE_PASSWORD separately' in str(caught.value)
    assert '4secret' not in str(caught.value)


def test_portfolio_overview_uses_bounded_database_round_trips(client):
    from sqlalchemy import event
    c,factory=client;engine=factory.kw['bind'];queries=[]
    def record(*args):queries.append(args[2])
    event.listen(engine,'before_cursor_execute',record)
    try:
        response=c.get('/api/v1/portfolio/overview')
        assert response.status_code==200 and response.json()['summary']['companies']==18
        assert len(queries)<=7
    finally:event.remove(engine,'before_cursor_execute',record)


def test_prefetched_network_preserves_ranking_and_avoids_per_person_queries(client):
    from sqlalchemy import event
    from app.services.network import NetworkIntelligence
    from app.db.seed import DEMO_OWNER
    _,factory=client
    with factory() as db:
        baseline=NetworkIntelligence(db,DEMO_OWNER).recommend('RELIANCE',event_title='joint operating agreement')
        service=NetworkIntelligence(db,DEMO_OWNER,preload=True)
        queries=[];engine=factory.kw['bind']
        def record(*args):queries.append(args[2])
        event.listen(engine,'before_cursor_execute',record)
        try:
            assert service.recommend('RELIANCE',event_title='joint operating agreement')==baseline
            assert NetworkIntelligence(db,'another-owner',preload=True).recommend('RELIANCE')['recommendations']==[]
            assert len(queries)<=7  # Only the second owner's bounded preload performs SQL.
        finally:event.remove(engine,'before_cursor_execute',record)
