import io
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from PIL import Image
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app
from test_api import create, upload


def test_failed_delete_during_upload_preserves_existing_assets(setup, monkeypatch):
    client, storage, factory = setup
    scan = create(client)
    existing = upload(client, scan).json()
    upload_started, staged, prepared = Event(), Event(), Event()
    original_store, original_stage = storage.store_image, storage.stage_scan

    def concurrent_store(*args):
        upload_started.set()
        assert staged.wait(5)
        result = original_store(*args)
        prepared.set()
        return result

    def concurrent_stage(*args):
        result = original_stage(*args)
        staged.set()
        assert prepared.wait(5)
        return result

    def fail_delete_only():
        with factory() as db:
            commit = db.commit
            delete = db.delete
            deleting = False

            def mark_delete(record):
                nonlocal deleting
                deleting = True
                delete(record)

            def commit_or_fail():
                if deleting:
                    raise OperationalError('delete', {}, Exception('injected failure'))
                commit()

            monkeypatch.setattr(db, 'commit', commit_or_fail)
            monkeypatch.setattr(db, 'delete', mark_delete)
            yield db

    monkeypatch.setattr(storage, 'store_image', concurrent_store)
    monkeypatch.setattr(storage, 'stage_scan', concurrent_stage)
    app.dependency_overrides[get_db] = fail_delete_only
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(upload, client, scan)
        assert upload_started.wait(5)
        deletion = pool.submit(client.delete, f'/api/scans/{scan}')
        assert deletion.result(timeout=10).status_code == 500
        assert pending.result(timeout=10).status_code == 201
    assert storage.path(existing['storage_key']).is_file()
    assert client.get(f'/api/scans/{scan}/assets/{existing["asset_id"]}/content').status_code == 200
    assert len(client.get(f'/api/scans/{scan}/assets').json()['items']) == 2
    assert not list((storage.root / 'pending_deletion').iterdir())


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '1e999', '"\\ud800"'])
def test_invalid_nested_metadata_is_rejected_before_persistence(setup, value):
    client, _, _ = setup
    response = client.post('/api/scans', content='{"metadata":{"nested":[{"value":' + value + '}]}}',
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert client.get('/api/scans').json()['items'] == []


def test_truncated_jpeg_is_rejected_before_persistence(setup):
    client, storage, _ = setup
    scan = create(client)
    image = io.BytesIO()
    Image.new('RGB', (32, 32), 'blue').save(image, format='JPEG')
    # PIL's JPEG verify() accepts this header, but decoding the pixels fails.
    truncated = image.getvalue()[:-12]
    response = upload(client, scan, filename='truncated.jpg', data=truncated)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'INVALID_ASSET'
    assert client.get(f'/api/scans/{scan}/assets').json()['items'] == []
    assert list(storage.scan_dir(scan).rglob('*.jpg')) == []
