import logging
import sqlite3
from threading import BoundedSemaphore
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4
from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError, TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session
from .config import get_settings
from .database import engine, get_db, initialize_schema, lock_scan_write
from .models import ScanAsset, ScanSession, now
from .schemas import ScanCreate, asset_out, scan_out
from .storage import AssetTooLarge, InvalidAsset, PrivateStorage, StorageError, MeshTimeout, get_storage
from .auth import CurrentAccount, own_scan, require_owned_scan, same_origin_write, router as auth_router
from .upload_limits import UploadLimits, UploadLimitError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('oralscan')
settings = get_settings()

@asynccontextmanager
async def lifespan(_app):
    if settings.database_url.startswith('sqlite:///'):
        db_path = settings.database_url.removeprefix('sqlite:///')
        if db_path != ':memory:': Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    initialize_schema(engine)
    try:
        yield
    finally:
        engine.dispose()

app = FastAPI(title='AI OralScan API', version='0.2.0', lifespan=lifespan)
app.include_router(auth_router)
from .assistant import router as assistant_router
app.include_router(assistant_router)
from .inference.routes import router as inference_router
app.include_router(inference_router)
from .geometry.routes import router as geometry_router
app.include_router(geometry_router)
from .unified import router as unified_router
app.include_router(unified_router)
from .reports import router as reports_router
app.include_router(reports_router)
app.add_middleware(UploadLimits, max_file_bytes=settings.max_upload_bytes, timeout=settings.upload_body_timeout_seconds)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(',') if x.strip()], allow_credentials=False, allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Content-Type'])

@app.middleware('http')
async def private_api_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def error(code: str, message: str, status: int, details=None):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message, 'details': details or {}, 'request_id': str(uuid4())}})

@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return error('VALIDATION_ERROR', 'Invalid request', 422, {'fields': [{'location': list(e['loc']), 'message': e['msg']} for e in exc.errors()]})

@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    code = exc.code if isinstance(exc, UploadLimitError) else 'HTTP_ERROR'
    return error(code, str(exc.detail), exc.status_code)

@app.exception_handler(SQLAlchemyError)
async def database_error(_request: Request, _exc: SQLAlchemyError):
    log.error('Database operation failed (%s)', type(_exc).__name__)
    sqlite_code = getattr(getattr(_exc, 'orig', None), 'sqlite_errorcode', None)
    if isinstance(_exc, PoolTimeoutError) or (
        isinstance(_exc, OperationalError) and sqlite_code is not None
        and sqlite_code & 0xff in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    ):
        response = error('DATABASE_BUSY', 'Database is busy; retry shortly', 503)
        response.headers['Retry-After'] = '1'
        return response
    return error('DATABASE_ERROR', 'Database operation failed', 500)

@app.exception_handler(OSError)
@app.exception_handler(StorageError)
async def storage_error(_request: Request, _exc: Exception):
    log.error('File storage operation failed (%s)', type(_exc).__name__)
    return error('STORAGE_ERROR', 'File storage operation failed', 500)

@app.exception_handler(Exception)
async def unexpected_error(_request: Request, _exc: Exception):
    log.error('Unexpected request failure (%s)', type(_exc).__name__)
    return error('INTERNAL_ERROR', 'An unexpected error occurred', 500)

Db = Annotated[Session, Depends(get_db)]
Storage = Annotated[PrivateStorage, Depends(get_storage)]

def missing_scan(): return error('SCAN_NOT_FOUND', 'Scan not found', 404)

@app.get('/api/health')
def health(db: Db):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'version': '0.2.0'}

@app.post('/api/scans', status_code=201, dependencies=[Depends(same_origin_write)])
def create_scan(payload: ScanCreate, db: Db, account: CurrentAccount):
    scan = ScanSession(owner_id=account.account_id, metadata_json=payload.metadata, source_types=[])
    db.add(scan); db.commit(); db.refresh(scan)
    return scan_out(scan)

@app.get('/api/scans')
def list_scans(
    db: Db,
    account: CurrentAccount,
    scan_id: Annotated[str | None, Query(max_length=36)] = None,
    modality: Literal["image_2d", "mesh_3d", "mixed"] | None = None,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
):
    if any(value is not None and value.tzinfo is None for value in (date_from, date_to)):
        return error("INVALID_DATE_RANGE", "Dates must include a timezone", 422)
    if date_from and date_to and date_from >= date_to:
        return error("INVALID_DATE_RANGE", "The end must be after the start", 422)
    query = select(ScanSession).where(ScanSession.owner_id == account.account_id)
    if scan_id:
        query = query.where(ScanSession.scan_id.contains(scan_id.lower(), autoescape=True))
    if date_from:
        query = query.where(ScanSession.created_at >= date_from.astimezone(timezone.utc).replace(tzinfo=None))
    if date_to:
        query = query.where(ScanSession.created_at < date_to.astimezone(timezone.utc).replace(tzinfo=None))
    if modality:
        for kind in ("image_2d", "mesh_3d") if modality == "mixed" else (modality,):
            query = query.where(select(ScanAsset.asset_id).where(
                ScanAsset.scan_id == ScanSession.scan_id, ScanAsset.modality == kind,
            ).exists())
    scans = db.scalars(query.order_by(ScanSession.created_at.desc(), ScanSession.scan_id)).all()
    return {'items': [scan_out(scan) for scan in scans]}

@app.get('/api/scans/{scan_id}')
def get_scan(scan_id: UUID, db: Db, account: CurrentAccount):
    scan = own_scan(db, account, scan_id)
    return scan_out(scan) if scan else missing_scan()

@app.delete('/api/scans/{scan_id}', status_code=204, dependencies=[Depends(same_origin_write)])
def delete_scan(scan_id: UUID, db: Db, storage: Storage, account: CurrentAccount):
    lock_scan_write(db)
    scan = own_scan(db, account, scan_id)
    if not scan: return missing_scan()
    staged = None
    try:
        # Flush database constraints before moving files. On a commit failure,
        # restore files before releasing the SQLite writer lock.
        db.delete(scan); db.flush()
        staged = storage.stage_scan(str(scan_id))
        db.commit()
    except BaseException:
        try:
            storage.restore(staged)
        finally:
            db.rollback()
        raise
    try:
        storage.purge(staged)
    except OSError as exc:
        # Database deletion has committed. Quarantine remains private for operator cleanup.
        log.error('Deleted scan files remain in pending_deletion (%s)', type(exc).__name__)
        return error('STORAGE_CLEANUP_PENDING', 'Scan was deleted but private file cleanup is pending', 500)
    return Response(status_code=204)

@app.get('/api/scans/{scan_id}/assets', dependencies=[Depends(require_owned_scan)])
def list_assets(scan_id: UUID, db: Db):
    assets = db.scalars(select(ScanAsset).where(ScanAsset.scan_id == str(scan_id)).order_by(ScanAsset.created_at)).all()
    return {'items': [asset_out(asset) for asset in assets]}

upload_slots = BoundedSemaphore(4)


@app.post('/api/scans/{scan_id}/assets', status_code=201, dependencies=[Depends(same_origin_write)])
def create_asset(scan_id: UUID, db: Db, storage: Storage, account: CurrentAccount, file: Annotated[UploadFile, File()], source_type: Annotated[Literal['upload', 'camera', 'model_import'], Form()] = 'upload', captured_at: Annotated[datetime | None, Form()] = None, unit: Annotated[Literal['unknown','mm','cm','m'], Form()] = 'unknown'):
    # FastAPI runs sync endpoints in its worker pool: image decoding, disk writes,
    # SQLite waits and mesh parsing must not block the ASGI event loop.
    if not upload_slots.acquire(blocking=False):
        response = error('UPLOAD_BUSY', 'Upload processing is busy; retry shortly', 503)
        response.headers['Retry-After'] = '1'
        return response
    try:
        return save_asset(scan_id, db, storage, account, file, source_type, captured_at, unit)
    finally:
        try:
            file.file.close()
        finally:
            upload_slots.release()


def save_asset(scan_id, db, storage, account, file, source_type, captured_at, unit):
    if captured_at is not None and captured_at.tzinfo is None:
        return error('VALIDATION_ERROR', 'Capture time must include a timezone', 422)
    scan = own_scan(db, account, scan_id)
    if not scan: return missing_scan()
    # Return the connection before potentially expensive upload validation.
    db.rollback()
    try:
        prepared = storage.store_mesh(str(scan_id), file, unit) if source_type=='model_import' else storage.store_image(str(scan_id), file)
    except InvalidAsset as exc: return error('INVALID_ASSET', str(exc), 422)
    except AssetTooLarge: return error('FILE_TOO_LARGE', 'File exceeds the upload limit', 413)
    except MeshTimeout: return error('MESH_TIMEOUT', 'Mesh parsing exceeded the time limit', 422)
    published = None
    try:
        details = prepared.details
        if captured_at is not None:
            details['metadata_json']['captured_at'] = captured_at.isoformat()
        asset = ScanAsset(scan_id=str(scan_id), modality='mesh_3d' if source_type=='model_import' else 'image_2d', source_type=source_type, **details)
        lock_scan_write(db)
        scan = own_scan(db, account, scan_id)
        if not scan:
            db.rollback()
            return missing_scan()
        published = storage.publish_upload(prepared)
        db.add(asset)
        scan.source_types = sorted(set(scan.source_types + [source_type]))
        scan.updated_at = now()
        db.commit()
    except BaseException:
        try:
            if published is not None:
                published.unlink(missing_ok=True)
        finally:
            db.rollback()
        raise
    finally:
        prepared.discard()
    return asset_out(asset)

@app.get('/api/scans/{scan_id}/assets/{asset_id}/content', dependencies=[Depends(require_owned_scan)])
def asset_content(scan_id: UUID, asset_id: UUID, db: Db, storage: Storage):
    asset = db.get(ScanAsset, str(asset_id))
    if not asset or asset.scan_id != str(scan_id): return error('ASSET_NOT_FOUND', 'Asset not found', 404)
    path = storage.path(asset.storage_key)
    if not path.is_file(): return error('ASSET_FILE_MISSING', 'Asset file is unavailable', 404)
    return FileResponse(path, filename=asset.filename, content_disposition_type='inline' if asset.modality=='image_2d' else 'attachment', media_type={'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','webp':'image/webp'}.get(asset.file_format,'application/octet-stream'), headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
