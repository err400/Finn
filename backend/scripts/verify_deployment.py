"""Verify local or deployed frontend/API/CORS. Reviewer code is read from process env only."""
import argparse
import json
import os
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--frontend',required=True)
parser.add_argument('--backend',required=True,help='Origin without /api/v1')
parser.add_argument('--research',action='store_true',help='Make one synthesis request; may incur provider cost')
parser.add_argument('--report',type=Path,default=Path('../docs/verification/deployment-smoke.json'))
args=parser.parse_args();front=args.frontend.rstrip('/');api=args.backend.rstrip('/')+'/api/v1'
headers={}
if os.environ.get('FINN_REVIEWER_TOKEN'):headers['Authorization']='Bearer '+os.environ['FINN_REVIEWER_TOKEN']
report={'frontend':front,'backend':args.backend,'hosted':not args.backend.startswith('http://127.0.0.1')}
with httpx.Client(timeout=90,follow_redirects=False) as client:
    page=client.get(front);page.raise_for_status();assert '<div id="root">' in page.text
    report['frontend_served']=True
    health=client.get(api+'/health');health.raise_for_status();assert health.json()['database']=='ok'
    report['access_mode']=health.json().get('access_mode')
    report['storage_ephemeral']=health.json().get('ephemeral_storage')
    r=client.get(api+'/portfolio/overview',headers={**headers,'Origin':front});r.raise_for_status()
    assert r.headers.get('access-control-allow-origin')==front
    overview=r.json();assert len(overview['items'])==18;report['portfolio']=overview['summary']
    pre=client.options(api+'/research',headers={'Origin':front,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
    assert pre.status_code==200 and 'authorization' in pre.headers.get('access-control-allow-headers','').lower();report['cors_verified']=True
    digest=client.get(api+'/push/digest',params={'mode':'all','start':'2016-01-01T00:00:00+05:30'},headers=headers);digest.raise_for_status()
    data=digest.json();report['announcements']=data['total_available'];report['archive_coverage']=data.get('archive_coverage')
    material=next((i for i in data['important'] if i['network']),None)
    if material:
        assert material['citation']['url'] and all(p['synthetic'] for p in material['network']);report['event_to_person_verified']=True
    if args.research:
        research=client.post(api+'/research',headers=headers,json={'ticker':'PIDILITIND','workflow':'snapshot','question':'What business segments and operating performance are disclosed in the primary reports?'})
        research.raise_for_status();result=research.json()
        assert result['evidence'] and result['status'] in {'completed','evidence_only','synthesis_unavailable'}
        for claim in (result.get('answer') or {}).get('claims',[]):
            for citation in claim['citations']:
                passage=next(e for e in result['evidence'] if e['chunk_id']==citation['chunk_id'])
                assert citation['quote'] in ' '.join(passage['text'].split()) and citation['url'].endswith('#page='+str(citation['page']))
        report['research']={'status':result['status'],'passages':len(result['evidence']),'verified_claims':len((result.get('answer') or {}).get('claims',[]))}
args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
