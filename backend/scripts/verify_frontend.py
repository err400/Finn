"""Verify current real frontend API contracts. Creates one labeled UI-check rule,
then pauses it; no secrets or model credentials are read by this script."""
import json
from pathlib import Path
import httpx
base='http://127.0.0.1:8001/api/v1'
report={};rule_id=None
with httpx.Client(timeout=65) as c:
    try:
        r=c.get('http://127.0.0.1:5173/');r.raise_for_status();report['frontend_http']=r.status_code
        r=c.get(base+'/portfolio/overview');r.raise_for_status();overview=r.json();report['portfolio']=overview['summary']
        assert overview['summary']['companies']==18 and overview['summary']['price_coverage']==18
        window=overview['replay_window'];assert window
        digest=c.get(base+'/push/digest',params={'mode':'replay','start':window['start']+'T00:00:00+05:30','end':window['end_exclusive']+'T00:00:00+05:30'});digest.raise_for_status();item=digest.json()['important'][0]
        assert item['citation']['url'] and item['network'][0]['synthetic']
        report['event']={'id':item['id'],'source':item['citation']['url'],'network_person':item['network'][0]['name'],'degree':item['network'][0]['degree']}
        docs=c.get(base+'/data/companies/'+item['ticker']+'/documents');docs.raise_for_status();assert docs.json()['items'];report['company_documents']=len(docs.json()['items'])
        profile=c.get(base+'/network/people/'+str(item['network'][0]['id']));profile.raise_for_status();assert profile.json()['connection_path']
        r=c.post(base+'/push/rules',json={'name':'Frontend verification · 3% historical price move','kind':'price_move','ticker':'RELIANCE','threshold':'3','direction':'absolute','lookback':20});r.raise_for_status();rule_id=r.json()['id']
        evaluate=c.post(base+'/push/evaluate',json={'as_of':'2026-11-02','mode':'replay'});evaluate.raise_for_status()
        trigger=next(a for a in c.get(base+'/push/alerts?limit=500').json() if a['rule_id']==rule_id and a['observed_date']=='2026-11-02')
        report['alert']={'triggering_value':trigger['evidence']['triggering_value'],'threshold':trigger['evidence']['threshold'],'observed_date':trigger['observed_date'],'source':trigger['evidence']['sources'][0]['url']}
        paused=c.patch(base+'/push/rules/'+str(rule_id),json={'enabled':False});paused.raise_for_status();assert paused.json()['enabled'] is False;report['rule_saved_and_paused']=True
        saved=next(r for r in c.get(base+'/push/rules').json() if r['id']==rule_id);assert saved['enabled'] is False
        r=c.post(base+'/research',json={'ticker':'RELIANCE','workflow':'snapshot','question':'What business segments and financial performance are disclosed in the available primary reports?'});r.raise_for_status();research=r.json()
        assert research['status']=='completed' and research['answer']['claims'] and research['network']
        report['research']={'status':research['status'],'cache_hit':research['cache_hit'],'claims':len(research['answer']['claims']),'evidence_passages':len(research['evidence']),'calculated_metrics':len(research['financials']['metrics']),'source_period_end':research['evidence_period_end']}
        e=c.options(base+'/push/rules/'+str(rule_id),headers={'Origin':'http://127.0.0.1:5173','Access-Control-Request-Method':'PATCH','Access-Control-Request-Headers':'content-type'});assert e.status_code==200 and 'PATCH' in e.headers.get('access-control-allow-methods','');report['browser_cors_patch']=True
        report['visual_qa']='Desktop user screenshots inspected; direct browser automation denied by computer-use permissions. Mobile/desktop navigation is tested in jsdom, not a browser layout engine.'
        Path(__file__).resolve().parents[2].joinpath('docs/verification/frontend-live.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        if rule_id:c.patch(base+'/push/rules/'+str(rule_id),json={'enabled':False})
