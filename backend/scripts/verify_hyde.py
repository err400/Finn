"""Exercise a running FINN process. Never reads or prints a credential."""
import json
from pathlib import Path
import httpx
base='http://127.0.0.1:8001/api/v1'
with httpx.Client(timeout=65) as client:
    health=client.get(base+'/health');health.raise_for_status()
    print('Backend reachable:',health.status_code,flush=True)
    response=client.post(base+'/research',json={'ticker':'RELIANCE','workflow':'snapshot','question':'What business segments and financial performance are disclosed in the available primary reports?'})
    response.raise_for_status();data=response.json()
    report={'http_status':response.status_code,'status':data['status'],'model':data.get('model'),'evidence_passages':len(data.get('evidence',[])),
            'verified_claim_count':len((data.get('answer') or {}).get('claims',[])),'model_error':data.get('model_error'),'cache_hit':data.get('cache_hit'),
            'citations':[{'document_id':e['document_id'],'page':e['page'],'url':e['url'],'sha256':e['sha256']} for e in data.get('evidence',[])]}
    path=Path(__file__).resolve().parents[2]/'docs/verification/hyde-synthesis.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
