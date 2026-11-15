from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.seed import DEMO_OWNER
from app.models.entities import Contact, Company
from app.models.intelligence import NetworkProfile, Education, RelationshipEdge, CompanyPeer

def seed_network(db: Session):
    contacts = {c.name: c for c in db.scalars(select(Contact).where(Contact.owner_id == DEMO_OWNER))}
    for i, c in enumerate(contacts.values()):
        if db.get(NetworkProfile, c.id) is None:
            db.add(NetworkProfile(contact_id=c.id, aliases=[c.name.replace(' Demo ', ' ')],
                bio='Synthetic professional profile created only for this FINN demonstration. Career and education below are invented.',
                last_contact_date=date(2026, 1, min(i+1,28))))
            db.add(Education(contact_id=c.id,institution='Demo Institute of Technology' if i%2 else 'Demo School of Management',
                qualification='Synthetic engineering degree' if i%2 else 'Synthetic management degree',start_year=2009,end_year=2013))
    second_degree = {'Priya Demo Menon': 'Aarav Demo Mehta', 'Rohan Demo Kapoor': 'Mira Demo Rao', 'Sana Demo Ali': 'Dev Demo Shah'}
    for name, c in contacts.items():
        source = str(contacts[second_degree[name]].id) if name in second_degree else 'investor'
        exists = db.scalar(select(RelationshipEdge).where(RelationshipEdge.owner_id==DEMO_OWNER,RelationshipEdge.source_key==source,RelationshipEdge.target_id==c.id))
        if not exists:
            db.add(RelationshipEdge(owner_id=DEMO_OWNER,source_key=source,target_id=c.id,
                relationship='Synthetic former-colleague relationship' if source!='investor' else 'Synthetic professional acquaintance',
                strength=4 if name in second_degree else 3,provenance='Explicitly invented relationship edge; not inferred from overlapping employment or education.'))
    companies={c.ticker:c for c in db.scalars(select(Company))}
    for a,b in [('INFY','TCS'),('TCS','INFY'),('DEEPAKNTR','PIDILITIND'),('PIDILITIND','DEEPAKNTR')]:
        if not db.scalar(select(CompanyPeer).where(CompanyPeer.company_id==companies[a].id,CompanyPeer.peer_id==companies[b].id)):
            db.add(CompanyPeer(company_id=companies[a].id,peer_id=companies[b].id,
                relationship='sector_peer',provenance='Demo relevance mapping, not evidence of a supplier, customer or personal relationship.'))
    db.commit()
