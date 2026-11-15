"""Register and load the checked-in research model on a running local backend."""
import argparse
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

import httpx

from ..config import get_settings

CONFIG_PATH = Path(__file__).with_name("best_model.json")
REPO_ROOT = CONFIG_PATH.resolve().parents[3]


def checked_response(response: httpx.Response):
    if not response.is_success:
        try:
            detail = response.json()
        except ValueError:
            detail = {}
        message = detail.get("error", {}).get("message") or detail.get("detail")
        if not isinstance(message, str):
            message = f"HTTP {response.status_code}"
        raise RuntimeError(message)
    return response.json()


def place_model(config: dict, model_dir: Path) -> None:
    source = REPO_ROOT / config["model_key"]
    data = source.read_bytes()
    expected = config["sha256"]
    if sha256(data).hexdigest() != expected:
        raise RuntimeError("仓库中的模型与已核对版本不符，请检查 best.onnx 文件。")
    model_dir.mkdir(parents=True, exist_ok=True)
    target = model_dir / config["model_key"]
    if target.is_symlink():
        raise RuntimeError("模型目录中的 best.onnx 是链接，请先检查该文件。")
    if target.exists():
        if sha256(target.read_bytes()).hexdigest() != expected:
            raise RuntimeError("模型目录中已有不同版本的 best.onnx，工具没有覆盖它。")
        return
    with NamedTemporaryFile(dir=model_dir, prefix=".best-", delete=False) as temp:
        temp_path = Path(temp.name)
        try:
            temp.write(data)
            temp.close()
            # Publish the complete file without replacing a concurrent installation.
            os.link(temp_path, target)
        finally:
            temp.close()
            temp_path.unlink(missing_ok=True)


def register_and_load(client, username: str, password: str, config: dict, model_dir: Path):
    account = checked_response(client.post("/api/auth/login", json={"username": username, "password": password}))
    try:
        if account.get("role") != "admin":
            raise RuntimeError("此账号没有模型管理权限，请使用本机工作台管理员账号。")
        place_model(config, model_dir)
        keys = ("name", "version", "model_key", "sha256")
        expected = {k: v for k, v in config.items() if k not in keys}
        records = checked_response(client.get("/api/models"))["items"]
        model = next((row for row in records if row["config"] == expected
                      and all(row[k] == config[k] for k in keys)), None)
        if model is None:
            model = checked_response(client.post("/api/models", json=config))
        result = checked_response(client.post("/api/models/load", json={"model_id": model["model_id"]}))
        if result.get("status") != "READY":
            raise RuntimeError("后端未返回模型就绪状态。")
        return result
    finally:
        try:
            client.post("/api/auth/logout")
        except httpx.RequestError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="启用本机 OralScan 的二维研究检测模型。")
    parser.add_argument("--username", help="本机工作台管理员账号")
    parser.add_argument("--port", type=int, default=8000, help="本机后端端口（默认 8000）")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口须在 1–65535 之间。")
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=30, trust_env=False) as client:
            health = checked_response(client.get("/api/health"))
            if health.get("status") != "ok":
                raise RuntimeError("请先启动本机 OralScan 后端。")
            username = args.username or input("本机管理员账号：").strip()
            if not username:
                raise RuntimeError("请提供本机管理员账号。")
            password = getpass("管理员密码（输入时不显示）：")
            register_and_load(client, username, password, config, get_settings().models_dir)
        print("模型已就绪。请刷新分析页，选择口内近照开始分析。")
        return 0
    except (httpx.RequestError, OSError, RuntimeError) as exc:
        print(f"未能启用模型：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
