from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import get_settings

class Base(DeclarativeBase):
    pass

def make_engine(url: str):
    options = {'connect_args': {"check_same_thread": False, "timeout": 30}} if url.startswith('sqlite') else {
        'connect_args': {'connect_timeout': 10, 'prepare_threshold': None}, 'pool_size': 3, 'max_overflow': 2, 'pool_pre_ping': True}
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            if ":memory:" not in url and url != "sqlite://":
                connection.execute("PRAGMA journal_mode=WAL")
    return engine

engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    with SessionLocal() as session:
        yield session
