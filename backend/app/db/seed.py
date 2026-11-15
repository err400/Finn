import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Company, PortfolioHolding, Contact, Employment

DEMO_OWNER = "synthetic-demo"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

def seed_demo(db: Session):
    for row in json.loads((FIXTURES / "companies.json").read_text()):
        company = db.scalar(select(Company).where(Company.ticker == row["ticker"]))
        if company is None:
            company = Company(**row)
            db.add(company)
            db.flush()
        if db.scalar(select(PortfolioHolding).where(PortfolioHolding.owner_id == DEMO_OWNER, PortfolioHolding.company_id == company.id)) is None:
            db.add(PortfolioHolding(owner_id=DEMO_OWNER, company_id=company.id))
    for row in json.loads((FIXTURES / "network.json").read_text()):
        if db.scalar(select(Contact).where(Contact.owner_id == DEMO_OWNER, Contact.name == row["name"])):
            continue
        company = db.scalar(select(Company).where(Company.ticker == row["ticker"]))
        contact = Contact(owner_id=DEMO_OWNER, **{k: row[k] for k in ["name", "expertise", "synthetic", "provenance"]})
        db.add(contact)
        db.flush()
        db.add(Employment(contact_id=contact.id, company_id=company.id, **{k: row[k] for k in ["role", "start_year", "end_year"]}))
    db.commit()
