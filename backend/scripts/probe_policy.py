import httpx,json
from datetime import datetime,timezone
from pathlib import Path
u='https://www.tcs.com/who-we-are/legal/legal-disclaimer'
r=httpx.get(u,timeout=20,follow_redirects=True,headers={'User-Agent':'FINN-prototype/0.2 (personal educational research)'})
p=Path(__file__).resolve().parents[2]/'docs/source-probes/45.bin';p.write_bytes(r.content)
row={'requested_url':u,'final_url':str(r.url),'status':r.status_code,'completed_at':datetime.now(timezone.utc).isoformat(),'content_type':r.headers.get('content-type'),'local_file':'docs/source-probes/45.bin'}
p.with_suffix('.json').write_text(json.dumps(row,indent=2));print(json.dumps(row))
