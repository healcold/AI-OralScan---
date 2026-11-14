from sqlalchemy import create_engine, event, inspect
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

def initialize_schema(bind):
    # create_all adds new tables; older workspaces also need the nullable owner column.
    with bind.begin() as connection:
        if connection.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        Base.metadata.create_all(connection)
        if 'owner_id' not in {column['name'] for column in inspect(connection).get_columns('scan_sessions')}:
            connection.exec_driver_sql(
                'ALTER TABLE scan_sessions ADD COLUMN owner_id VARCHAR(36) REFERENCES accounts(account_id)')
            connection.exec_driver_sql('CREATE INDEX ix_scan_sessions_owner_id ON scan_sessions (owner_id)')


def get_db():
    with SessionLocal() as db:
        yield db


def lock_scan_write(db):
    """Serialize file mutations that accompany scan changes in SQLite."""
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
