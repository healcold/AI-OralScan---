"""Playwright-only server loading a tiny synthetic ONNX model marked DEMO."""
import sys
from pathlib import Path

import numpy as np
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.inference.inference_engine import runtime
from app.inference.model_loader import load_model
from app.main import app
from types import SimpleNamespace
from test_inference import make_onnx, spec


def main():
    settings = get_settings()
    # Fail closed if invoked without the isolated environment created by Playwright.
    if not (settings.models_dir.parent.name.startswith("oralscan-e2e-")
            and settings.storage_dir.parent == settings.models_dir.parent
            and settings.database_url == f'sqlite:///{(settings.models_dir.parent / "scan.db").as_posix()}'):
        raise RuntimeError("Run this fixture server through the Playwright configuration")
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    predictions = np.array([[[16, 16, 20, 20, 0.9, 0.1, 8]]], dtype=np.float32)
    proto = np.ones((1, 1, 4, 4), dtype=np.float32)
    digest = make_onnx(settings.models_dir / "fixture.onnx", predictions, proto)
    config = spec(model_key="fixture.onnx", sha256=digest, task="segmentation", mask_dim=1)
    session = load_model(settings.models_dir, "fixture.onnx", digest, config)
    runtime.activate(SimpleNamespace(model_id="demo-fixture", name="Synthetic ONNX fixture",
                    version="demo-v1", task="segmentation", config=config), session)
    runtime.adapter.is_demo = True
    uvicorn.run(app, host="127.0.0.1", port=5800, access_log=False)


if __name__ == "__main__":
    main()
