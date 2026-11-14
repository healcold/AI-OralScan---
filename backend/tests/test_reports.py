import base64
import io
from datetime import datetime
from pathlib import Path
from os import environ

from PIL import Image

from app.geometry.routes import get_private_storage as get_mesh_storage
from app.inference.inference_engine import RuntimeRegistry, get_runtime
from app.inference.routes import get_private_storage as get_image_storage
from app.main import app
from app.models import ScanSession
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
