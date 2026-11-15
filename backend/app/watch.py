"""Local monitor: python -m app.watch --once --refresh. Omit --once to keep watching.
Only the explicit --refresh flag performs external source requests; no OS jobs installed.
"""
import argparse,json,time
from datetime import datetime,timedelta
from pathlib import Path
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import Base,engine,SessionLocal
from app.db.seed import seed_demo,DEMO_OWNER
from app.db.network_seed import seed_network
from app.models import intelligence,ingestion,entities
from app.models.entities import Company,PortfolioHolding
from app.models.ingestion import IngestionRun
from app.services.normalization import utc
from app.services.ingestion import IngestionService,refresh_lock
from app.services.push import PushService
from app.services.normalization import IST
from app.providers.contracts import ProviderError
from app.api.ingestion import run_out

def tick(refresh=False,datasets=('prices','filings'),force_filings=False):
    settings=get_settings();today=datetime.now(IST).date();runs=[]
    with refresh_lock(settings.data_dir),SessionLocal() as db:
        svc=IngestionService(db,settings.data_dir)
        if refresh:
            companies=db.scalars(select(Company).join(PortfolioHolding).where(PortfolioHolding.owner_id==DEMO_OWNER)).all()
            for dataset in datasets:
                for company in companies:
                    if dataset=='prices':
                        last=db.scalar(select(IngestionRun).where(IngestionRun.ticker==company.ticker,IngestionRun.dataset=='prices',IngestionRun.status=='success').order_by(IngestionRun.id.desc()).limit(1))
                        if last and last.completed_at and (datetime.now(IST)-utc(last.completed_at)).total_seconds()<21600 and last.details.get('end_exclusive')==today.isoformat():
                            continue
                    runs.append(run_out(svc.refresh(company.ticker,dataset,'live',today-timedelta(days=120),today,force_filings and dataset=='filings' and company.id==companies[0].id)))
        evaluation=PushService(db).evaluate(today,'live')
        previous=PushService(db).evaluate(today-timedelta(days=1),'live')
    return {'checked_at':datetime.now(IST).isoformat(),'source_refresh_requested':refresh,'runs':runs,'evaluation':evaluation,'previous_day_evaluation':previous}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--once',action='store_true');p.add_argument('--refresh',action='store_true');p.add_argument('--interval',type=int,default=900);p.add_argument('--report',type=Path);args=p.parse_args()
    if args.interval<900:p.error('Source watcher interval must be at least 900 seconds')
    Base.metadata.create_all(engine)
    with SessionLocal() as db:seed_demo(db);seed_network(db)
    while True:
        try:result=tick(args.refresh)
        except ProviderError as exc:result={'status':'deferred','code':exc.code,'message':str(exc)}
        print(json.dumps(result,default=str),flush=True)
        if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,default=str,indent=2)+'\n')
        if args.once:break
        time.sleep(args.interval)
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
