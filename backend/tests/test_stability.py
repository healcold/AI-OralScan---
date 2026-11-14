from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import sqlite3

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import make_engine, get_db
from app.main import app
from test_api import create, upload


def test_upload_does_not_block_health_or_hold_database_connection(setup, monkeypatch):
    client, storage, factory = setup
    scan = create(client)
    entered, release = Event(), Event()
    original = storage.store_image

    def slow(*args):
        assert factory.kw['bind'].pool.checkedout() == 0
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(storage, 'store_image', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(upload, client, scan)
        try:
            assert entered.wait(5)
            assert pool.submit(client.get, '/api/health').result(timeout=2).status_code == 200
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 201


def test_concurrent_uploads_preserve_all_source_types(setup, monkeypatch):
    client, storage, _ = setup
    scan = create(client)
    ready = Barrier(2)
    original = storage.store_image

    def synchronized(*args):
        result = original(*args)
        ready.wait(timeout=5)
        return result

    monkeypatch.setattr(storage, 'store_image', synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(upload, client, scan, source) for source in ('upload', 'camera')]
        assert [future.result(timeout=10).status_code for future in pending] == [201, 201]
    assert set(client.get(f'/api/scans/{scan}').json()['source_types']) == {'upload', 'camera'}


def test_scan_deleted_during_upload_does_not_leave_asset(setup, monkeypatch):
    client, storage, _ = setup
    scan = create(client)
    original = storage.store_image

    def delete_during_upload(*args):
        assert client.delete(f'/api/scans/{scan}').status_code == 204
        return original(*args)

    monkeypatch.setattr(storage, 'store_image', delete_during_upload)
    assert upload(client, scan).status_code == 404
    assert list(storage.scan_dir(scan).rglob('*.png')) == []


def test_busy_database_returns_retryable_error(setup):
    client, _, _ = setup
    cause = sqlite3.OperationalError('private lock details')
    cause.sqlite_errorcode = sqlite3.SQLITE_BUSY

    def busy_db():
        raise OperationalError('private SQL', {}, cause)

    app.dependency_overrides[get_db] = busy_db
    response = client.get('/api/scans')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'DATABASE_BUSY'
    assert response.headers['Retry-After'] == '1'
    assert 'private' not in response.text


def test_sqlite_wal_allows_writer_while_reader_is_active(tmp_path):
    engine = make_engine(f'sqlite:///{(tmp_path / "wal.db").as_posix()}', busy_timeout_seconds=0.1)
    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE entries (value INTEGER)'))
        with engine.connect() as reader, engine.connect() as writer:
            assert reader.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            assert reader.exec_driver_sql('PRAGMA busy_timeout').scalar() == 100
            assert reader.exec_driver_sql('PRAGMA journal_mode').scalar() == 'wal'
            reader.exec_driver_sql('BEGIN')
            assert reader.exec_driver_sql('SELECT count(*) FROM entries').scalar() == 0
            writer.exec_driver_sql('INSERT INTO entries VALUES (1)')
            writer.commit()
            assert reader.exec_driver_sql('SELECT count(*) FROM entries').scalar() == 0
            reader.rollback()
            assert reader.exec_driver_sql('SELECT count(*) FROM entries').scalar() == 1
    finally:
        engine.dispose()


def test_upload_capacity_is_released_after_failure(setup, monkeypatch):
    from threading import BoundedSemaphore
    client, _, _ = setup
    scan = create(client)
    slots = BoundedSemaphore(1)
    monkeypatch.setattr('app.main.upload_slots', slots)
    slots.acquire()
    try:
        response = upload(client, scan)
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'UPLOAD_BUSY'
    finally:
        slots.release()
    assert upload(client, scan, data=b'broken').status_code == 422
    assert upload(client, scan).status_code == 201
