import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, select, func
from app.main import app
from app.db.session import Base, get_db
from app.db.seed import seed_demo
from app.db.network_seed import seed_network
from app.models.entities import Company, ResearchRun

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        seed_demo(db)
        seed_demo(db)
        seed_network(db)
        seed_network(db)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    # Avoid production lifespan; test data is initialized above.
    c = TestClient(app, raise_server_exceptions=True, client=("127.0.0.1", 50000))
    try:
        yield c, factory
    finally:
        c.close()
        app.dependency_overrides.clear()
        engine.dispose()
