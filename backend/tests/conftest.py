import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app, get_storage
from app.storage import PrivateStorage

@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f'sqlite:///{(tmp_path / "test.db").as_posix()}', connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _): conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    storage = PrivateStorage(tmp_path / 'private', 1024 * 1024)
    def db_override():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, storage, factory
    app.dependency_overrides.clear()
    engine.dispose()

