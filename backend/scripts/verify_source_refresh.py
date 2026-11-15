import json,time
from pathlib import Path
import httpx
base='http://127.0.0.1:8001/api/v1'
with httpx.Client(timeout=15) as c:
 r=c.post(base+'/push/refresh',json={});r.raise_for_status();requested=r.json()
 print('Refresh request:',requested['status'],flush=True)
 for _ in range(60):
  state=c.get(base+'/push/refresh-status').json()
  if state['status']!='running':break
  time.sleep(1)
 data=c.get(base+'/push/digest?mode=live').json()
 checks=data.get('source_checks',[])
 report={'request_status':requested['status'],'coordinator':state,'source_checks':checks,'matching_stored_portfolio_filings':data['total_available'],
         'coverage':data['coverage']}
 Path(__file__).resolve().parents[2].joinpath('docs/verification/source-refresh.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 assert checks and all(not s['last_error'] and not s['overdue'] for s in checks),'Check source failure report; previously verified data remains available.'
