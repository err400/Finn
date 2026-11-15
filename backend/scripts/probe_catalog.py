import json,time
from pathlib import Path
from datetime import datetime,timezone
import httpx
urls=[
'https://www.ril.com/sites/default/files/2025-04/Q4_FY2024_25_Transcript.pdf',
'https://rilstaticasset.akamaized.net/sites/default/files/2025-08/RIL-Integrated-Annual-Report-2024-25.pdf',
'https://www.tcs.com/content/dam/tcs/pdf/discover-tcs/investor-relations/corporate-actions/2024-25/SE-Letter-CS.pdf',
'https://www.tcs.com/who-we-are/legal/tcs-com-terms-of-use',
'https://www.ril.com/legal-notice',
]
folder=Path(__file__).resolve().parents[2]/'docs'/'source-probes';out=[]
with httpx.Client(timeout=20,follow_redirects=True,headers={'User-Agent':'FINN-prototype/0.2 (personal educational research)'}) as c:
 for i,url in enumerate(urls,40):
  row={'requested_url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
  try:
   r=c.get(url);p=folder/f'{i}.bin';p.write_bytes(r.content);row.update(completed_at=datetime.now(timezone.utc).isoformat(),status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type'),bytes=len(r.content),local_file=str(p.relative_to(folder.parent.parent)))
  except httpx.HTTPError as e:row['error']=str(e)
  out.append(row);print(json.dumps(row),flush=True);time.sleep(2)
(folder/'catalog.json').write_text(json.dumps(out,indent=2))
