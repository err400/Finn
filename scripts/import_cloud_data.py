"""Privately prompt in YOUR terminal; safely diagnose or import into Supabase.
No credentials are written to disk, command arguments, or diagnostic output.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true',help='Check connection and private bucket without copying data')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    url=getpass.getpass('Supabase Session-pooler connection URI (hidden): ').strip()
    if url.startswith('postgresql://'):url=url.replace('postgresql://','postgresql+psycopg://',1)
    if not url.startswith('postgresql+psycopg://'):
        raise SystemExit('Use the full Postgres Session-pooler URI from Supabase Connect, beginning postgresql://')
    from sqlalchemy.engine import make_url
    try:
        parsed=make_url(url)
        if not (parsed.host or '').endswith('.pooler.supabase.com') or parsed.port!=5432:
            raise ValueError()
    except Exception:
        raise SystemExit('Select Session pooler in Supabase Connect: host ends .pooler.supabase.com and port is 5432. No credentials displayed.')
    if not parsed.password or 'YOUR-PASSWORD' in parsed.password.upper():
        password=getpass.getpass('Project DATABASE password (hidden; encoded automatically): ')
        if not password:raise SystemExit('Database password cannot be empty')
        parsed=parsed.set(password=password)
    parsed=parsed.update_query_dict({'sslmode':'require'})
    project=input('Supabase project URL [https://yeqkhpnjlfpjvnsygpbo.supabase.co]: ').strip() or 'https://yeqkhpnjlfpjvnsygpbo.supabase.co'
    parts=urlsplit(project)
    if parts.scheme!='https' or not (parts.hostname or '').endswith('.supabase.co') or parts.path not in {'','/'} or parts.query or parts.fragment or parts.username or parts.password:
        raise SystemExit('Enter the HTTPS project URL without backslashes, quotes, or extra paths. No credentials displayed.')
    key=getpass.getpass('Supabase server-side service_role or secret key (hidden): ').strip()
    if not key:raise SystemExit('Storage key cannot be empty')
    env={**os.environ,'FINN_DATABASE_URL':parsed.render_as_string(hide_password=False),'FINN_STORAGE_BACKEND':'supabase','FINN_STORAGE_URL':project,'FINN_STORAGE_KEY':key,'FINN_STORAGE_BUCKET':'finn-private','FINN_BOOTSTRAP_ENABLED':'false','FINN_ACCESS_MODE':'local'}
    command=[str(root/'backend/.venv/bin/python'),'-m','app.cloud_import']
    if args.check_only:command.append('--check-only')
    process=subprocess.Popen(command,cwd=root/'backend',env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    terminal_status=None
    for line in process.stdout:
        try:event=json.loads(line)
        except ValueError:continue
        # Print only known structured fields from the worker; never raw stderr or unexpected output.
        status=event.get('status');stage=event.get('stage')
        if stage in {'database','storage','upload'} and (status in {'checking','passed','running'} or isinstance(event.get('uploaded_objects'),int)):
            if 'uploaded_objects' in event:print(f"Upload: {int(event['uploaded_objects'])}/{int(event['total_objects'])} objects",flush=True)
            else:print(f"{stage.capitalize()}: {status}",flush=True)
        if status in {'ready','copied','failed'}:
            terminal_status=status
            from sys import path
            path.insert(0,str(root/'backend'))
            from app.cloud_import import MESSAGES
            if status=='failed':
                safe_code=event.get('code') if event.get('code') in MESSAGES else 'unexpected'
                print('Import stopped ['+safe_code+']: '+MESSAGES[safe_code])
            elif status=='ready':print('Checks passed. No data was uploaded or copied. Run again without --check-only to import.')
            else:print(f"Import completed: {int(event['uploaded_objects'])} objects and {int(event['copied_rows'])} rows copied. Local data unchanged.")
    code=process.wait()
    if code and terminal_status is None:raise SystemExit('Import worker exited unexpectedly; local data unchanged. No raw credentials were displayed.')
    raise SystemExit(code)

if __name__=='__main__':main()
