"""Safe operator import diagnostics. No raw exceptions, URLs, or credentials on stdout."""
import argparse
import json
import time
from pathlib import Path

MESSAGES = {
    'configuration': 'Check the project URL and private storage configuration.',
    'database_auth': 'Database login rejected. Use the Session-pooler URI and the project database password, not your Supabase account password.',
    'database_tenant': 'Pooler username/project was not recognized. Copy the Session-pooler URI directly from this project; keep its complete username.',
    'database_network': 'Database host could not be reached. Check the Session-pooler host, port 5432, network/VPN, and whether the project is paused.',
    'database_tls': 'Database TLS connection failed. Use sslmode=require and check your network certificates.',
    'database_unavailable': 'Database connection failed. Check the Session-pooler details and project status.',
    'target_not_empty': 'Destination already contains FINN records. Nothing was overwritten. Do not delete them; use a reviewed migration or the existing workspace.',
    'storage_auth': 'Storage access rejected. Use the server-side service_role or secret key from this same Supabase project, not the anon/publishable key.',
    'bucket_missing': 'The finn-private bucket was not found. Create it in this Supabase project before importing.',
    'bucket_public': 'The finn-private bucket is public. Turn Public bucket OFF before importing.',
    'storage_network': 'Private Storage could not be reached. Check the project URL, project status, and network.',
    'storage_unavailable': 'Private Storage request failed. Check the bucket and project configuration.',
    'source_integrity': 'A local source file failed integrity verification. No database copy was committed.',
    'schema_failed': 'Destination schema initialization failed. Check database-role permissions. No financial records were copied.',
    'upload_failed': 'A source-file upload failed. Earlier uploaded objects may remain; retry is safe by content hash. No database copy was committed.',
    'copy_failed': 'Database copy failed and its record transaction was rolled back. Uploaded source objects may remain. Local data is unchanged.',
    'source_missing': 'Local finn.db or data/blobs is missing. Run from the existing FINN project with its verified local data.',
    'unexpected': 'The import worker could not complete. Local data is unchanged; no raw credential-bearing exception is displayed.',
}

class ImportFailure(Exception):
    def __init__(self, code): self.code=code

def emit(**values): print(json.dumps(values), flush=True)

def database_error_code(exc):
    original=getattr(exc, 'orig', exc)
    state=getattr(original, 'sqlstate', None)
    # Match known diagnostics internally; never return the raw driver message.
    message=str(original).casefold()
    if 'tenant or user not found' in message:return 'database_tenant'
    if state in {'28P01','28000'} or 'password authentication failed' in message:return 'database_auth'
    if 'certificate' in message or 'ssl error' in message:return 'database_tls'
    if any(t in message for t in ['timeout','timed out','could not translate host','name or service not known','nodename nor servname','connection refused','network is unreachable']):return 'database_network'
    return 'database_unavailable'

def check_target_empty(target):
    from sqlalchemy import inspect, select, func
    from app.db.session import Base
    existing=set(inspect(target).get_table_names())
    with target.connect() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name in existing and connection.scalar(select(func.count()).select_from(table)):
                raise ImportFailure('target_not_empty')

def check_private_bucket(settings, client):
    import httpx
    key=settings.storage_key.get_secret_value()
    headers={'apikey':key}
    if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
    for attempt in range(3):
        try:
            response=client.get(settings.storage_url.rstrip('/')+'/storage/v1/bucket/'+settings.storage_bucket,headers=headers)
            break
        except httpx.HTTPError as exc:
            if attempt==2:raise ImportFailure('storage_network') from exc
            time.sleep(1)
    if response.status_code in {401,403}:raise ImportFailure('storage_auth')
    if response.status_code==404:raise ImportFailure('bucket_missing')
    if response.status_code!=200:raise ImportFailure('storage_unavailable')
    try:data=response.json()
    except ValueError as exc:raise ImportFailure('storage_unavailable') from exc
    if data.get('public') is not False:raise ImportFailure('bucket_public')

def run_import(source_db,source_blobs,check_only=False):
    import hashlib
    import httpx
    from sqlalchemy import text
    try:
        from app.core.config import get_settings
        settings=get_settings()
        from app.db.session import engine,make_engine
        from app.models import entities,ingestion,intelligence
        from app.migrate_local import copy_database
        from app.providers.storage import SupabaseBlobStore
    except Exception as exc:raise ImportFailure('configuration') from exc
    if not source_db.is_file() or not source_blobs.is_dir():raise ImportFailure('source_missing')
    if engine.dialect.name!='postgresql' or settings.storage_backend!='supabase':raise ImportFailure('configuration')
    emit(stage='database',status='checking')
    try:
        with engine.connect() as connection:connection.execute(text('SELECT 1'))
        check_target_empty(engine)
    except ImportFailure:raise
    except Exception as exc:raise ImportFailure(database_error_code(exc)) from exc
    emit(stage='database',status='passed')
    with httpx.Client(timeout=httpx.Timeout(45,connect=10),follow_redirects=False) as client:
        emit(stage='storage',status='checking')
        check_private_bucket(settings,client)
        emit(stage='storage',status='passed')
        if check_only:
            emit(status='ready',message='Database connection, empty destination, and private bucket checks passed. No data was uploaded or copied.')
            return
        # Verify all local bytes before the first upload.
        files=[p for p in source_blobs.iterdir() if p.is_file() and len(p.name)==64]
        for file in files:
            if hashlib.sha256(file.read_bytes()).hexdigest()!=file.name:raise ImportFailure('source_integrity')
        # Harden/create tables before placing source objects in the private bucket.
        try:
            from app.db.initialize import initialize_database
            initialize_database(engine)
        except Exception as exc:raise ImportFailure('schema_failed') from exc
        store=SupabaseBlobStore(settings,client);uploaded=0
        emit(stage='upload',status='running',total_objects=len(files))
        for file in files:
            try:store.put(file.name,file.read_bytes())
            except Exception as exc:raise ImportFailure('upload_failed') from exc
            uploaded+=1
            if uploaded%10==0:emit(stage='upload',uploaded_objects=uploaded,total_objects=len(files))
        source=make_engine('sqlite:///'+str(source_db.resolve()))
        try:counts=copy_database(source,engine)
        except Exception as exc:raise ImportFailure('copy_failed') from exc
        finally:source.dispose()
    emit(status='copied',uploaded_objects=uploaded,copied_rows=sum(counts.values()),message='Import completed. Local source data is unchanged.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    try:run_import(Path('finn.db'),Path('data/blobs'),args.check_only)
    except ImportFailure as exc:
        emit(status='failed',code=exc.code,message=MESSAGES[exc.code]);return 1
    except Exception:
        emit(status='failed',code='unexpected',message=MESSAGES['unexpected']);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
