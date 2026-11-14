from base64 import b64encode
from hashlib import sha256
from io import BytesIO
import json
import subprocess
import sys
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentAccount, own_scan, require_owned_scan, same_origin_write
from .config import ROOT
from .database import get_db, lock_scan_write
from .models import Report, ScanAsset, now
from .report_pdf import render_pdf
from .storage import PrivateStorage, get_storage
from .unified import summarize_scan, timestamp

router = APIRouter(prefix="/api")
DISCLAIMER = "本平台提供基于图像和三维模型的辅助分析参考，不构成临床诊断。实际诊断应由专业口腔医生结合临床检查确定。"
REVIEW = "请由专业口腔医生结合原始资产与临床检查复核结果。若分析缺失或失败，先检查输入质量和分析状态。"


class ReportCreate(BaseModel):
    format: Literal["pdf", "json"]


def asset_preview(asset: ScanAsset, storage: PrivateStorage) -> dict:
    path = storage.path(asset.storage_key)
    try:
        data = path.read_bytes()
        if sha256(data).hexdigest() != asset.sha256:
            return {"status": "unavailable", "reason": "Original asset hash does not match"}
        if asset.modality == "image_2d":
            buffer = BytesIO()
            with Image.open(BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((960, 960), Image.Resampling.LANCZOS)
                image.save(buffer, format="JPEG", quality=88)
            payload, media_type = buffer.getvalue(), "image/jpeg"
        else:
            process = subprocess.run(
                [sys.executable, "-m", "app.report_preview", str(path), asset.file_format],
                cwd=ROOT, capture_output=True, timeout=12, check=True,
            )
            payload, media_type = process.stdout, "image/png"
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "reason": "Mesh preview exceeded the time limit"}
    except (OSError, ValueError, subprocess.CalledProcessError):
        return {"status": "unavailable", "reason": "Original asset could not be rendered"}
    return {"status": "available", "media_type": media_type, "base64": b64encode(payload).decode("ascii")}


def report_out(report: Report) -> dict:
    return {
        "report_id": report.report_id, "scan_id": report.scan_id,
        "format": report.format, "created_at": timestamp(report.created_at),
        "is_demo": report.analysis_snapshot.get("is_demo", False),
        "download_url": f"/api/scans/{report.scan_id}/reports/{report.report_id}/content",
    }


@router.post("/scans/{scan_id}/reports", status_code=201, dependencies=[Depends(same_origin_write)])
def create_report(scan_id: UUID, request: ReportCreate, account: CurrentAccount, db: Session = Depends(get_db),
                  storage: PrivateStorage = Depends(get_storage)):
    from .main import error
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN")
    scan = own_scan(db, account, scan_id)
    if not scan:
        return error("SCAN_NOT_FOUND", "Scan not found", 404)
    snapshot = summarize_scan(db, scan)
    originals = {a.asset_id: a for a in db.scalars(select(ScanAsset).where(ScanAsset.scan_id == str(scan_id)))}
    # Release the read transaction during preview rendering.
    for original in originals.values():
        db.expunge(original)
    db.rollback()
    report_id, generated_at = str(uuid4()), now()
    snapshot.update({
        "schema_version": 1, "report_id": report_id, "generated_at": timestamp(generated_at),
        "disclaimer": DISCLAIMER, "review_recommendation": REVIEW,
        "is_demo": any(f["evidence"].get("is_demo") is True for f in snapshot["findings"])
        or any(j["result_summary"].get("is_demo") is True for a in snapshot["assets"] for j in a["jobs"]),
    })
    for asset in snapshot["assets"]:
        asset_id = asset["asset_id"]
        asset["original_asset_url"] = f"/api/scans/{scan_id}/assets/{asset_id}/content"
        original = originals.get(asset_id)
        asset["preview"] = (asset_preview(original, storage) if original else
                            {"status": "unavailable", "reason": "Original asset is unavailable"})
    if request.format == "pdf":
        try:
            payload = render_pdf(snapshot)
        except (ValueError, OSError):
            return error("REPORT_RENDER_FAILED", "Unable to render the PDF report", 500)
    else:
        payload = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    key = f"scans/{scan_id}/reports/{report_id}.{request.format}"
    path = storage.path(key)
    lock_scan_write(db)
    if not own_scan(db, account, scan_id):
        return error("SCAN_NOT_FOUND", "Scan was removed during report generation", 404)
    report = Report(report_id=report_id, scan_id=str(scan_id), format=request.format,
                    storage_key=key, analysis_snapshot=snapshot, disclaimer=DISCLAIMER, created_at=generated_at)
    created = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            created = True
            output.write(payload)
        db.add(report)
        db.commit()
    except Exception:
        db.rollback()
        if created:
            path.unlink(missing_ok=True)
        raise
    return report_out(report)


@router.get("/scans/{scan_id}/reports", dependencies=[Depends(require_owned_scan)])
def list_reports(scan_id: UUID, db: Session = Depends(get_db)):
    reports = db.scalars(select(Report).where(Report.scan_id == str(scan_id)).order_by(Report.created_at.desc()))
    return {"items": [report_out(report) for report in reports]}


@router.get("/scans/{scan_id}/reports/{report_id}/content", dependencies=[Depends(require_owned_scan)])
def report_content(scan_id: UUID, report_id: UUID, db: Session = Depends(get_db),
                   storage: PrivateStorage = Depends(get_storage)):
    from .main import error
    report = db.get(Report, str(report_id))
    if not report or report.scan_id != str(scan_id):
        return error("REPORT_NOT_FOUND", "Report not found in this scan", 404)
    path = storage.path(report.storage_key)
    if not path.is_file():
        return error("REPORT_FILE_MISSING", "Saved report file is unavailable", 404)
    media_type = "application/pdf" if report.format == "pdf" else "application/json"
    return FileResponse(path, filename=f"oralscan-{report.report_id}.{report.format}", media_type=media_type,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
