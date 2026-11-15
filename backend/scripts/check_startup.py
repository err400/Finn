"""Start the actual ASGI server against a disposable database and check readiness."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx

with tempfile.TemporaryDirectory(prefix='finn-startup-') as folder:
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'FINN_DATABASE_URL':'sqlite:///'+folder+'/test.db','FINN_DATA_DIR':folder+'/data','FINN_ACCESS_MODE':'local','FINN_STORAGE_BACKEND':'local','FINN_BOOTSTRAP_ENABLED':'false','FINN_AUTO_REFRESH_ENABLED':'false'}
    process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--loop','asyncio','--no-proxy-headers'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                r=httpx.get(f'http://127.0.0.1:{port}/api/v1/health',timeout=1)
                if r.status_code==200:break
            except httpx.HTTPError:pass
            if process.poll() is not None:raise RuntimeError('Backend exited during startup')
            time.sleep(.2)
        else:raise RuntimeError('Backend did not become ready')
        assert r.json()['database']=='ok'
        overview=httpx.get(f'http://127.0.0.1:{port}/api/v1/portfolio/overview').json()
        assert overview['summary']['companies']==18
        print(json.dumps({'startup':'passed','health':'ok','seeded_companies':18,'database':'disposable SQLite'}))
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
