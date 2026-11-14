"""Aggregate independent pipeline results while retaining their source coordinates."""
from uuid import UUID
from datetime import timezone
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import ScanSession, ScanAsset, AnalysisJob, Finding
from .geometry.findings import geometry_findings

router=APIRouter(prefix='/api')
PIPELINE_FOR_MODALITY = {"image_2d": "image_2d", "mesh_3d": "geometry_3d"}

def timestamp(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat().replace('+00:00','Z')

def summarize_scan(db: Session, scan: ScanSession):
    assets = db.scalars(select(ScanAsset).where(ScanAsset.scan_id == scan.scan_id)
                        .order_by(ScanAsset.created_at, ScanAsset.asset_id)).all()
    jobs = db.scalars(select(AnalysisJob).where(AnalysisJob.scan_id == scan.scan_id)
                      .order_by(AnalysisJob.created_at.desc(), AnalysisJob.job_id.desc())).all()
    findings = db.scalars(select(Finding).where(Finding.scan_id == scan.scan_id)
                          .order_by(Finding.created_at, Finding.finding_id)).all()
    asset_by_id = {asset.asset_id: asset for asset in assets}
    jobs_by_asset = defaultdict(list)
    job_by_id = {}
    entries = []
    mesh_findings = []
    for job in jobs:
        asset = asset_by_id.get(job.asset_id)
        if asset is None or PIPELINE_FOR_MODALITY.get(asset.modality) != job.pipeline:
            continue
        job_by_id[job.job_id] = job
        jobs_by_asset[job.asset_id].append({
            "job_id": job.job_id, "pipeline": job.pipeline, "status": job.status,
            "created_at": timestamp(job.created_at), "parameters": job.parameters,
            "result_summary": job.result_summary,
        })
        mesh_findings.extend(geometry_findings(job))
    for asset in assets:
        related = jobs_by_asset[asset.asset_id]
        entries.append({
            "asset_id": asset.asset_id, "modality": asset.modality, "source_type": asset.source_type,
            "filename": asset.filename, "file_format": asset.file_format, "file_size": asset.file_size,
            "sha256": asset.sha256, "created_at": timestamp(asset.created_at), "metadata": asset.metadata_json,
            "analysis_status": related[0]["status"] if related else "not_analyzed", "jobs": related,
        })
    image_findings = []
    for finding in findings:
        job = job_by_id.get(finding.job_id)
        if finding.modality != "image_2d" or not job or job.pipeline != "image_2d" or job.asset_id != finding.asset_id:
            continue
        location = finding.location
        if location and location.get("coordinate_space") != "exif_oriented_image_pixels":
            continue
        image_findings.append({
            "finding_id": finding.finding_id, "scan_id": finding.scan_id, "asset_id": finding.asset_id,
            "job_id": finding.job_id, "modality": finding.modality, "category": finding.category,
            "confidence": finding.confidence, "location": location, "evidence": finding.evidence,
            "model_version": finding.model_version, "review_status": finding.review_status,
        })
    return {
        "scan_id": scan.scan_id, "created_at": timestamp(scan.created_at), "status": scan.status,
        "source_types": scan.source_types, "assets": entries, "findings": image_findings + mesh_findings,
        "limitations": [
            "Research and assisted screening only; model scores are not disease probabilities.",
            "2D and 3D coordinates are independent; no spatial registration has been performed.",
            "Mesh quality findings describe whole-mesh measurements; no segmentation was performed.",
        ],
    }

@router.get('/scans/{scan_id}/unified-analysis')
def unified_analysis(scan_id: UUID, db: Session=Depends(get_db)):
    scan=db.get(ScanSession,str(scan_id))
    if not scan:
        from .main import error
        return error('SCAN_NOT_FOUND','Scan not found',404)
    return summarize_scan(db,scan)
