from typing import Annotated, Literal
from uuid import UUID
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AnalysisJob, Finding, ModelRegistry, ScanAsset, ScanSession
from ..storage import PrivateStorage
from .inference_engine import RuntimeRegistry, get_runtime
from .model_loader import ModelLoadError, load_model

router=APIRouter(prefix='/api')

class ModelSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=100)
    version: str=Field(min_length=1,max_length=100)
    task: Literal['detection','segmentation']
    device: Literal['CPUExecutionProvider']='CPUExecutionProvider'
    purpose: Literal['oral_research']
    contract_verified: Literal[True]
    model_key: str=Field(min_length=1,max_length=255)
    sha256: str=Field(pattern=r'^[0-9a-fA-F]{64}$')
    input_size: tuple[int,int]
    labels: list[str]=Field(min_length=1,max_length=100)
    resize_mode: Literal['resize','letterbox']
    color_order: Literal['RGB','BGR']
    dtype: Literal['float32','uint8']
    scale: float=Field(gt=0,le=1)
    pad_value: int=Field(ge=0,le=255)
    output_layout: Literal['BNC','BCN']
    mask_dim: int=Field(ge=0,le=128)
    confidence_threshold: float=Field(ge=0,le=1)
    nms_threshold: float=Field(ge=0,le=1)
    max_detections: int=Field(ge=1,le=100)

    @model_validator(mode='after')
    def validate_contract(self):
        if any(x<1 or x>2048 for x in self.input_size): raise ValueError('Input dimensions must be 1–2048')
        if any(not label.strip() or len(label)>100 for label in self.labels) or len(set(self.labels))!=len(self.labels): raise ValueError('Labels must be unique and non-empty')
        if self.dtype=='uint8' and self.scale!=1: raise ValueError('uint8 requires scale 1')
        if (self.task=='detection' and self.mask_dim!=0) or (self.task=='segmentation' and self.mask_dim<1): raise ValueError('Mask dimension does not match task')
        return self

class LoadRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model_id: UUID

class AnalyzeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset_ids: list[UUID]=Field(min_length=1,max_length=1)
    pipeline: Literal['image_2d']='image_2d'

def respond_error(code,message,status):
    from ..main import error
    return error(code,message,status)

def get_model_root():
    from ..config import get_settings
    return get_settings().models_dir

def get_private_storage():
    from ..main import get_storage
    return get_storage()

Db=Annotated[Session,Depends(get_db)]
Runtime=Annotated[RuntimeRegistry,Depends(get_runtime)]

def model_out(record):
    return {'model_id':record.model_id,'name':record.name,'version':record.version,'task':record.task,'sha256':record.sha256,'model_key':record.model_key,'config':record.config,'created_at':record.created_at}

@router.post('/models',status_code=201)
def register_model(spec:ModelSpec,db:Db):
    from pathlib import PurePosixPath, PureWindowsPath
    if PurePosixPath(spec.model_key).is_absolute() or PureWindowsPath(spec.model_key).is_absolute() or '..' in PurePosixPath(spec.model_key.replace('\\','/')).parts or PureWindowsPath(spec.model_key).drive:
        return respond_error('INVALID_MODEL_KEY','Model key must be a relative path within the models directory',422)
    config=spec.model_dump(exclude={'name','version','model_key','sha256'})
    record=ModelRegistry(name=spec.name,version=spec.version,task=spec.task,model_key=spec.model_key,sha256=spec.sha256.lower(),config=config)
    db.add(record);db.commit();db.refresh(record)
    return model_out(record)

@router.get('/models')
def list_models(db:Db): return {'items':[model_out(m) for m in db.scalars(select(ModelRegistry).order_by(ModelRegistry.created_at.desc())).all()]}

@router.get('/models/status')
def model_status(runtime:Runtime):
    adapter,model_id,name,version=runtime.snapshot()
    if adapter is None:return {'status':'MODEL_NOT_CONFIGURED','model':None}
    return {'status':'READY','model':{'model_id':model_id,'name':name,'version':version,'device':'CPUExecutionProvider'}}

@router.post('/models/load')
def activate_model(payload:LoadRequest,db:Db,runtime:Runtime,root=Depends(get_model_root)):
    record=db.get(ModelRegistry,str(payload.model_id))
    if not record:return respond_error('MODEL_NOT_FOUND','Registered model not found',404)
    try: session=load_model(root,record.model_key,record.sha256,record.config)
    except ModelLoadError as exc: return respond_error('MODEL_LOAD_FAILED',str(exc),422)
    runtime.activate(record,session)
    return model_status(runtime)

@router.post('/scans/{scan_id}/analyze',status_code=201)
def analyze(scan_id:UUID,payload:AnalyzeRequest,db:Db,runtime:Runtime,storage:PrivateStorage=Depends(get_private_storage)):
    if not db.get(ScanSession,str(scan_id)): return respond_error('SCAN_NOT_FOUND','Scan not found',404)
    asset=db.get(ScanAsset,str(payload.asset_ids[0]))
    if not asset or asset.scan_id!=str(scan_id): return respond_error('ASSET_NOT_FOUND','Image asset not found in this scan',404)
    if asset.modality!='image_2d': return respond_error('INVALID_MODALITY','Only 2D image assets are supported',422)
    adapter,model_id,model_name,model_version=runtime.snapshot()
    if adapter is None:return respond_error('MODEL_NOT_CONFIGURED','No oral research model is loaded',409)
    is_demo=getattr(adapter,'is_demo',None)
    if not isinstance(is_demo,bool):return respond_error('INVALID_ADAPTER','Adapter must declare whether its output is DEMO',422)
    job=AnalysisJob(scan_id=str(scan_id),asset_id=asset.asset_id,pipeline='image_2d',status='running',parameters={'model_id':model_id,'model_version':model_version},result_summary={});db.add(job);db.flush()
    started=time.perf_counter()
    try: results=adapter.infer(storage.path(asset.storage_key))
    except Exception:
        job.status='failed';job.result_summary={'error':'Inference failed or model output did not match its contract','processing_time_ms':round((time.perf_counter()-started)*1000,3),'model_name':model_name,'model_version':model_version,'is_demo':is_demo};db.commit()
        return respond_error('INFERENCE_FAILED','Inference failed or model output did not match its contract',422)
    for item in results:
        evidence={**item['evidence'],'is_demo':is_demo}
        db.add(Finding(scan_id=str(scan_id),asset_id=asset.asset_id,job_id=job.job_id,modality='image_2d',category=item['category'],confidence=item['confidence'],location=item['location'],evidence=evidence,model_version=model_version))
    job.status='succeeded';job.result_summary={'count':len(results),'model_name':model_name,'model_version':model_version,'is_demo':is_demo,'processing_time_ms':round((time.perf_counter()-started)*1000,3)};db.commit()
    return {'job_id':job.job_id,'asset_id':asset.asset_id,'status':job.status,'finding_count':len(results),'is_demo':is_demo}

@router.get('/scans/{scan_id}/analysis')
def get_analysis(scan_id:UUID,db:Db):
    if not db.get(ScanSession,str(scan_id)):return respond_error('SCAN_NOT_FOUND','Scan not found',404)
    jobs=db.scalars(select(AnalysisJob).where(AnalysisJob.scan_id==str(scan_id)).order_by(AnalysisJob.created_at.desc())).all()
    findings=db.scalars(select(Finding).where(Finding.scan_id==str(scan_id)).order_by(Finding.created_at.desc())).all()
    return {'jobs':[{'job_id':j.job_id,'asset_id':j.asset_id,'status':j.status,'parameters':j.parameters,'result_summary':j.result_summary,'created_at':j.created_at} for j in jobs], 'findings':[{'finding_id':f.finding_id,'asset_id':f.asset_id,'job_id':f.job_id,'category':f.category,'confidence':f.confidence,'location':f.location,'evidence':f.evidence,'model_version':f.model_version} for f in findings], 'limitations':['Research and assisted screening only; model scores are not disease probabilities.']}
