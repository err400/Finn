"""Small explicit accessibility probe. Never bypass challenges or enumerate exchange APIs."""
import json, time
from pathlib import Path
from datetime import datetime, timezone
import httpx
URLS = [
 'https://query1.finance.yahoo.com/v8/finance/chart/INFY.NS?range=1mo&interval=1d',
 'https://www.nseindia.com/static/nse-terms-of-use',
 'https://www.bseindia.com/robots.txt',
 'https://www.bseindia.com/static/about/termsofuse.aspx',
 'https://www.bseindia.com/data/xml/announcements.xml',
 'https://www.infosys.com/robots.txt',
 'https://www.infosys.com/investors/reports-filings/quarterly-results/2024-2025/q3.html',
 'https://www.infosys.com/investors/reports-filings/annual-report/annual/documents/infosys-ar-25.pdf',
 'https://www.tcs.com/robots.txt',
 'https://www.tcs.com/who-we-are/investor-relations',
 'https://www.ril.com/robots.txt',
 'https://www.ril.com/investors/financial-reporting',
]
out=[]
folder=Path(__file__).resolve().parents[2]/'docs'/'source-probes'; folder.mkdir(parents=True,exist_ok=True)
with httpx.Client(timeout=30,follow_redirects=True,headers={'User-Agent':'FINN-prototype/0.2 (educational source accessibility check)'}) as client:
 for i,url in enumerate(URLS):
  row={'requested_url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
  try:
   r=client.get(url)
   row.update(status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type'),bytes=len(r.content))
   extension='pdf' if r.content.startswith(b'%PDF') else 'txt'
   path=folder/f'{i:02d}.{extension}'; path.write_bytes(r.content)
   row['local_file']=str(path.relative_to(folder.parent.parent))
   if 'json' in r.headers.get('content-type',''):
    try: row['json_keys']=list(r.json())[:10]
    except ValueError: pass
  except httpx.HTTPError as exc: row['error']=str(exc)
  out.append(row); print(json.dumps(row),flush=True); time.sleep(1.5)
(folder/'results.json').write_text(json.dumps(out,indent=2))
