import base64
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from os import environ
from threading import Barrier, Event

from PIL import Image
from sqlalchemy import event, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.geometry.routes import get_private_storage as get_mesh_storage
from app.inference.inference_engine import RuntimeRegistry, get_runtime
from app.inference.routes import get_private_storage as get_image_storage
from app.main import app
from app.models import Report, ScanSession
from test_api import create, upload, image_bytes
from test_geometry import upload_mesh


def test_multimodal_history_report_round_trip(setup):
    client, storage, factory = setup
    runtime = RuntimeRegistry()

    class DemoAdapter:
        is_demo = True
        fail = False

        def infer(self, _):
            if self.fail:
                raise ValueError("Synthetic failure")
            return [{
                "category": "Synthetic region",
                "confidence": 0.8,
                "location": {"coordinate_space": "exif_oriented_image_pixels",
                             "bbox": [0, 0, 4, 3], "image_size": [4, 3]},
                "evidence": {},
            }]

    adapter = DemoAdapter()
    runtime.model_id = "demo-model"
    runtime.name = "Synthetic verification model"
    runtime.version = "fixture-v1"
    runtime.adapter = adapter
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[get_image_storage] = lambda: storage
    app.dependency_overrides[get_mesh_storage] = lambda: storage
    scan = create(client)
    unrelated = create(client)
    with factory() as db:
        db.get(ScanSession, scan).created_at = datetime(2026, 11, 12, 16, 15)
        db.get(ScanSession, unrelated).created_at = datetime(2026, 11, 12, 15, 59)
        db.commit()
    image = upload(client, scan, source="camera").json()
    mesh, mesh_bytes = upload_mesh(client, scan, "open.obj")
    base = f"/api/scans/{scan}"
    assert client.post(f"{base}/analyze", json={"asset_ids": [image["asset_id"]]}).status_code == 201
    assert client.post(f'{base}/assets/{mesh["asset_id"]}/geometry-analysis').status_code == 200
    adapter.fail = True
    assert client.post(f"{base}/analyze", json={"asset_ids": [image["asset_id"]]}).status_code == 422

    unified = client.get(f"{base}/unified-analysis").json()
    assets = {a["asset_id"]: a for a in unified["assets"]}
    assert assets[image["asset_id"]]["analysis_status"] == "failed"
    assert assets[mesh["asset_id"]]["analysis_status"] == "succeeded"
    finding = next(f for f in unified["findings"] if f["modality"] == "image_2d")
    assert finding["asset_id"] == image["asset_id"] and finding["scan_id"] == scan
    assert finding["location"]["coordinate_space"] == "exif_oriented_image_pixels"
    assert finding["model_version"] == "fixture-v1" and finding["evidence"]["is_demo"]
    mesh_findings = [f for f in unified["findings"] if f["modality"] == "mesh_3d"]
    assert mesh_findings and all(f["asset_id"] == mesh["asset_id"] and f["location"] is None for f in mesh_findings)

    filters = {"scan_id": scan[:8], "modality": "mixed",
               "from": "2026-11-13T00:00:00+08:00", "to": "2026-11-14T00:00:00+08:00"}
    assert [s["scan_id"] for s in client.get("/api/scans", params=filters).json()["items"]] == [scan]
    assert client.get("/api/scans", params={"scan_id": "%"}).json()["items"] == []
    assert client.get("/api/scans", params={"from": "2026-11-13T00:00:00"}).status_code == 422

    saved = {}
    for kind in ("json", "pdf"):
        response = client.post(f"{base}/reports", json={"format": kind})
        assert response.status_code == 201, response.text
        saved[kind] = response.json()
        assert saved[kind]["is_demo"]
    assert {r["format"] for r in client.get(f"{base}/reports").json()["items"]} == {"pdf", "json"}
    json_response = client.get(saved["json"]["download_url"])
    snapshot = json_response.json()
    assert snapshot["disclaimer"] == "本平台提供基于图像和三维模型的辅助分析参考，不构成临床诊断。实际诊断应由专业口腔医生结合临床检查确定。"
    assert snapshot["findings"] == unified["findings"]
    for asset in snapshot["assets"]:
        assert asset["preview"]["status"] == "available"
        preview = Image.open(io.BytesIO(base64.b64decode(asset["preview"]["base64"])))
        assert preview.format == ("JPEG" if asset["modality"] == "image_2d" else "PNG")
        if asset["modality"] == "image_2d":
            assert client.get(asset["original_asset_url"]).content == image_bytes()
        else:
            assert client.get(asset["original_asset_url"]).content == mesh_bytes
            assert asset["jobs"][0]["result_summary"]["geometry_metrics"]["volume"]["value"] is None

    pdf = client.get(saved["pdf"]["download_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert pdf.headers["content-type"] == "application/pdf"
    if qa_path := environ.get("ORALSCAN_PHASE7_QA_PDF"):
        Path(qa_path).write_bytes(pdf.content)
    assert client.get(saved["pdf"]["download_url"].replace(scan, unrelated)).status_code == 404
    adapter.fail = False
    assert client.post(f"{base}/analyze", json={"asset_ids": [image["asset_id"]]}).status_code == 201
    assert client.get(saved["json"]["download_url"]).content == json_response.content
    assert client.get(saved["pdf"]["download_url"]).content == pdf.content
    assert client.delete(base).status_code == 204
    assert client.get(saved["pdf"]["download_url"]).status_code == 404
    assert not storage.scan_dir(scan).exists()


def test_report_commit_failure_removes_file_and_allows_retry(setup, monkeypatch):
    client, storage, _ = setup
    scan = create(client)
    assert upload(client, scan).status_code == 201
    url = f"/api/scans/{scan}/reports"
    commit = Session.commit

    def failing_commit(db):
        if any(isinstance(row, Report) for row in db.new):
            raise OperationalError("INSERT", {}, RuntimeError("injected commit failure"))
        return commit(db)

    with monkeypatch.context() as fault:
        fault.setattr(Session, "commit", failing_commit)
        response = client.post(url, json={"format": "json"})
    assert response.status_code == 500
    assert client.get(url).json()["items"] == []
    assert not list((storage.scan_dir(scan) / "reports").glob("*.json"))
    assert client.post(url, json={"format": "json"}).status_code == 201


def test_report_does_not_recreate_scan_deleted_during_render(setup, monkeypatch):
    import app.reports as reports

    client, storage, _ = setup
    scan = create(client)
    assert upload(client, scan).status_code == 201
    preview = reports.asset_preview

    def delete_after_preview(asset, private_storage):
        result = preview(asset, private_storage)
        assert client.delete(f"/api/scans/{scan}").status_code == 204
        return result

    monkeypatch.setattr(reports, "asset_preview", delete_after_preview)
    response = client.post(f"/api/scans/{scan}/reports", json={"format": "json"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SCAN_NOT_FOUND"
    assert not storage.scan_dir(scan).exists()


def test_unrenderable_preview_does_not_discard_report(setup, monkeypatch):
    client, _, _ = setup
    scan = create(client)
    assert upload(client, scan).status_code == 201
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    response = client.post(f"/api/scans/{scan}/reports", json={"format": "json"})
    assert response.status_code == 201
    snapshot = client.get(response.json()["download_url"]).json()
    assert snapshot["assets"][0]["preview"]["status"] == "unavailable"


def test_report_metadata_and_download_do_not_load_preview_snapshot(setup):
    client, _, _ = setup
    scan = create(client)
    assert upload(client, scan).status_code == 201
    url = f"/api/scans/{scan}/reports"
    saved = client.post(url, json={"format": "json"}).json()
    loaded = []

    def check_deferred(report, _context):
        loaded.append(report.report_id)
        assert "analysis_snapshot" in inspect(report).unloaded

    event.listen(Report, "load", check_deferred)
    try:
        listing = client.get(url)
        download = client.get(saved["download_url"])
    finally:
        event.remove(Report, "load", check_deferred)
    assert listing.status_code == download.status_code == 200
    assert listing.json()["items"] == [saved]
    assert loaded == [saved["report_id"], saved["report_id"]]


def test_report_generation_rejects_excess_concurrency_and_recovers(setup, monkeypatch):
    import app.reports as reports

    client, _, _ = setup
    scan = create(client)
    assert upload(client, scan).status_code == 201
    url = f"/api/scans/{scan}/reports"
    ready, finish = Barrier(3), Event()
    preview = reports.asset_preview

    def slow_preview(asset, storage):
        ready.wait(timeout=10)
        assert finish.wait(timeout=10)
        return preview(asset, storage)

    with monkeypatch.context() as fault, ThreadPoolExecutor(max_workers=2) as pool:
        fault.setattr(reports, "asset_preview", slow_preview)
        pending = [pool.submit(client.post, url, json={"format": "json"}) for _ in range(2)]
        try:
            ready.wait(timeout=10)
            rejected = client.post(url, json={"format": "json"})
            assert rejected.status_code == 503
            assert rejected.json()["error"]["code"] == "REPORT_BUSY"
            assert client.get("/api/health").status_code == 200
        finally:
            finish.set()
        assert all(task.result(timeout=10).status_code == 201 for task in pending)
    assert client.post(url, json={"format": "json"}).status_code == 201
