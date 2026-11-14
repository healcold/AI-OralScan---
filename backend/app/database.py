from contextlib import closing

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

def make_engine(url: str, *, busy_timeout_seconds: float | None = None):
    parsed = make_url(url)
    sqlite = parsed.get_backend_name() == 'sqlite'
    timeout = get_settings().sqlite_busy_timeout_seconds if busy_timeout_seconds is None else busy_timeout_seconds
    engine = create_engine(
        url, hide_parameters=True, pool_pre_ping=True,
        connect_args={'check_same_thread': False, 'timeout': timeout} if sqlite else {},
    )
    if sqlite:
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(connection, _record):
            with closing(connection.cursor()) as cursor:
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.execute(f'PRAGMA busy_timeout={int(timeout * 1000)}')
                if parsed.database not in (None, '', ':memory:') and parsed.query.get('mode') != 'memory':
                    cursor.execute('PRAGMA journal_mode=WAL')
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
