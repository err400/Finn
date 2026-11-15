"""Local operator CLI: python -m app.ingest --help. No AI/model calls."""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import Base, engine, SessionLocal
from app.db.seed import seed_demo, DEMO_OWNER
from app.models import entities, ingestion, intelligence
from app.db.network_seed import seed_network
from app.models.entities import Company, PortfolioHolding
from app.models.ingestion import FetchCache
from app.providers.http import CachedHttpFetcher, validate_source_url
from app.providers.contracts import ProviderError
from app.services.ingestion import IngestionService, refresh_lock
from app.services.normalization import IST
from app.api.ingestion import run_out

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    refresh = commands.add_parser('refresh')
    scope = refresh.add_mutually_exclusive_group(required=True)
    scope.add_argument('--ticker', action='append', help='Repeat for several symbols; accepts NSE:INFY or INFY.NS')
    scope.add_argument('--portfolio', action='store_true')
    refresh.add_argument('--dataset', choices=['prices','filings','documents'], required=True)
    refresh.add_argument('--mode', choices=['live','replay'], default='live')
    refresh.add_argument('--start', type=date.fromisoformat, default=datetime.now(IST).date()-timedelta(days=90))
    refresh.add_argument('--end', type=date.fromisoformat, default=datetime.now(IST).date(), help='Exclusive end date; today is always excluded')
    refresh.add_argument('--force', action='store_true', help='Revalidate cache; still obey rate/cooldown limits')
    refresh.add_argument('--report', type=Path)
    capture = commands.add_parser('import-probes', help='Import only real successful captures from the source-accessibility probes')
    capture.add_argument('folder', type=Path)
    args = parser.parse_args()
    if args.command == 'refresh':
        if args.start >= args.end or (args.end-args.start).days > 3660 or args.end > datetime.now(IST).date():
            parser.error('Invalid date window (positive, at most ten years, no future end date)')
        if args.mode == 'replay' and args.dataset != 'filings': parser.error('Replay is only for filings')
    settings = get_settings()
    from app.db.initialize import initialize_database
    initialize_database(engine)
    with refresh_lock(settings.data_dir), SessionLocal() as db:
        seed_demo(db)
        seed_network(db)
        if args.command == 'import-probes':
            records=[]
            for p in sorted(args.folder.glob('*.json')):
                data=json.loads(p.read_text())
                records.extend(data if isinstance(data,list) else [data])
            http = CachedHttpFetcher(db, settings.data_dir)
            count=0
            for row in records:
                if row.get('status') != 200 or not row.get('local_file'): continue
                try:
                    url=validate_source_url(row['requested_url'])
                    final=validate_source_url(row['final_url'])
                except ProviderError: continue
                local = Path(__file__).resolve().parents[2] / row['local_file']
                content=local.read_bytes()
                # The filesystem mtime is when the original probe actually saved the received bytes.
                fetched=datetime.fromisoformat(row['completed_at']) if row.get('completed_at') else datetime.fromtimestamp(local.stat().st_mtime,timezone.utc)
                snapshot=http.capture(url,final,content,{'content-type':row.get('content_type') or 'application/octet-stream'},fetched)
                ttl=900 if url.endswith('.xml') else 7*86400 if content.startswith(b'%PDF') else 6*3600
                cache=db.get(FetchCache,url)
                if cache is None: cache=FetchCache(url=url);db.add(cache)
                cache.snapshot_id=snapshot.id;cache.last_checked_at=fetched;cache.expires_at=fetched+timedelta(seconds=ttl)
                count+=1
            db.commit();print(json.dumps({'imported_actual_captures':count}));return
        symbols = db.scalars(select(Company.ticker).join(PortfolioHolding).where(PortfolioHolding.owner_id==DEMO_OWNER).order_by(Company.ticker)).all() if args.portfolio else args.ticker
        svc=IngestionService(db,settings.data_dir)
        report=[]
        for ticker in symbols:
            try: result=run_out(svc.refresh(ticker,args.dataset,args.mode,args.start,args.end,args.force))
            except (ValueError,ProviderError) as exc: result={'ticker':ticker,'status':'failed','message':str(exc)}
            report.append(result)
            print(json.dumps(result,default=str),flush=True)
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,default=str,indent=2)+'\n')
        if any(r['status']=='failed' for r in report): raise SystemExit(1)

if __name__ == '__main__':
    try: main()
    except ProviderError as exc:
        print(json.dumps({'status': 'failed', 'error_code': exc.code, 'message': str(exc)}))
        raise SystemExit(1)
