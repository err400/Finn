"""Verify actual stored data through the live API. Creates labeled test rules then pauses them.
No model credentials are read. Research verification is handled separately by verify_hyde.py.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
import httpx
BASE='http://127.0.0.1:8001/api/v1'
with httpx.Client(timeout=30) as c:
    health=c.get(BASE+'/health');health.raise_for_status()
    assert health.json()['providers']['llm']['configured']
    status=c.get(BASE+'/data/status').json()
    portfolio=c.get(BASE+'/portfolio').json()
    price_candidates=[];volume_candidates=[]
    for company in portfolio:
        rows=c.get(BASE+'/data/companies/'+company['ticker']+'/prices').json()['items']
        rows=sorted(rows,key=lambda r:r['trading_date'])
        for i,row in enumerate(rows):
            if i and (date.fromisoformat(row['trading_date'])-date.fromisoformat(rows[i-1]['trading_date'])).days<=7:
                move=(Decimal(row['close'])/Decimal(rows[i-1]['close'])-1)*100
                price_candidates.append((abs(move),row['trading_date'],company['ticker']))
            if i>=20:
                previous=rows[i-20:i]
                if (date.fromisoformat(row['trading_date'])-date.fromisoformat(previous[0]['trading_date'])).days<=80:
                    average=sum(Decimal(p['volume']) for p in previous)/20
                    if average>0:volume_candidates.append((Decimal(row['volume'])/average,row['trading_date'],company['ticker']))
    p=max(price_candidates);v=max(volume_candidates)
    checks=[];created=[]
    try:
        for kind,candidate,threshold in [('price_move',p,'3'),('volume_spike',v,'2')]:
            _,day,ticker=candidate
            r=c.post(BASE+'/push/rules',json={'name':'Demo validation · '+kind,'kind':kind,'ticker':ticker,'threshold':threshold,'lookback':20});r.raise_for_status();rule_id=r.json()['id'];created.append(rule_id)
            evaluation=c.post(BASE+'/push/evaluate',json={'as_of':day,'mode':'replay'});evaluation.raise_for_status()
            alerts=c.get(BASE+'/push/alerts?limit=500').json();trigger=next((a for a in alerts if a['rule_id']==rule_id),None)
            assert trigger is not None
            checks.append({'kind':kind,'ticker':ticker,'observation_date':day,'triggering_value':trigger['evidence']['triggering_value'],'threshold':threshold,'sources':trigger['evidence']['sources']})
        r=c.post(BASE+'/push/rules',json={'name':'Demo validation · operating-agreement disclosure','kind':'announcement_category','ticker':'RELIANCE','categories':['press_release']});r.raise_for_status();rule_id=r.json()['id'];created.append(rule_id)
        e=c.post(BASE+'/push/evaluate',json={'as_of':'2025-07-29','mode':'replay'});e.raise_for_status()
        alert=next(a for a in c.get(BASE+'/push/alerts?limit=500').json() if a['rule_id']==rule_id)
        assert alert['evidence']['network'][0]['synthetic']
        checks.append({'kind':'announcement_category','ticker':'RELIANCE','observation_date':'2025-07-29','triggering_value':alert['evidence']['triggering_value'],'sources':alert['evidence']['sources']})
        digest=c.get(BASE+'/push/digest',params={'mode':'replay','start':'2025-07-29T00:00:00+05:30','end':'2025-07-30T00:00:00+05:30'});digest.raise_for_status();d=digest.json();item=d['important'][0]
        assert item['network'][0]['name']=='Priya Demo Menon' and item['network'][0]['degree']==2
        report={'data_counts':status['counts'],'portfolio_companies':len(portfolio),'llm_configured':True,'alert_checks':checks,
                'event_to_person':{'filing_id':item['id'],'publication_date':item['published_date'],'source':item['citation']['url'],'mode':d['mode'],'recommended_synthetic_person':item['network'][0]['name'],'degree':item['network'][0]['degree']},
                'test_rules':'Created for verification then paused; historical trigger evidence retained.'}
        output=Path(__file__).resolve().parents[2]/'docs/verification/workflows.json';output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        for rule_id in created:c.patch(BASE+'/push/rules/'+str(rule_id),json={'enabled':False}).raise_for_status()
