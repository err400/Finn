"""Prompt privately in YOUR terminal, then copy the existing local workspace to Supabase.
No credential is written to disk or printed. Run before the first Render deployment.
"""
import getpass
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
url=getpass.getpass('Supabase Session-pooler connection URI (hidden): ').strip()
if url.startswith('postgresql://'):url=url.replace('postgresql://','postgresql+psycopg://',1)
if not url.startswith('postgresql+psycopg://'):raise SystemExit('Use the Postgres Session-pooler URI from Supabase Connect')
if 'sslmode=' not in url:url+=('&' if '?' in url else '?')+'sslmode=require'
project=input('Supabase project URL (https://PROJECT.supabase.co): ').strip()
key=getpass.getpass('Supabase server-side service_role key (hidden): ').strip()
env={**os.environ,'FINN_DATABASE_URL':url,'FINN_STORAGE_BACKEND':'supabase','FINN_STORAGE_URL':project,'FINN_STORAGE_KEY':key,'FINN_STORAGE_BUCKET':'finn-private','FINN_BOOTSTRAP_ENABLED':'false','FINN_ACCESS_MODE':'local'}
result=subprocess.run([str(root/'backend/.venv/bin/python'),'-m','app.migrate_local','--source-db','finn.db','--source-blobs','data/blobs'],cwd=root/'backend',env=env,capture_output=True,text=True)
if result.returncode:
    # Suppress driver exceptions, which can contain connection or machine details.
    raise SystemExit('Import failed. Check that the target is empty, bucket private, credentials valid, and network reachable. Local data is unchanged. No credentials were printed.')
print(result.stdout.strip())
