import json
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import database, main, storage
from app.auth import create_account
from app.config import Settings
from app.inference import bundled, inference_engine
from app.inference.inference_engine import RuntimeRegistry
from test_api import create, upload


CREDENTIALS = {'username': 'bundled-model-operator', 'password': 'test-model-operator'}


@pytest.fixture
def startup(tmp_path, monkeypatch):
    url = f'sqlite:///{(tmp_path / "startup.db").as_posix()}'
    models = tmp_path / 'models'
    models.mkdir()
    engine = database.make_engine(url)
    database.initialize_schema(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        create_account(db, **CREDENTIALS, role='admin')

    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(database, 'SessionLocal', factory)
    monkeypatch.setattr(bundled, 'SessionLocal', factory)
    monkeypatch.setattr(storage, 'get_settings', lambda: main.settings)
    monkeypatch.setattr(inference_engine, 'runtime', RuntimeRegistry())

    def client(*, enable=False):
        if enable:
            monkeypatch.setenv('ORALSCAN_ENABLE_BUNDLED_MODEL', 'true')
        else:
            monkeypatch.delenv('ORALSCAN_ENABLE_BUNDLED_MODEL', raising=False)
        settings = Settings(
            _env_file=None,
            database_url=url,
            storage_dir=tmp_path / 'private',
            models_dir=models,
        )
        monkeypatch.setattr(main, 'settings', settings)
        return TestClient(main.app, base_url='https://testserver')

    yield client, models
    engine.dispose()


def login(client):
    response = client.post('/api/auth/login', json=CREDENTIALS)
    assert response.status_code == 200, response.text


def place_verified_model(models):
    copyfile(bundled.CONFIG_PATH.resolve().parents[3] / 'best.onnx', models / 'best.onnx')


def test_startup_loading_is_disabled_by_default(startup):
    start, models = startup
    place_verified_model(models)
    with start() as client:
        login(client)
        assert client.get('/api/models/status').json()['status'] == 'MODEL_NOT_CONFIGURED'
        assert client.get('/api/models').json()['items'] == []


@pytest.mark.parametrize('legacy_registration', [False, True])
def test_verified_model_runs_inference_and_reuses_registration(startup, legacy_registration):
    start, models = startup
    place_verified_model(models)
    existing_id = None
    if legacy_registration:
        with start() as client:
            login(client)
            manifest = json.loads(bundled.CONFIG_PATH.read_text(encoding='utf-8'))
            manifest['name'], manifest['version'] = bundled.LEGACY_IDENTITY
            registered = client.post('/api/models', json=manifest)
            assert registered.status_code == 201, registered.text
            existing_id = registered.json()['model_id']

    with start(enable=True) as client:
        login(client)
        status = client.get('/api/models/status').json()
        assert status['status'] == 'READY', status
        model_id = status['model']['model_id']
        if existing_id is not None:
            assert model_id == existing_id
        scan_id = create(client)
        asset = upload(client, scan_id)
        assert asset.status_code == 201, asset.text
        result = client.post(
            f'/api/scans/{scan_id}/analyze',
            json={'asset_ids': [asset.json()['asset_id']]},
        )
        assert result.status_code == 201, result.text
        assert result.json()['status'] == 'succeeded'
        assert result.json()['is_demo'] is False

    with start(enable=True) as client:
        login(client)
        assert client.get('/api/models/status').json()['model']['model_id'] == model_id
        records = client.get('/api/models').json()['items']
        assert [record['model_id'] for record in records] == [model_id]
        assert [scan['scan_id'] for scan in client.get('/api/scans').json()['items']] == [scan_id]


@pytest.mark.parametrize(
    ('model_bytes', 'message'),
    [(None, 'Model file is unavailable'), (b'wrong sha256', 'Model SHA-256 does not match')],
    ids=['missing', 'checksum-mismatch'],
)
def test_startup_model_error_preserves_the_rest_of_the_api(startup, caplog, model_bytes, message):
    start, models = startup
    with start() as client:
        login(client)
        scan_id = create(client)
    if model_bytes is not None:
        (models / 'best.onnx').write_bytes(model_bytes)

    with start(enable=True) as client:
        assert client.get('/api/health').json()['status'] == 'ok'
        login(client)
        assert client.get(f'/api/scans/{scan_id}').status_code == 200
        assert client.get('/api/models/status').json()['status'] == 'MODEL_NOT_CONFIGURED'
        assert client.get('/api/models').json()['items'] == []
    assert message in caplog.text
