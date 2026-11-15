"""Page-preserving chunks and SQLite FTS5/BM25. No external embeddings needed."""
import hashlib
import re
from sqlalchemy import select, text
from app.models.ingestion import DocumentAsset, DocumentPage, RawSnapshot
from app.models.intelligence import ResearchChunk

PRIMARY_KINDS={'annual_report','earnings_transcript','quarterly_results'}
EXPANSIONS={
 'snapshot':'business segments products customers revenue operating profit financial results',
 'trajectory':'growth revenue margins EBITDA profit changes performance cash debt',
 'guidance_vs_actual':'guidance outlook expected target future growth management delivered actual performance',
}
STOP={'what','which','does','about','with','from','this','that','have','company','please','give','would','could','should','tell','their','there','based','using'}

def normalize_text(value):return re.sub(r'\s+',' ',value).strip()

def chunk_page(value,size=1200,overlap=180):
    value=normalize_text(value);start=0
    while start<len(value):
        end=min(start+size,len(value))
        if end<len(value):
            cut=value.rfind(' ',start+size//2,end)
            if cut>start:end=cut
        yield value[start:end]
        if end==len(value):break
        start=max(start+1,end-overlap)
        if start and value[start-1]!=' ':
            next_space=value.find(' ',start)
            if next_space!=-1:start=next_space+1

def index_documents(db,company_id):
    sqlite=db.bind.dialect.name=='sqlite'
    if sqlite:
        db.execute(text('CREATE VIRTUAL TABLE IF NOT EXISTS research_fts USING fts5(chunk_id UNINDEXED, document_id UNINDEXED, text, tokenize="unicode61")'))
    docs=db.scalars(select(DocumentAsset).where(DocumentAsset.company_id==company_id,DocumentAsset.kind.in_(PRIMARY_KINDS),DocumentAsset.extraction_status.in_(['extracted','partial']))).all()
    for doc in docs:
        if db.scalar(select(ResearchChunk.id).where(ResearchChunk.document_id==doc.id).limit(1)):continue
        pages=db.scalars(select(DocumentPage).where(DocumentPage.document_id==doc.id).order_by(DocumentPage.page_number)).all()
        for page in pages:
            for ordinal,content in enumerate(chunk_page(page.text)):
                if len(content)<40:continue
                row=ResearchChunk(document_id=doc.id,page_number=page.page_number,ordinal=ordinal,text=content,content_hash=hashlib.sha256(content.encode()).hexdigest())
                db.add(row);db.flush()
                if sqlite:
                    db.execute(text('INSERT INTO research_fts(chunk_id, document_id, text) VALUES (:id,:doc,:text)'),{'id':row.id,'doc':doc.id,'text':content})
    db.commit()
    return docs

def retrieve(db,company_id,question,workflow,limit=10):
    docs=index_documents(db,company_id)
    tokens=list(dict.fromkeys(w for w in re.findall(r'[a-zA-Z0-9]{3,}',question.casefold()+' '+EXPANSIONS[workflow]) if w not in STOP))[:35]
    if not tokens:return [],docs
    query=' OR '.join('"'+t+'"' for t in tokens)
    if db.bind.dialect.name=='postgresql':
        query=' | '.join(tokens)
        sql='''SELECT c.id, -ts_rank_cd(to_tsvector('english', c.text), to_tsquery('english', :query)) AS score
        FROM research_chunks c JOIN ingestion_documents d ON d.id=c.document_id
        WHERE to_tsvector('english', c.text) @@ to_tsquery('english', :query) AND d.company_id=:company
        AND d.kind IN ('annual_report','earnings_transcript','quarterly_results')
        ORDER BY score, c.id LIMIT 100'''
    else:
        sql='''SELECT c.id, bm25(research_fts) AS score FROM research_fts
        JOIN research_chunks c ON c.id=research_fts.chunk_id JOIN ingestion_documents d ON d.id=c.document_id
        WHERE research_fts MATCH :query AND d.company_id=:company
        AND d.kind IN ('annual_report','earnings_transcript','quarterly_results')
        ORDER BY score, c.id LIMIT 100'''
    rows=db.execute(text(sql),{'query':query,'company':company_id}).all()
    matches={chunk.id:(chunk,doc,source) for chunk,doc,source in db.execute(
        select(ResearchChunk,DocumentAsset,RawSnapshot)
        .join(DocumentAsset,ResearchChunk.document_id==DocumentAsset.id)
        .join(RawSnapshot,DocumentAsset.snapshot_id==RawSnapshot.id)
        .where(ResearchChunk.id.in_([row[0] for row in rows])))}
    hits=[];per_doc={};per_page={}
    for chunk_id,score in rows:
        chunk,doc,source=matches[chunk_id]
        if per_doc.get(doc.id,0)>=4 or per_page.get((doc.id,chunk.page_number),0)>=2:continue
        hits.append({'chunk_id':chunk.id,'document_id':doc.id,'kind':doc.kind,'title':doc.title,'page':chunk.page_number,'text':chunk.text,
                     'url':source.final_url+f'#page={chunk.page_number}','sha256':doc.sha256,'period_end':str(doc.period_end) if doc.period_end else None,
                     'publication_date':str(doc.published_date) if doc.published_date else None,'retrieval_score':float(-score)})
        per_doc[doc.id]=per_doc.get(doc.id,0)+1;per_page[(doc.id,chunk.page_number)]=per_page.get((doc.id,chunk.page_number),0)+1
        if len(hits)>=limit:break
    return hits,docs
