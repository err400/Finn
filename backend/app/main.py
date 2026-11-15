from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.db.session import Base, engine, SessionLocal
from app.db.seed import seed_demo
from app.api.router import router
from app.api.portfolio_overview import router as portfolio_router
from app.api.intelligence import router as intelligence_router
from app.api.ingestion import router as ingestion_router
from app.models import ingestion, intelligence
from app.db.network_seed import seed_network
from app.models import entities  # register all models before create_all

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.initialize import initialize_database
    initialize_database(engine)
    with SessionLocal() as db:
        seed_demo(db)
        seed_network(db)
    async def evaluate_stored_data():
        from app.watch import tick
        while True:
            try:
                await asyncio.to_thread(tick, False)
            except Exception as exc:
                if getattr(exc, "code", "") == "busy":
                    logging.getLogger(__name__).info("Stored-data alert evaluation deferred while ingestion is active")
                else:
                    logging.getLogger(__name__).exception("Stored-data alert evaluation deferred")
            await asyncio.sleep(60)
    async def refresh_sources():
        from app.services.source_refresh import source_refresh
        while True:
            try:
                await source_refresh.request(automatic=True)
            except Exception:
                logging.getLogger(__name__).exception("Scheduled source refresh deferred")
            await asyncio.sleep(get_settings().source_refresh_seconds)
    task = asyncio.create_task(evaluate_stored_data())
    from app.services.bootstrap import start_bootstrap
    bootstrap_task = asyncio.create_task(start_bootstrap()) if get_settings().bootstrap_enabled else None
    source_task = asyncio.create_task(refresh_sources()) if get_settings().auto_refresh_enabled else None
    try:
        yield
    finally:
        if bootstrap_task:
            bootstrap_task.cancel()
            try:await bootstrap_task
            except asyncio.CancelledError:pass
        if source_task:
            source_task.cancel()
            try:await source_task
            except asyncio.CancelledError:pass
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="FINN", version="0.1.0", lifespan=lifespan,
              description="FINN prototype: primary financial evidence, synthetic network, deterministic PUSH and grounded PULL. Single reviewer gate; production identity is not implemented.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization", "X-FINN-Ingest-Token"])

@app.middleware('http')
async def response_security(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response
app.include_router(router)
app.include_router(portfolio_router)
app.include_router(ingestion_router)
app.include_router(intelligence_router)
