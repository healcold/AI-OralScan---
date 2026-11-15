from pathlib import Path

from sqlalchemy import select

from ..database import SessionLocal, lock_scan_write
from ..models import ModelRegistry
from .inference_engine import get_runtime
from .model_loader import load_model
from .routes import ModelSpec


def activate_bundled_model(root: Path) -> None:
    spec = ModelSpec(
        name='OralScan YOLO11n', version='best-2026-11-14', task='detection',
        purpose='oral_research', contract_verified=True, model_key='best.onnx',
        sha256='d360a72a4c48542eed5147296e67084122dda514b0a376948ae6e59d7b80315c',
        input_size=(640, 640),
        labels=['calculus', 'caries', 'gingivitis', 'hypodontia', 'tooth_discolation', 'ulcer'],
        resize_mode='letterbox', color_order='RGB', dtype='float32',
        scale=1 / 255, pad_value=114, output_layout='BCN', mask_dim=0,
        confidence_threshold=0.25, nms_threshold=0.45, max_detections=50,
    )
    config = spec.model_dump(mode='json', exclude={'name', 'version', 'model_key', 'sha256'})
    session = load_model(root, spec.model_key, spec.sha256, config)
    with SessionLocal() as db:
        lock_scan_write(db)
        records = db.scalars(select(ModelRegistry).where(
            ModelRegistry.model_key == spec.model_key, ModelRegistry.sha256 == spec.sha256,
        ))
        record = next((item for item in records if item.config == config), None)
        if record is None:
            record = ModelRegistry(
                name=spec.name, version=spec.version, task=spec.task,
                model_key=spec.model_key, sha256=spec.sha256, config=config,
            )
            db.add(record)
        db.commit()
    get_runtime().activate(record, session)
