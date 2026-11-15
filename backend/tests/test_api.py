import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, select, func
from app.main import app
from app.db.session import Base, get_db
from app.db.seed import seed_demo
from app.models.entities import Company, ResearchRun

def test_portfolio_and_idempotent_seed(client):
    c, factory = client
    assert c.get("/api/v1/health").json()["database"] == "ok"
    holdings = c.get("/api/v1/portfolio").json()
    assert len(holdings) == 18
    assert len({x["sector"] for x in holdings}) >= 10
    assert len(c.get("/api/v1/research/demo-companies").json()) == 4
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == 18

def test_network_filter_and_owner_isolation(client):
    from app.services.network import find_contacts
    c, factory = client
    data = c.get("/api/v1/network?ticker=INFY.NS").json()
    assert len(data["contacts"]) >= 1
    assert all(x["synthetic"] for x in data["contacts"])
    with factory() as db:
        assert find_contacts(db, "another-owner", "INFY") == []

def test_arbitrary_ticker_has_no_fabricated_analysis(client):
    c, factory = client
    response = c.post("/api/v1/research", json={"ticker": "newticker.ns", "question": "What changed?"})
    assert response.status_code == 201
    result = response.json()
    assert result["ticker"] == "NEWTICKER"
    assert result["answer"] is None and result["citations"] == []
    assert result["status"] == "insufficient_evidence"
    with factory() as db:
        assert db.get(ResearchRun, result["id"]).ticker == "NEWTICKER"

def test_validation_and_empty_feed(client):
    c, _ = client
    assert c.post("/api/v1/research", json={"ticker": "../../bad", "question": "hello"}).status_code == 422
    assert c.post("/api/v1/research", json={"ticker": "INFY", "question": "   "}).status_code == 422
    assert c.get("/api/v1/briefing").json()["status"] == "sources_not_connected"
    assert c.get("/api/v1/companies?q=Infosys").json()[0]["ticker"] == "INFY"
