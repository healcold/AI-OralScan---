import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app, get_storage
from app.storage import PrivateStorage

def image_bytes():
    stream=io.BytesIO(); Image.new('RGB',(4,3),'blue').save(stream,format='PNG'); return stream.getvalue()

def create(client):
    response=client.post('/api/scans',json={'metadata':{'note':'test'}})
    assert response.status_code==201
    return response.json()['scan_id']

def upload(client, scan_id, source='upload', filename='test.png', data=None):
    return client.post(f'/api/scans/{scan_id}/assets', data={'source_type':source}, files={'file':(filename, data if data is not None else image_bytes(),'image/png')})

def test_create_list_get_and_delete_scan(setup):
    client,storage,_=setup
    assert client.get('/api/health').json()['status']=='ok'
    scan_id=create(client)
    assert client.get(f'/api/scans/{scan_id}').json()['metadata']=={'note':'test'}
    assert [s['scan_id'] for s in client.get('/api/scans').json()['items']]==[scan_id]
    asset=upload(client,scan_id).json()
    assert storage.path(asset['storage_key']).exists()
    assert client.delete(f'/api/scans/{scan_id}').status_code==204
    assert client.get(f'/api/scans/{scan_id}').status_code==404
    assert not storage.scan_dir(scan_id).exists()

def test_multiple_assets_source_metadata_hash_and_private_content(setup):
    client,storage,_=setup; scan_id=create(client)
    first=upload(client,scan_id,filename='../unsafe.png').json(); second=upload(client,scan_id,'camera').json()
    assert first['filename']=='unsafe.png' and len(first['sha256'])==64
    assert first['metadata']['width']==4 and first['metadata']['height']==3
    assert len(client.get(f'/api/scans/{scan_id}/assets').json()['items'])==2
    assert set(client.get(f'/api/scans/{scan_id}').json()['source_types'])=={'upload','camera'}
    response=client.get(f'/api/scans/{scan_id}/assets/{second["asset_id"]}/content')
    assert response.content==image_bytes()
    assert client.get('/data/private/'+first['storage_key']).status_code==404
    with pytest.raises(Exception): storage.path('../other')

def test_invalid_requests_and_corrupt_or_oversized_images(setup):
    client,storage,_=setup; scan_id=create(client)
    assert client.post('/api/scans',json={'unexpected':1}).json()['error']['code']=='VALIDATION_ERROR'
    assert client.get('/api/scans/not-a-uuid').status_code==422
    assert upload(client,scan_id,filename='bad.png',data=b'not an image').json()['error']['code']=='INVALID_ASSET'
    broken=bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c020000000b4944415478da63fcff1f0003030200ef97da2a0000000049454e44ae426082')
    assert upload(client,scan_id,filename='bad.png',data=broken).status_code==422
    assert upload(client,scan_id,filename='bad.txt').status_code==422
    storage.limit=2
    assert upload(client,scan_id).status_code==413
    assert client.get(f'/api/scans/{scan_id}/assets').json()['items']==[]

def test_storage_failure_is_explicit_and_preserves_record(setup, monkeypatch):
    client,storage,_=setup; scan_id=create(client); upload(client,scan_id)
    def fail(_): raise OSError('secret path')
    monkeypatch.setattr(storage,'stage_scan',fail)
    response=client.delete(f'/api/scans/{scan_id}')
    assert response.status_code==500 and response.json()['error']['code']=='STORAGE_ERROR'
    assert 'secret path' not in response.text
    assert client.get(f'/api/scans/{scan_id}').status_code==200

def test_database_failure_returns_structured_error(setup):
    client,_,_=setup
    def broken_db(): raise OperationalError('select',{},Exception('private database error'))
    app.dependency_overrides[get_db]=broken_db
    response=client.get('/api/scans')
    assert response.status_code==500 and response.json()['error']['code']=='DATABASE_ERROR'
    assert 'private database error' not in response.text

def test_upload_database_failure_removes_new_file(setup, monkeypatch):
    client,storage,factory=setup; scan_id=create(client)
    def broken_db():
        with factory() as db:
            def fail(): raise OperationalError('insert',{},Exception('failed'))
            monkeypatch.setattr(db,'commit',fail)
            yield db
    app.dependency_overrides[get_db]=broken_db
    response=upload(client,scan_id)
    assert response.status_code==500 and response.json()['error']['code']=='DATABASE_ERROR'
    assert list(storage.scan_dir(scan_id).rglob('*.png'))==[]

def test_delete_database_failure_restores_staged_files(setup, monkeypatch):
    client,storage,factory=setup; scan_id=create(client); asset=upload(client,scan_id).json()
    def broken_db():
        with factory() as db:
            def fail(): raise OperationalError('delete',{},Exception('failed'))
            monkeypatch.setattr(db,'commit',fail)
            yield db
    app.dependency_overrides[get_db]=broken_db
    response=client.delete(f'/api/scans/{scan_id}')
    assert response.status_code==500
    assert storage.path(asset['storage_key']).is_file()
    with factory() as db:
        from app.models import ScanSession
        assert db.get(ScanSession,scan_id) is not None

def test_swagger_and_schema(setup):
    client,_,_=setup
    assert client.get('/docs').status_code==200
    assert '/api/scans' in client.get('/openapi.json').json()['paths']

def test_camera_capture_time_is_preserved(setup):
    client,_,_=setup; scan_id=create(client)
    response=client.post(f'/api/scans/{scan_id}/assets',data={'source_type':'camera','captured_at':'2026-11-13T12:00:00Z'},files={'file':('capture.png',image_bytes(),'image/png')})
    assert response.status_code==201
    assert response.json()['metadata']['captured_at']=='2026-11-13T12:00:00+00:00'
