import hashlib
import os
import re
import shutil
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4
from PIL import Image, UnidentifiedImageError
from fastapi import UploadFile
from .image_processing import read_metadata
from .config import ROOT, get_settings

class StorageError(Exception): pass
class InvalidAsset(Exception): pass
class AssetTooLarge(Exception): pass
class MeshTimeout(Exception): pass


def get_storage():
    settings = get_settings()
    return PrivateStorage(settings.storage_dir, settings.max_upload_bytes)

def safe_name(name: str) -> str:
    name = name.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^\w.\-]', '_', name, flags=re.UNICODE).strip('. ')
    return (name or 'upload')[-200:]

class PrivateStorage:
    def __init__(self, root: Path, limit: int):
        self.root = root.resolve()
        self.limit = limit

    def scan_dir(self, scan_id: str) -> Path:
        scan_id = str(UUID(scan_id))
        return self.root / 'scans' / scan_id

    def path(self, key: str) -> Path:
        parts = key.split('/')
        if (len(parts) != 4 or parts[0] != 'scans'
                or parts[2] not in ('originals', 'reports', 'derived')
                or not re.fullmatch(r'[0-9a-f-]{36}\.[a-zA-Z0-9]+', parts[3])):
            raise StorageError('Invalid storage key')
        try:
            scan = self.scan_dir(parts[1])
        except ValueError as exc:
            raise StorageError('Invalid scan storage key') from exc
        expected = scan / parts[2] / parts[3]
        path = expected.resolve()
        if path != expected:
            raise StorageError('Storage aliases are not allowed')
        return path

    def store_image(self, scan_id: str, file: UploadFile):
        name = safe_name(file.filename or '')
        ext = Path(name).suffix.lower().lstrip('.')
        formats = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}
        if ext not in formats: raise InvalidAsset('Only JPEG, PNG and WebP images are supported in this phase')
        asset_id = str(uuid4())
        key = f'scans/{str(UUID(scan_id))}/originals/{asset_id}.{ext}'
        path = self.path(key)
        digest = hashlib.sha256(); size = 0; created = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as out:
                created = True
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.limit: raise AssetTooLarge()
                    digest.update(chunk); out.write(chunk)
            try:
                with Image.open(path) as image:
                    if image.format != formats[ext]: raise InvalidAsset('File content does not match its extension')
                metadata = read_metadata(path)
            except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
                raise InvalidAsset('Invalid image content') from exc
            return {'asset_id': asset_id, 'filename': name, 'file_format': ext, 'file_size': size, 'storage_key': key, 'sha256': digest.hexdigest(), 'metadata_json': metadata}
        except BaseException:
            if created: path.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()

    def store_mesh(self, scan_id: str, file: UploadFile, unit: str):
        name=safe_name(file.filename or '')
        ext=Path(name).suffix.lower().lstrip('.')
        if ext not in ('stl','obj','ply'): raise InvalidAsset('Only STL, OBJ and PLY are supported')
        asset_id=str(uuid4()); key=f'scans/{str(UUID(scan_id))}/originals/{asset_id}.{ext}'; path=self.path(key)
        digest=hashlib.sha256(); size=0; created=False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as out:
                created=True
                while chunk:=file.file.read(1024*1024):
                    size+=len(chunk)
                    if size>self.limit: raise AssetTooLarge()
                    digest.update(chunk); out.write(chunk)
            try:
                result=subprocess.run([sys.executable,'-m','app.mesh_worker',str(path),ext,unit], cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', timeout=15, check=False)
            except subprocess.TimeoutExpired as exc: raise MeshTimeout() from exc
            try: parsed=json.loads(result.stdout)
            except json.JSONDecodeError as exc: raise InvalidAsset('Mesh parser failed') from exc
            if not isinstance(parsed, dict): raise InvalidAsset('Mesh parser returned an invalid response')
            if result.returncode or not parsed.get('ok'): raise InvalidAsset(parsed.get('error','Invalid mesh'))
            if not isinstance(parsed.get('metadata'), dict): raise InvalidAsset('Mesh parser returned invalid metadata')
            return {'asset_id':asset_id,'filename':name,'file_format':ext,'file_size':size,'storage_key':key,'sha256':digest.hexdigest(),'metadata_json':parsed['metadata']}
        except BaseException:
            if created: path.unlink(missing_ok=True)
            raise
        finally: file.file.close()

    def stage_scan(self, scan_id: str):
        source = self.scan_dir(scan_id)
        if not source.exists(): return None
        trash = self.root / 'pending_deletion'
        trash.mkdir(parents=True, exist_ok=True)
        # Keep the staged path shorter than the source path on Windows.
        target = trash / uuid4().hex[:16]
        os.replace(source, target)
        return source, target

    def restore(self, staged):
        if staged:
            source, target = staged
            source.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, source)

    def purge(self, staged):
        if staged:
            target = str(staged[1].resolve())
            if os.name == 'nt': target = '\\\\?\\' + target
            shutil.rmtree(target)
