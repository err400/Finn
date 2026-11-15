"""Single-process source coordinator. Shared tasks, persisted HTTP cooldowns,
non-blocking API reads and no LLM calls. Production would use a durable worker."""
import asyncio
from datetime import datetime,timezone
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.ingestion import FetchCache
from app.services.normalization import utc
from app.providers.exchange_rss import FEEDS

class SourceRefreshManager:
    def __init__(self,worker=None):
        self.task=None
        self.worker=worker
        self.state={'status':'idle','started_at':None,'completed_at':None,'message':'No refresh requested in this process.'}
    def status(self):return dict(self.state)
    def recent_check(self):
        with SessionLocal() as db:
            entries=db.scalars(select(FetchCache).where(FetchCache.url.in_(FEEDS.values()))).all()
            if len(entries)!=len(FEEDS):return False
            now=datetime.now(timezone.utc)
            return all(c.last_attempt_at and (now-utc(c.last_attempt_at)).total_seconds()<300 for c in entries)
    async def request(self,*,automatic=False):
        if self.task and not self.task.done():return self.status()
        if self.recent_check():
            self.state.update(status='recently_checked',message='Exchange feeds were checked within the last five minutes. Cached source records are being reused; any source errors remain visible.')
            return self.status()
        self.state={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'completed_at':None,'message':'Checking published exchange sources in the background.'}
        self.task=asyncio.create_task(self._run(automatic))
        return self.status()
    async def _run(self,automatic):
        try:
            if self.worker:result=await self.worker(automatic)
            else:
                from app.watch import tick
                for attempt in range(3):
                    try:
                        result=await asyncio.to_thread(tick,True,('filings','prices') if automatic else ('filings',),True)
                        break
                    except Exception as exc:
                        if getattr(exc,'code','')!='busy' or attempt==2:raise
                        await asyncio.sleep(1)
            runs=result.get('runs',[])
            bad=[r for r in runs if r['status'] in {'failed','partial','stale'}]
            self.state.update(status='partial' if bad else 'success',message='Some sources could not be refreshed; previously verified data is retained.' if bad else 'Published sources checked. Stored records and alert evaluations are updated.',
                failed_runs=len(bad),refreshed_runs=len(runs))
        except Exception as exc:
            if getattr(exc,'code','')=='busy':
                self.state.update(status='deferred',message='Another ingestion job is active. Existing verified data remains available; refresh will retry on the next cycle.')
            else:
                self.state.update(status='failed',message='Source update could not finish. Stored evidence is retained; retry later.')
        finally:self.state['completed_at']=datetime.now(timezone.utc).isoformat()

source_refresh=SourceRefreshManager()
