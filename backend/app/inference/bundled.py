"""Load the repository's verified research model into the current backend."""

from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from ..database import SessionLocal, lock_scan_write
from ..models import ModelRegistry
from .inference_engine import get_runtime
from .model_loader import ModelLoadError, load_model
from .routes import ModelSpec, model_out


CONFIG_PATH = Path(__file__).with_name('best_model.json')
REGISTRATION_FIELDS = {'name', 'version', 'model_key', 'sha256'}
# The original Huawei Cloud build registered the same model under these values.
LEGACY_IDENTITY = ('OralScan YOLO11n', 'best-2026-11-14')


def find_bundled_registration(records: Iterable[dict], manifest: dict) -> dict | None:
    config = {key: value for key, value in manifest.items() if key not in REGISTRATION_FIELDS}
    identity = (manifest['name'], manifest['version'])
    legacy = None
    for record in records:
        if (
            record['model_key'] != manifest['model_key']
            or record['sha256'] != manifest['sha256']
            or record['config'] != config
        ):
            continue
        record_identity = (record['name'], record['version'])
        if record_identity == identity:
            return record
        if legacy is None and record_identity == LEGACY_IDENTITY:
            legacy = record
    return legacy


def activate_bundled_model(root: Path) -> ModelRegistry:
    try:
        spec = ModelSpec.model_validate_json(CONFIG_PATH.read_bytes())
    except (OSError, ValidationError) as exc:
        raise ModelLoadError('Bundled model manifest is unavailable or invalid') from exc

    manifest = spec.model_dump(mode='json')
    config = spec.model_dump(mode='json', exclude=REGISTRATION_FIELDS)
    session = load_model(root, spec.model_key, spec.sha256, config)

    with SessionLocal() as db:
        # Run ONNX initialization before the transaction, then serialize SQLite registration.
        lock_scan_write(db)
        records = {
            record.model_id: record
            for record in db.scalars(
                select(ModelRegistry)
                .where(ModelRegistry.model_key == spec.model_key, ModelRegistry.sha256 == spec.sha256)
                .order_by(ModelRegistry.created_at.desc(), ModelRegistry.model_id)
            )
        }
        match = find_bundled_registration((model_out(record) for record in records.values()), manifest)
        if match is None:
            record = ModelRegistry(
                name=spec.name,
                version=spec.version,
                task=spec.task,
                model_key=spec.model_key,
                sha256=spec.sha256,
                config=config,
            )
            db.add(record)
        else:
            record = records[match['model_id']]
        db.commit()

    get_runtime().activate(record, session)
    return record
