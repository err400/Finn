"""Explainable, owner-scoped graph recommendations over explicitly synthetic data."""
import re
from collections import deque,defaultdict
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Company, Contact, Employment
from app.models.intelligence import NetworkProfile, Education, RelationshipEdge, CompanyPeer
from app.services.normalization import normalize_name

TOPICS = {'results':['finance','results','planning'], 'M&A':['strategy','acquisition','capex'],
          'capex':['capex','project','operations'], 'litigation':['compliance','litigation'],
          'management_change':['leadership','operations'], 'press_release':['strategy','operating agreements','upstream']}

def person_key(value):
    return re.sub(r'[^a-z0-9]','',re.sub(r'\b(mr|mrs|ms|dr)\.?(?:\s+|$)','',value.casefold()))

class NetworkIntelligence:
    def __init__(self, db: Session, owner_id: str, *, preload=False):
        self.db,self.owner_id=db,owner_id
        self.preloaded=preload
        if preload:
            self._people=db.scalars(select(Contact).where(Contact.owner_id==owner_id,Contact.synthetic.is_(True))).all()
            ids=[p.id for p in self._people]
            self._companies=db.scalars(select(Company)).all()
            self._edges=db.scalars(select(RelationshipEdge).where(RelationshipEdge.owner_id==owner_id)).all()
            self._roles=defaultdict(list)
            for e,c in db.execute(select(Employment,Company).join(Company,Company.id==Employment.company_id).where(Employment.contact_id.in_(ids))):self._roles[e.contact_id].append((e,c))
            self._education=defaultdict(list)
            for e in db.scalars(select(Education).where(Education.contact_id.in_(ids))):self._education[e.contact_id].append(e)
            self._profiles={p.contact_id:p for p in db.scalars(select(NetworkProfile).where(NetworkProfile.contact_id.in_(ids)))}
            self._peers=defaultdict(dict)
            for p in db.scalars(select(CompanyPeer)):self._peers[p.company_id][p.peer_id]=p
            self._paths=None

    def people(self):
        if self.preloaded:return self._people
        return self.db.scalars(select(Contact).where(Contact.owner_id==self.owner_id,Contact.synthetic.is_(True))).all()

    def resolve_company(self, value):
        key=normalize_name(value.strip().upper().removeprefix('NSE:').removesuffix('.NS'))
        matches=[c for c in (self._companies if self.preloaded else self.db.scalars(select(Company))) if key in {normalize_name(c.name),normalize_name(c.ticker)}]
        if len(matches)!=1:raise ValueError('Company name is unavailable or ambiguous; enter an exact registered NSE ticker')
        return matches[0]

    def paths(self):
        if self.preloaded and self._paths is not None:return self._paths
        people={p.id:p for p in self.people()}
        adjacency={}
        for e in (self._edges if self.preloaded else self.db.scalars(select(RelationshipEdge).where(RelationshipEdge.owner_id==self.owner_id))):
            if e.target_id not in people or (e.source_key!='investor' and e.source_key not in {str(i) for i in people}):continue
            adjacency.setdefault(e.source_key,[]).append(e)
        found={};queue=deque([('investor',[])])
        while queue:
            source,path=queue.popleft()
            if len(path)>=2:continue
            for edge in adjacency.get(source,[]):
                if edge.target_id in found:continue
                route=path+[edge];found[edge.target_id]=route;queue.append((str(edge.target_id),route))
        if self.preloaded:self._paths=found
        return found

    def profile(self,contact_id):
        contact=next((p for p in self.people() if p.id==contact_id),None)
        if not contact:return None
        extra=self._profiles.get(contact.id) if self.preloaded else self.db.get(NetworkProfile,contact.id)
        roles=self._roles[contact.id] if self.preloaded else self.db.execute(select(Employment,Company).join(Company,Employment.company_id==Company.id).where(Employment.contact_id==contact.id)).all()
        education=self._education[contact.id] if self.preloaded else self.db.scalars(select(Education).where(Education.contact_id==contact.id)).all()
        route=self.paths().get(contact.id,[])
        return {'id':contact.id,'name':contact.name,'expertise':contact.expertise,'synthetic':True,'provenance':contact.provenance,
                'bio':extra.bio if extra else None,'aliases':extra.aliases if extra else [],'last_contact_date':str(extra.last_contact_date) if extra and extra.last_contact_date else None,
                'roles':[{'ticker':c.ticker,'company':c.name,'role':e.role,'start_year':e.start_year,'end_year':e.end_year,'synthetic':True} for e,c in roles],
                'education':[{'institution':e.institution,'qualification':e.qualification,'start_year':e.start_year,'end_year':e.end_year,'synthetic':True} for e in education],
                'degree':len(route) if route else None,
                'connection_path':[{'from':self.db.get(Contact,int(e.source_key)).name if e.source_key!='investor' else 'Demo investor','to':self.db.get(Contact,e.target_id).name,
                                    'relationship':e.relationship,'strength':e.strength,'provenance':e.provenance,'synthetic':True} for e in route]}

    def match_person(self,name):
        key=person_key(name)
        matches=[]
        for p in self.people():
            extra=self.db.get(NetworkProfile,p.id)
            if key in {person_key(x) for x in [p.name]+(extra.aliases if extra else [])}:matches.append(self.profile(p.id))
        return {'query':name,'synthetic':True,'matches':matches,'ambiguous':len(matches)>1,
                'message':'Exact normalized names/aliases only. No connection to an identifiable real person is inferred.'}

    def recommend(self,company_value,*,category=None,event_title='',limit=3):
        company=self.resolve_company(company_value)
        peers=self._peers[company.id] if self.preloaded else {p.peer_id:p for p in self.db.scalars(select(CompanyPeer).where(CompanyPeer.company_id==company.id))}
        paths=self.paths();recommendations=[]
        tokens=set(re.findall(r'[a-z]{3,}',(event_title+' '+company.sector).casefold()))
        if 'joint operating' in event_title.casefold():tokens.update(['upstream','operating agreements','energy'])
        tokens.update(TOPICS.get(category,[]))
        for p in self.people():
            route=paths.get(p.id)
            if not route:continue
            roles=self._roles[p.id] if self.preloaded else self.db.execute(select(Employment,Company).join(Company,Company.id==Employment.company_id).where(Employment.contact_id==p.id)).all()
            direct=[(e,c) for e,c in roles if c.id==company.id]
            peer=[(e,c) for e,c in roles if c.id in peers]
            reasons=[];components={}
            if direct:
                e,c=direct[0];components['company_experience']=65
                reasons.append(f'{e.role} at {c.name}, {e.start_year}–{e.end_year or "present"} (synthetic history).')
            elif peer:
                e,c=peer[0];components['peer_experience']=40
                reasons.append(f'{e.role} at {c.name}, a demo sector peer of {company.name}; not evidence of a commercial relationship.')
            sector_match=any(normalize_name(company.sector)==normalize_name(t) for t in p.expertise)
            if sector_match:components['sector_expertise']=10;reasons.append(f'Profile lists {company.sector} experience.')
            matched=[t for t in p.expertise if t.casefold() in tokens or any(w in tokens for w in t.casefold().split())]
            if matched:components['topic_fit']=min(18,6*len(matched));reasons.append('Relevant declared themes: '+', '.join(matched)+'.')
            if not any(k in components for k in ['company_experience','peer_experience','sector_expertise']):continue
            components['reachability']=10 if len(route)==1 else 3
            components['relationship_strength']=min(e.strength for e in route)*2
            if len(route)==2:
                intermediary=self.db.get(Contact,route[0].target_id)
                reasons.append(f'Second-degree route through {intermediary.name}; this introduction edge is explicitly synthetic.')
            else:reasons.append('Direct synthetic professional acquaintance of the demo investor.')
            profile=self.profile(p.id)
            profile.update(score=min(100,sum(components.values())),score_components=components,reasons=reasons,
                reason=' '.join(reasons),company=company.name,ticker=company.ticker,role=(direct or peer or roles)[0][0].role,
                suggested_question=self.question(category,event_title),
                limitations='Synthetic experience suggests a possible source of public context; it does not establish current company knowledge, personal access to management, or inside information.')
            recommendations.append(profile)
        recommendations.sort(key=lambda r:(-r['score'],r['degree'],r['name']))
        return {'company':company.name,'ticker':company.ticker,'synthetic':True,'ranking_method':'Deterministic additive relevance score, not a probability or endorsement.',
                'recommendations':recommendations[:limit],'limitations':'No scraping or real-person enrichment. Shared employers/education never create relationship edges.'}

    @staticmethod
    def question(category,title):
        if 'joint operating' in title.casefold():return 'From public information, what questions would you ask about operating responsibilities, conditions and capital commitments in this agreement?'
        return {'results':'Which operating drivers would you check against the published results?',
                'M&A':'Which integration risks and transaction conditions would you investigate in the public filing?',
                'capex':'Which execution milestones and funding assumptions deserve a closer look?',
                'litigation':'What public process milestones and disclosed contingencies should we track?',
                'management_change':'What public experience is relevant to the incoming role, and which questions should we ask?'}.get(category,'What industry context would help us interpret this public disclosure?')

def find_contacts(db: Session,owner_id: str,ticker: str | None):
    service=NetworkIntelligence(db,owner_id)
    if ticker:
        try:return service.recommend(ticker)['recommendations']
        except ValueError:return []
    result=[]
    for p in service.people():
        profile=service.profile(p.id)
        if profile['roles']:
            role=profile['roles'][0];profile.update(ticker=role['ticker'],company=role['company'],role=role['role'],reason=f"{role['role']} at {role['company']} ({role['start_year']}–{role['end_year'] or 'present'}). Synthetic history and connections.")
        result.append(profile)
    return result
