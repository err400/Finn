import json,time
from pathlib import Path
from datetime import datetime,timezone
import httpx
urls=[
'https://www.nseindia.in/static/rss-feed',
'https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2024-25/ar/annual-report-2024-2025.pdf',
'https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2024-25/q4/Management%20Commentary/Transcript%20of%20the%20Q4%202024-25%20Earnings%20Conference%20Call%20held%20at%201900%20hrs%20IST%20on%20Apr%2010%2C%202025.pdf',
'https://www.ril.com/investor/resource-center/corporate-announcements?page=17',
'https://www.infosys.com/investors/documents/exchange-filings/2025/financial-results-q3.pdf',
'https://www.bseindia.com/xml-data/corpfiling/AttachLive/2124f834-2285-4a0a-8a01-7cc9ef541adb.pdf',
]
folder=Path(__file__).resolve().parents[2]/'docs'/'source-probes'; out=[]
with httpx.Client(timeout=15,follow_redirects=True,headers={'User-Agent':'FINN-prototype/0.2 (educational source accessibility check)'}) as c:
 for i,url in enumerate(urls,20):
  row={'requested_url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
  try:
   r=c.get(url); path=folder/f'{i:02d}'+Path('x') if False else folder/f'{i:02d}.bin';path.write_bytes(r.content)
   row.update(status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type'),bytes=len(r.content),local_file=str(path.relative_to(folder.parent.parent)))
  except httpx.HTTPError as e:row['error']=str(e)
  out.append(row); print(json.dumps(row),flush=True);time.sleep(1.5)
(folder/'additional.json').write_text(json.dumps(out,indent=2))
