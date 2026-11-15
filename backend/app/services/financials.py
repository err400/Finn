"""Conservative layout-constrained extraction and Decimal comparisons.
Only a recognizable consolidated INR-crore table with explicit quarter headers and
six numeric columns is accepted. Unsupported layouts yield no calculated facts.
"""
import calendar
import re
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.models.ingestion import DocumentAsset, DocumentPage, RawSnapshot

METRICS={'Gross Revenue':'gross_revenue','Revenue from operations':'revenue_from_operations','Total Income':'total_income',
         'EBITDA':'ebitda','Profit Before Tax':'pbt','Profit After Tax':'pat'}

def change(current,previous):
    current,previous=Decimal(str(current)),Decimal(str(previous))
    if not current.is_finite() or not previous.is_finite() or previous<=0:return None
    return format(((current/previous-1)*100).quantize(Decimal('0.01')),'f')

def quarter_end(q,year):
    year=int(year);year=2000+year if year<100 else year
    month={1:6,2:9,3:12,4:3}[int(q)];year=year if int(q)==4 else year-1
    return date(year,month,calendar.monthrange(year,month)[1])

def extract_table(text):
    if not re.search(r'consolidated financial highlights',text,re.I) or not re.search(r'₹\s+in\s+crore',text,re.I):return []
    headers=re.findall(r'([1-4])Q\s*FY(\d{2,4})\b',text,re.I)
    if len(headers)!=3 or len(set(headers))!=3:return []
    periods=[quarter_end(q,y) for q,y in headers]
    if periods[0]<=periods[1] or periods[0]<=periods[2]:return []
    facts=[]
    for line in text.splitlines():
        match=re.fullmatch(r'\s*\d+\s+('+ '|'.join(re.escape(m) for m in METRICS)+r')\s+(.+?)\s*',line,re.I)
        if not match:continue
        label=next(m for m in METRICS if m.casefold()==match[1].casefold())
        values=match[2].split()
        if len(values)!=6 or not all(re.fullmatch(r'-?\d[\d,]*(?:\.\d+)?',v) for v in values):continue
        nums=[Decimal(v.replace(',','')) for v in values[:3]]
        for period,value in zip(periods,nums):
            facts.append({'metric':METRICS[label],'source_label':label,'value':format(value,'f'),'period_end':period.isoformat(),
                          'currency':'INR','unit':'crore','basis':'consolidated','evidence_quote':line.strip()})
    return facts

def financial_comparisons(db,company_id):
    facts=[]
    for doc,page,source in db.execute(select(DocumentAsset,DocumentPage,RawSnapshot).join(DocumentPage,DocumentPage.document_id==DocumentAsset.id).join(RawSnapshot,DocumentAsset.snapshot_id==RawSnapshot.id).where(DocumentAsset.company_id==company_id,DocumentAsset.kind=='quarterly_results')):
        for fact in extract_table(page.text):
            fact['citation']={'document_id':doc.id,'page':page.page_number,'url':source.final_url+f'#page={page.page_number}',
                              'sha256':doc.sha256,'quote':fact['evidence_quote']}
            facts.append(fact)
    # Never compare conflicting values from different reports silently.
    grouped={}
    for fact in facts:grouped.setdefault((fact['metric'],fact['period_end']),[]).append(fact)
    clean={key:rows[0] for key,rows in grouped.items() if len({r['value'] for r in rows})==1}
    comparisons=[]
    for metric in sorted({k[0] for k in clean}):
        newest=max(p for m,p in grouped if m==metric)
        if (metric,newest) not in clean:
            # A conflicting newest value cannot silently turn an older quarter into "current".
            continue
        rows=sorted([f for (m,_),f in clean.items() if m==metric],key=lambda f:f['period_end'],reverse=True)
        current=rows[0];day=date.fromisoformat(current['period_end'])
        item={**current,'qoq':None,'yoy':None}
        for past in rows[1:]:
            old=date.fromisoformat(past['period_end']);months=(day.year-old.year)*12+day.month-old.month
            relation='qoq' if months==3 else 'yoy' if months==12 and day.month==old.month else None
            if relation:
                item[relation]={'previous_value':past['value'],'previous_period_end':past['period_end'],'change_percent':change(current['value'],past['value']),
                                'formula':'(current / previous - 1) * 100','citation':past['citation']}
        comparisons.append(item)
    return {'metrics':comparisons,'method':'Conservative explicit quarter-header/table extraction; Decimal arithmetic. No values are supplied by an LLM.',
            'limitation':'Only recognized consolidated INR-crore quarterly tables are supported. Gross revenue and revenue from operations remain distinct; PAT is not automatically equated with profit including associates/JVs.',
            'conflicting_periods':[{'metric':m,'period_end':p} for (m,p),rows in grouped.items() if len({r['value'] for r in rows})>1]}
