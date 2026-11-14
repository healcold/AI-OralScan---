from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

def make_engine(url: str):
    engine = create_engine(url, hide_parameters=True, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(connection, _record):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine

engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        yield db


def lock_scan_write(db):
    """Serialize file mutations that accompany scan changes in SQLite."""
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
