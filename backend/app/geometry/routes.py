import json
import subprocess
import sys
import time
from threading import BoundedSemaphore
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import ROOT
from ..database import get_db, lock_scan_write
from ..models import AnalysisJob, ScanAsset, ScanSession
from ..storage import PrivateStorage, StorageError
from .pipeline import failed_result
from .schemas import MeshAnalysisResult
from .findings import geometry_findings

router=APIRouter(prefix='/api')
Db=Annotated[Session,Depends(get_db)]
geometry_slots=BoundedSemaphore(2)

def get_private_storage():
    from ..main import get_storage
    return get_storage()

def error(code,message,status,details=None):
    from ..main import error as api_error
    return api_error(code,message,status,details)

def check_asset(scan_id,asset_id,db):
    if not db.get(ScanSession,str(scan_id)):return None,error('SCAN_NOT_FOUND','Scan not found',404)
    asset=db.get(ScanAsset,str(asset_id))
    if not asset or asset.scan_id!=str(scan_id):return None,error('ASSET_NOT_FOUND','Asset not found in this scan',404)
    if asset.modality!='mesh_3d':return None,error('INVALID_MODALITY','Asset is not a 3D mesh',422)
    return asset,None

@router.post('/scans/{scan_id}/assets/{asset_id}/geometry-analysis')
def analyze_geometry(scan_id:UUID,asset_id:UUID,db:Db,storage:PrivateStorage=Depends(get_private_storage)):
    if not geometry_slots.acquire(blocking=False):
        response=error('GEOMETRY_BUSY','Geometry analysis capacity is busy; retry shortly',503)
        response.headers['Retry-After']='1'
        return response
    try:
        return run_geometry_analysis(scan_id,asset_id,db,storage)
    finally:
        geometry_slots.release()

def run_geometry_analysis(scan_id,asset_id,db,storage):
    lock_scan_write(db)
    asset,problem=check_asset(scan_id,asset_id,db)
    if problem:return problem
    unit=asset.metadata_json.get('unit','unknown')
    job=AnalysisJob(scan_id=str(scan_id),asset_id=str(asset_id),pipeline='geometry_3d',status='running',parameters={'asset_sha256':asset.sha256,'unit':unit,'algorithm':'geometry_v1'},result_summary={})
    storage_key=asset.storage_key;file_format=asset.file_format;sha256=asset.sha256
    db.add(job);db.flush();job_id=job.job_id
    # Release the connection while the bounded subprocess does CPU work.
    db.commit();started=time.perf_counter()
    try:
        path=storage.path(storage_key)
        proc=subprocess.run([sys.executable,'-m','app.geometry.worker',str(path),file_format,unit,str(asset_id),sha256],cwd=str(ROOT),capture_output=True,text=True,timeout=20,check=False)
        if proc.returncode!=0:raise ValueError('Geometry worker failed to process the asset')
        result=MeshAnalysisResult.model_validate(json.loads(proc.stdout))
    except subprocess.TimeoutExpired:
        result=failed_result(str(asset_id),unit,'Geometry processing exceeded the 20-second time limit.',round((time.perf_counter()-started)*1000,3))
    except (OSError,ValueError,StorageError):
        result=failed_result(str(asset_id),unit,'Geometry worker failed or the original asset is unavailable.',round((time.perf_counter()-started)*1000,3))
    lock_scan_write(db)
    db.expunge_all()
    job=db.get(AnalysisJob,job_id)
    if job is None:return error('SCAN_NOT_FOUND','Scan was deleted while analysis was running',404)
    result.job_id=job_id
    job.status=result.status;job.result_summary=result.model_dump(mode='json');db.commit()
    if result.status=='failed': return error('GEOMETRY_ANALYSIS_FAILED',result.warnings[0],422,{'job_id':job.job_id})
    return {**job.result_summary, 'findings': geometry_findings(job)}

@router.get('/scans/{scan_id}/assets/{asset_id}/geometry-analysis')
def get_geometry(scan_id:UUID,asset_id:UUID,db:Db):
    asset,problem=check_asset(scan_id,asset_id,db)
    if problem:return problem
    job=db.scalars(select(AnalysisJob).where(AnalysisJob.scan_id==str(scan_id),AnalysisJob.asset_id==str(asset_id),AnalysisJob.pipeline=='geometry_3d').order_by(AnalysisJob.created_at.desc(),AnalysisJob.job_id.desc())).first()
    if not job:return error('GEOMETRY_NOT_ANALYZED','This mesh has not been analyzed',404)
    if job.status=='running':return {'asset_id':str(asset_id),'job_id':job.job_id,'status':'running'}
    return {**job.result_summary, 'findings': geometry_findings(job)}
