"""Read-only check of the local API contracts used by the frontend."""
import httpx
with httpx.Client(timeout=10) as c:
 for path in ['/portfolio/overview','/push/digest?mode=live','/push/rules','/push/alerts','/health']:
  r=c.get('http://127.0.0.1:8001/api/v1'+path)
  print(path,r.status_code)
  if path=='/portfolio/overview' and r.status_code==200:print('overview counts:',r.json()['summary'])
  r=c.get('http://127.0.0.1:5173/')
  print('frontend:',r.status_code)
