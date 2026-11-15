import json,time
from pathlib import Path
from datetime import datetime,timezone
import httpx
urls=[
'https://www.pidilite.com/robots.txt',
'https://www.pidilite.com/investor-relations/listing-information',
'https://www.pidilite.com/terms-and-conditions',
'https://www.godeepak.com/robots.txt',
'https://www.godeepak.com/investor-relations/',
'https://www.tcs.com/investor-relations/corporate-actions',
'https://www.ril.com/investor/resource-center/corporate-announcements',
]
folder=Path(__file__).resolve().parents[2]/'docs/source-probes';out=[]
with httpx.Client(timeout=20,follow_redirects=True,headers={'User-Agent':'FINN-prototype/0.3 (personal educational source review)'}) as c:
 for i,url in enumerate(urls,60):
  row={'requested_url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
  try:
   r=c.get(url);p=folder/f'{i}.bin';p.write_bytes(r.content)
   row.update(completed_at=datetime.now(timezone.utc).isoformat(),status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type'),bytes=len(r.content),local_file=str(p.relative_to(folder.parent.parent)))
  except httpx.HTTPError as e:row['error']=str(e)
  out.append(row);print(json.dumps(row),flush=True);time.sleep(2)
(folder/'archive-sources.json').write_text(json.dumps(out,indent=2))
