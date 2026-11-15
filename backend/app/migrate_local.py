"""One-time operator migration into an EMPTY durable database. Reads secrets only from environment."""
import argparse
import hashlib
from pathlib import Path
from sqlalchemy import select, func, text
from app.core.config import get_settings
from app.db.session import Base, engine, make_engine
from app.db.initialize import initialize_database
from app.models import entities, ingestion, intelligence
from app.providers.storage import blob_store

def copy_database(source, target):
    initialize_database(target)
    counts={}
    with source.connect() as old, target.begin() as new:
        for table in Base.metadata.sorted_tables:
            if new.scalar(select(func.count()).select_from(table)):
                raise ValueError('Target must be empty. Stop the deployed API before migrating; do not overwrite a live workspace.')
        for table in Base.metadata.sorted_tables:
            rows=[dict(r) for r in old.execute(select(table)).mappings()]
            for i in range(0,len(rows),200):new.execute(table.insert(),rows[i:i+200])
            counts[table.name]=len(rows)
            if target.dialect.name=='postgresql' and 'id' in table.c and rows:
                seq=new.scalar(text("SELECT pg_get_serial_sequence(:table, 'id')"),{'table':table.name})
                if seq:new.execute(text('SELECT setval(:seq, :value, true)'),{'seq':seq,'value':max(r['id'] for r in rows)})
    return counts

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--source-blobs',type=Path,required=True)
    args=parser.parse_args()
    settings=get_settings()
    if not args.source_db.is_file() or not args.source_blobs.is_dir():parser.error('Source database and blob folder must exist')
    if engine.dialect.name!='postgresql' or settings.storage_backend!='supabase':parser.error('Configure target Postgres and private Supabase storage first')
    source=make_engine('sqlite:///'+str(args.source_db.resolve()))
    # Upload before metadata commit; interrupted upload is safe to retry by content hash.
    store=blob_store(settings.data_dir/'blobs');uploaded=0
    for file in args.source_blobs.iterdir():
        if not file.is_file() or len(file.name)!=64:continue
        content=file.read_bytes()
        if hashlib.sha256(content).hexdigest()!=file.name:raise ValueError('Source file integrity check failed')
        store.put(file.name,content);uploaded+=1
    counts=copy_database(source,engine)
    print({'status':'copied','uploaded_objects':uploaded,'copied_rows':sum(counts.values())})

if __name__=='__main__':main()
