import asyncio
import logging
from uuid import uuid4

import pytest
from fastapi import FastAPI, File, UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.main import app, database_error, http_error
from app.storage import StorageError
from app.upload_limits import UploadLimits
from test_api import create, upload


def test_cors_and_private_downloads(setup):
    client, storage, _ = setup
    accepted = client.options("/api/scans", headers={
        "Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST",
    })
    assert accepted.status_code == 200
    assert accepted.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-credentials" not in accepted.headers
    denied = client.options("/api/scans", headers={
        "Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "POST",
    })
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers

    scan, other = create(client), create(client)
    asset = upload(client, scan, filename="..\\..\\test.png").json()
    assert asset["filename"] == "test.png"
    path = f'/api/scans/{scan}/assets/{asset["asset_id"]}/content'
    assert client.get(path).headers["cache-control"] == "no-store"
    assert client.get(path.replace(scan, other)).status_code == 404
    with pytest.raises(StorageError):
        storage.path(f"scans/{scan}/../{asset['asset_id']}.png")
    with pytest.raises(StorageError):
        storage.path(f"scans/{scan}/originals/../../{other}/private.png")
    assert client.get(f"/api/scans/{scan}/assets/not-a-uuid/content").status_code == 422


def test_report_render_failure_is_retriable_without_a_partial_report(setup, monkeypatch):
    client, storage, _ = setup
    scan = create(client)
    original = upload(client, scan)
    assert original.status_code == 201
    url = f"/api/scans/{scan}/reports"

    def fail(_snapshot):
        raise ValueError("Injected render failure")

    with monkeypatch.context() as fault:
        fault.setattr("app.reports.render_pdf", fail)
        response = client.post(url, json={"format": "pdf"})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "REPORT_RENDER_FAILED"
        assert client.get(url).json()["items"] == []
        assert not (storage.scan_dir(scan) / "reports").exists()
    assert client.post(url, json={"format": "pdf"}).status_code == 201


def test_database_error_logs_exclude_values(caplog):
    sensitive = "synthetic-sensitive-sql-value"
    exc = OperationalError("SELECT ?", (sensitive,), ValueError(sensitive))
    with caplog.at_level(logging.ERROR, logger="oralscan"):
        response = asyncio.run(database_error(None, exc))
    assert response.status_code == 500
    assert sensitive not in caplog.text
    assert sensitive.encode() not in response.body


@pytest.mark.parametrize("oversize", [False, True])
def test_multipart_receive_timeout_and_streamed_size_limit(oversize):
    harness = FastAPI()
    harness.add_exception_handler(__import__("starlette.exceptions",fromlist=["HTTPException"]).HTTPException, http_error)
    harness.add_middleware(UploadLimits, max_file_bytes=1024, timeout=0.05)
    reached = False
    endpoint = f"/api/scans/{uuid4()}/assets"

    @harness.post(endpoint)
    async def upload_endpoint(file: UploadFile = File(...)):
        nonlocal reached
        reached = True
        return {"filename": file.filename}

    async def chunks():
        yield b'--t\r\nContent-Disposition: form-data; name="file"; filename="test.png"\r\n\r\n'
        if oversize:
            yield b"x" * (2 * 1024 * 1024)
        else:
            await asyncio.sleep(0.15)
        yield b'\r\n--t--\r\n'

    async def send():
        async with AsyncClient(transport=ASGITransport(app=harness), base_url="http://test") as client:
            return await client.post(endpoint, content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=t"})

    response = asyncio.run(send())
    assert response.status_code == (413 if oversize else 408), response.text
    assert response.json()["error"]["code"] == ("FILE_TOO_LARGE" if oversize else "UPLOAD_TIMEOUT")
    assert not reached
