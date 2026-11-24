# 华为云后端更新 · 模型随服务启动

适用于现有的华为云口腔医学影像智能分析系统部署。后端服务名是 ai-oralscan，上一版后端目录是 /opt/ai-oralscan-release-cf09d59/backend。这次只需切换后端源码和开启模型启动加载。网页由现有 Nginx 提供，SQLite、私有文件和 DeepSeek 继续使用原有服务配置。

在华为云 VNC 的 Linux 终端操作。提示符末尾是 # 时已是 root，否则先运行 sudo -i。各段在同一个终端依次执行。出现错误时，在当前步骤停下。

## 1. 拉取指定提交并预演

先设置 release_sha 为本次发布的完整提交号，从 GitHub 的合并提交页可以复制。

```bash
release_sha='把这里替换为40位提交号'
```

下面代码会在 /opt 创建独立发布目录，并以应用用户加载现有模型。预演使用临时 SQLite 和合成图片。

```bash
if [[ "$release_sha" =~ ^[0-9a-f]{40}$ ]]; then
    release_dir=$(mktemp -d "/opt/ai-oralscan-release-${release_sha:0:12}.XXXXXX")
    printf 'Release directory: %s\n' "$release_dir"
else
    printf 'Please supply a full commit SHA.\n'
fi
```

看到 Release directory 后，执行下一段。

```bash
(
    set -euo pipefail
    umask 022
    old_backend=/opt/ai-oralscan-release-cf09d59/backend
    python=/opt/ai-oralscan/backend/.venv/bin/python

    systemctl is-active --quiet ai-oralscan
    test "$(systemctl show -p User --value ai-oralscan)" = oralscan
    test "$(systemctl show -p WorkingDirectory --value ai-oralscan)" = "$old_backend"
    systemctl show -p ExecStart --value ai-oralscan | grep -F "path=$python " >/dev/null
    test ! -e "$old_backend/.env"
    test ! -L "$old_backend/.env"

    git -C "$release_dir" init -q
    git -C "$release_dir" fetch --depth=1 https://github.com/healcold/AI-OralScan---.git "$release_sha"
    git -C "$release_dir" checkout -q --detach FETCH_HEAD
    test "$(git -C "$release_dir" rev-parse HEAD)" = "$release_sha"
    cmp "$old_backend/requirements.txt" "$release_dir/backend/requirements.txt"
    chmod 0755 "$release_dir"

    preview=$(mktemp -d /var/tmp/ai-oralscan-model-check.XXXXXX)
    chown oralscan:oralscan "$preview"
    cd "$release_dir/backend"
    runuser -u oralscan -- env -i PATH=/usr/bin:/bin \
        ORALSCAN_DATABASE_URL="sqlite:///$preview/preview.db" \
        ORALSCAN_STORAGE_DIR="$preview/private" \
        ORALSCAN_MODELS_DIR=/var/lib/ai-oralscan/models \
        ORALSCAN_ENABLE_BUNDLED_MODEL=true \
        "$python" - "$preview" <<'PY'
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from PIL import Image

from app.inference.inference_engine import get_runtime
from app.main import app

with TestClient(app) as client:
    assert client.get('/api/health').json()['status'] == 'ok'
    adapter, _, name, version = get_runtime().snapshot()
    assert adapter is not None, 'Model did not load. Check the startup log above.'
    image = Path(sys.argv[1]) / 'smoke.png'
    Image.new('RGB', (64, 64), 'white').save(image)
    findings = adapter.infer(image)
    print(f'Model ready: {name} ({version}), synthetic image: {len(findings)} results')
PY
    printf '%s\n' "$release_sha" > "$release_dir/.model-preflight-ok"
    printf 'PREPARE_OK\n'
)
```

合成图片可以产生零个检测框。看到 PREPARE_OK 就表示后端已启动并完成一次 ONNX 推理。若旧后端路径、Python 路径、依赖清单或模型目录与上述约定不同，先核对现网配置。

## 2. 备份数据库并切换

这一步会短暂重启后端。SQLite 备份保存在服务器的 /var/backups 中。新 systemd 配置使用单独的文件，旧版本可以通过移走该文件恢复。

```bash
(
    set -euo pipefail
    old_backend=/opt/ai-oralscan-release-cf09d59/backend
    python=/opt/ai-oralscan/backend/.venv/bin/python
    dropin=/etc/systemd/system/ai-oralscan.service.d/40-bundled-model-release.conf

    test "$(cat "$release_dir/.model-preflight-ok")" = "$release_sha"
    test "$(git -C "$release_dir" rev-parse HEAD)" = "$release_sha"
    git -C "$release_dir" diff --quiet HEAD -- backend
    test ! -e "$release_dir/backend/.env"
    test ! -L "$release_dir/backend/.env"
    test "$(systemctl show -p WorkingDirectory --value ai-oralscan)" = "$old_backend"
    test ! -e "$dropin"
    test ! -L "$dropin"

    backup=$(mktemp -d /var/backups/oralscan-before-model.XXXXXX)
    (umask 077; timeout 90 "$python" - "$backup/oralscan.db" <<'PY'
from contextlib import closing
import sqlite3
import sys

with closing(sqlite3.connect('file:/var/lib/ai-oralscan/oralscan.db?mode=ro', uri=True)) as source:
    with closing(sqlite3.connect(sys.argv[1])) as target:
        source.backup(target)
        if target.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise SystemExit('SQLite backup check failed')
PY
    )
    printf 'Backup: %s/oralscan.db\n' "$backup"

    (set -C; umask 022
    printf '[Service]\nWorkingDirectory=%s/backend\nEnvironment=ORALSCAN_ENABLE_BUNDLED_MODEL=true\n' \
        "$release_dir" > "$dropin")
    systemctl daemon-reload
    test "$(systemctl show -p WorkingDirectory --value ai-oralscan)" = "$release_dir/backend"
    systemctl restart ai-oralscan
    curl -fsS --retry 15 --retry-connrefused --retry-delay 1 --max-time 5 --retry-max-time 45 \
        http://127.0.0.1:8000/api/health
    printf '\n'
    invocation=$(systemctl show -p InvocationID --value ai-oralscan)
    test -n "$invocation"
    journalctl --no-pager -o cat "_SYSTEMD_INVOCATION_ID=$invocation" | grep -F 'Bundled model ready:'
    printf 'DEPLOY_OK\n'
)
```

看到 DEPLOY_OK 后，在自己电脑打开 README 第一行的 HTTPS 网站。登录后查看一条原有检查，再用演示图片做一次「分析」。如果也要确认 DeepSeek，打开小安问一句普通问题。

## 3. 切换后出问题时回退

第 2 段已经写入 40-bundled-model-release.conf 时，运行这一段恢复旧后端。备份文件保留在服务器，回退代码无需覆盖生产数据库。

```bash
(
    set -euo pipefail
    dropin=/etc/systemd/system/ai-oralscan.service.d/40-bundled-model-release.conf
    test -f "$dropin"
    archived=$(mktemp /var/backups/oralscan-model-dropin.XXXXXX)
    mv -T -- "$dropin" "$archived"
    systemctl daemon-reload
    test "$(systemctl show -p WorkingDirectory --value ai-oralscan)" = \
        /opt/ai-oralscan-release-cf09d59/backend
    systemctl restart ai-oralscan
    curl -fsS --retry 15 --retry-connrefused --retry-delay 1 --max-time 5 --retry-max-time 45 \
        http://127.0.0.1:8000/api/health
    printf '\nROLLBACK_OK\n'
)
```
