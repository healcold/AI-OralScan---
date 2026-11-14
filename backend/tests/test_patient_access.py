from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.auth import COOKIE, create_account
from app.database import initialize_schema, make_engine
from app.main import app
from app.models import AccountRecovery, ScanSession
from test_api import create, upload


def test_legacy_database_migration_keeps_records_unassigned(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    try:
        with engine.begin() as db:
            db.exec_driver_sql("CREATE TABLE scan_sessions (scan_id VARCHAR(36) PRIMARY KEY)")
            db.exec_driver_sql("INSERT INTO scan_sessions (scan_id) VALUES ('legacy')")
        initialize_schema(engine)
        initialize_schema(engine)
        with engine.connect() as db:
            assert db.exec_driver_sql("SELECT scan_id, owner_id FROM scan_sessions").one() == ('legacy', None)
            assert 'accounts' in inspect(db).get_table_names()
    finally:
        engine.dispose()


def test_patient_access_is_checked_for_records_files_reports_and_assistant(setup):
    existing, _, factory = setup
    with factory() as db:
        a = create_account(db, 'patient-a', 'test-password-only-a')
        create_account(db, 'patient-b', 'test-password-only-b')
        legacy = ScanSession(source_types=[], metadata_json={'note': 'legacy'})
        db.add(legacy)
        db.commit()
        legacy_id = legacy.scan_id

    with TestClient(app, raise_server_exceptions=False) as patient_a, TestClient(app, raise_server_exceptions=False) as patient_b:
        assert patient_b.get('/api/scans').status_code == 401
        assert patient_b.post('/api/scans', json={'metadata': {}}).status_code == 401
        for client, suffix in [(patient_a, 'a'), (patient_b, 'b')]:
            login = client.post('/api/auth/login', json={'username': f'patient-{suffix}', 'password': f'test-password-only-{suffix}'})
            assert login.status_code == 200
            assert 'httponly' in login.headers['set-cookie'].lower()
            assert 'samesite=strict' in login.headers['set-cookie'].lower()
            assert client.get('/api/auth/me').json() == {'username': f'patient-{suffix}', 'role': 'patient'}
        scan = create(patient_a)
        with factory() as db:
            assert db.get(ScanSession, scan).owner_id == a.account_id
            assert db.get(ScanSession, legacy_id).owner_id is None
        asset = upload(patient_a, scan).json()['asset_id']
        base = f'/api/scans/{scan}'
        raw = f'{base}/assets/{asset}/content'
        report = patient_a.post(f'{base}/reports', json={'format': 'json'})
        assert report.status_code == 201
        report_url = report.json()['download_url']
        assert patient_a.get(report_url).status_code == 200
        assert patient_a.get(raw).status_code == 200

        b_scan = create(patient_b)
        assert [s['scan_id'] for s in patient_a.get('/api/scans').json()['items']] == [scan]
        assert [s['scan_id'] for s in patient_b.get('/api/scans').json()['items']] == [b_scan]
        for url in (base, f'{base}/assets', raw, f'{base}/analysis', f'{base}/unified-analysis',
                    f'{base}/assets/{asset}/geometry-analysis', f'{base}/reports', report_url, f'/api/scans/{legacy_id}'):
            assert patient_b.get(url).status_code == 404, url
        assert existing.get(base).status_code == 404  # Admin cannot read patient records.
        assert patient_b.post('/api/models/load', json={'model_id': scan}).status_code == 403
        assert upload(patient_b, scan).status_code == 404
        assert patient_b.post(f'{base}/reports', json={'format': 'json'}).status_code == 404
        assert patient_b.post(f'{base}/analyze', json={'asset_ids': [asset]}).status_code == 404
        assert patient_b.post(f'{base}/assets/{asset}/geometry-analysis').status_code == 404
        assert patient_b.delete(base).status_code == 404
        for fields in ({'scan_id': scan}, {'scan_id': scan, 'asset_id': asset, 'intent': 'explain_result'}):
            denied = patient_b.post('/api/assistant/chat', json={
                'provider': 'ollama', 'consent': True, 'messages': [{'role': 'user', 'content': '请解释结果'}], **fields})
            assert denied.status_code == 404
        assert patient_a.get(base).status_code == 200
        token = patient_a.cookies.get(COOKIE)
        assert patient_a.post('/api/auth/logout').status_code == 204
        patient_a.cookies.set(COOKIE, token)
        assert patient_a.get(report_url).status_code == 401


def test_login_and_mutations_reject_cross_origin(setup):
    client, _, _ = setup
    headers = {'Origin': 'https://another.example'}
    assert client.post('/api/auth/login', json={'username': 'unknown', 'password': 'wrong'}, headers=headers).status_code == 403
    assert client.post('/api/scans', json={'metadata': {}}, headers=headers).status_code == 403


def test_registration_creates_only_a_patient_and_requires_separate_login(setup):
    _, _, factory = setup
    with factory() as db:
        legacy = ScanSession(source_types=[], metadata_json={})
        db.add(legacy)
        db.commit()
        legacy_id = legacy.scan_id

    phone = '13900006124'
    password = 'demo!6'
    body = {'phone': phone, 'password': password, 'question': 'teacher', 'answer': '松'}
    with TestClient(app, raise_server_exceptions=False, base_url='https://testserver') as guest:
        assert guest.post('/api/auth/register', json={**body, 'phone': '123'}).status_code == 422
        assert guest.post('/api/auth/register', json={**body, 'password': 'short'}).status_code == 422
        assert guest.post('/api/auth/register', json={**body, 'role': 'admin'}).status_code == 422
        assert guest.post('/api/auth/register', json={**body, 'answer': '  '}).status_code == 422
        response = guest.post('/api/auth/register', json=body)
        assert response.status_code == 201
        assert response.json() == {'username': phone, 'role': 'patient'}
        assert 'set-cookie' not in response.headers
        assert guest.get('/api/auth/me').status_code == 401
        assert guest.post('/api/auth/register', json={**body, 'password': 'replacement'}).status_code == 409
        assert guest.post('/api/auth/login', json={'username': phone, 'password': 'replacement'}).status_code == 401
        assert guest.post('/api/auth/login', json={'username': phone, 'password': password}).status_code == 200
        assert guest.get('/api/scans').json()['items'] == []
        assert guest.get(f'/api/scans/{legacy_id}').status_code == 404


def test_password_reset_requires_private_answer_and_revokes_sessions(setup):
    _, _, factory = setup
    phone, old_password, new_password = '13900006125', 'old-password', 'new-password'
    answer = '模拟长答案' * 30
    recovery = {'phone': phone, 'question': 'mother', 'answer': answer}
    reset = {**recovery, 'password': new_password}
    login = {'username': phone, 'password': old_password}
    with TestClient(app, base_url='https://testserver') as existing, TestClient(app, base_url='https://testserver') as guest:
        assert existing.post('/api/auth/register', json={**recovery, 'password': old_password}).status_code == 201
        with factory() as db:
            saved = db.query(AccountRecovery).one()
            assert len(saved.answer_hash) == 128 and saved.answer_hash != answer
        assert existing.post('/api/auth/login', json=login).status_code == 200
        scan_id = create(existing)

        def submit(**changes):
            return guest.post('/api/auth/reset-password', json={**reset, **changes})

        assert guest.post('/api/auth/reset-password', json=reset, headers={'Origin': 'https://other.example'}).status_code == 403
        unknown = submit(phone='13900006126')
        wrong = submit(answer='incorrect-private-answer')
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()['error']['message'] == wrong.json()['error']['message']
        assert submit(question='father').status_code == 401
        assert existing.get('/api/auth/me').status_code == 200
        response = submit()
        assert response.status_code == 204 and 'set-cookie' not in response.headers
        assert existing.get(f'/api/scans/{scan_id}').status_code == 401
        assert guest.get('/api/auth/me').status_code == 401
        assert guest.post('/api/auth/login', json=login).status_code == 401
        assert guest.post('/api/auth/login', json={**login, 'password': new_password}).status_code == 200
        assert guest.get(f'/api/scans/{scan_id}').status_code == 200


def test_password_reset_caps_attempts_per_account(setup):
    client, _, _ = setup
    body = {'phone': '13900006127', 'question': 'teacher', 'answer': 'incorrect-secret-answer', 'password': 'new-password'}
    for _ in range(5):
        assert client.post('/api/auth/reset-password', json=body).status_code == 401
    assert client.post('/api/auth/reset-password', json=body).status_code == 429
