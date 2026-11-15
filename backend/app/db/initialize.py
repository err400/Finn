from sqlalchemy import text
from app.db.session import Base

def initialize_database(engine):
    Base.metadata.create_all(engine)
    if engine.dialect.name == 'postgresql':
        with engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS research_chunks_english_fts ON research_chunks USING gin(to_tsvector('english', text))"))
            roles=set(connection.scalars(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")))
            for table in Base.metadata.sorted_tables:
                # Table names are application metadata, never request input.
                name=connection.dialect.identifier_preparer.quote(table.name)
                connection.execute(text(f'ALTER TABLE {name} ENABLE ROW LEVEL SECURITY'))
                connection.execute(text(f'REVOKE ALL ON TABLE {name} FROM PUBLIC'))
                for role in roles:
                    connection.execute(text(f'REVOKE ALL ON TABLE {name} FROM {role}'))
                if 'id' in table.c:
                    sequence=connection.scalar(text("SELECT pg_get_serial_sequence(:table, 'id')"),{'table':table.name})
                    if sequence:
                        for role in roles | {'PUBLIC'}:
                            connection.execute(text(f'REVOKE ALL ON SEQUENCE {sequence} FROM {role}'))
