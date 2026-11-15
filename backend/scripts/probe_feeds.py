import json,time
from pathlib import Path
from datetime import datetime,timezone
import httpx
urls=[
'https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml',
'https://www.tcs.com/investor-relations',
'https://www.tcs.com/investor-relations/financial-statements',
'https://www.ril.com/investors/events-presentations',
'https://rilstaticasset.akamaized.net/sites/default/files/2025-07/SE_29072025.pdf',
'https://rilstaticasset.akamaized.net/sites/default/files/2025-04/25042025_Media_Release_RIL_Q4_FY2024_25_Financial_and_Operational_Performance.pdf',
]
folder=Path(__file__).resolve().parents[2]/'docs'/'source-probes';out=[]
with httpx.Client(timeout=15,follow_redirects=True,headers={'User-Agent':'FINN-prototype/0.2 (educational source accessibility check)'}) as c:
 for i,url in enumerate(urls,30):
  row={'requested_url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
  try:
   r=c.get(url);p=folder/f'{i}.bin';p.write_bytes(r.content);row.update(status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type'),bytes=len(r.content),local_file=str(p.relative_to(folder.parent.parent)))
  except httpx.HTTPError as e: row['error']=str(e)
  out.append(row);print(json.dumps(row),flush=True);time.sleep(1.5)
(folder/'feeds.json').write_text(json.dumps(out,indent=2))
