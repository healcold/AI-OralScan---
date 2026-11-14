# AI OralScan

Phase 7 在同一检查下展示二维和三维结果，支持 PDF 与 JSON 报告及历史查询。当前没有确认可用的口腔专用模型，未配置时不会产生二维推理结果。模型接入见 `docs/MODEL_INTEGRATION.md`，三维指标及其限制见 `docs/GEOMETRY_ANALYSIS.md`。研究和辅助筛查用途，不构成临床诊断。

在 PowerShell 中进入 `AI-OralScan/backend`，安装并启动后端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API 文档为 http://127.0.0.1:8000/docs 。另开 PowerShell，进入 `AI-OralScan/frontend`，安装依赖并启动：

```powershell
pnpm install
pnpm dev
```

打开终端输出的本地地址。前端开发服务器将 `/api` 代理到本地 8000 端口；自定义端口时需同步修改 Vite 代理。验证：前端执行 `pnpm build`、`pnpm typecheck`、`pnpm lint`、`pnpm test`；后端执行 `.\.venv\Scripts\python.exe -m pytest -q`。

通用 Unix shell（Linux 或 macOS）可在 `AI-OralScan/backend` 执行以下命令创建环境并启动后端；需要 Python 3 和对应平台可安装的依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在另一个终端进入 `AI-OralScan/frontend`，使用 Node.js 22 或更新版本及 pnpm，执行 `pnpm install` 和 `pnpm dev`。后端测试运行 `.venv/bin/python -m pytest -q`；端到端测试在前端目录执行 `pnpm test:e2e`，需要 Playwright 可用的浏览器。可选配置复制 `backend/.env.example` 为 `backend/.env` 并按本机环境修改；首次启动时数据库自动初始化。以上 Unix 命令尚未在本次 Windows 验收环境执行。

在 Analysis 的 Unified analysis 标签选择检查，可查看按资产列出的任务状态、失败原因、模型版本、耗时和结果。三维质量发现描述整个网格，没有局部坐标。二维检测框仍使用对应原图的像素坐标。

在 Reports 选择检查并生成 PDF 或 JSON。报告保留生成时的结果和预览，后续重新分析不会改变已保存的报告。PDF 嵌入原始图像的缩放预览和网格的固定视角预览。JSON 包含相同的预览数据和本地原件访问地址。报告显示模型缺失、任务失败及无法生成预览的情况。Windows 默认嵌入微软雅黑，也可通过进程环境变量 `ORALSCAN_REPORT_FONT` 指向可用的中文字体文件。

在 History 可按浏览器本地日期、模态和编号筛选。打开检查可访问原始资产、已保存分析和报告。删除检查会同时移除资产、任务和报告。

数据库和文件默认位于 `backend/data`，通过 `.env.example` 中的环境变量调整；不要公开此目录。资产 API 接受经内容校验的 JPEG、PNG、WebP 和 STL、OBJ、PLY，原件保存在 `scans/<id>/originals/`，`derived/` 为后续派生物预留。上传上限默认 25 MiB，图片上限 4000 万像素。页面预览使用浏览器图像方向处理；后端保存 EXIF 方向并通过独立处理模块按需修正，原文件不被改写。

3D 导入允许选择已有检查或创建新检查；单位默认 `unknown`，可选 mm、cm、m，不自动换算。Trimesh 在独立子进程中进行基础解析，限制 200,000 顶点、400,000 面和 15 秒解析时间（STL 在合并顶点前按每面三个顶点计数）。OBJ 的材质库和外部纹理引用被忽略，不加载外部文件；3D 可视化为几何预览，不能假定所有格式均有材质或颜色。网格质量和几何指标不代表疾病。解析进程没有操作系统级内存配额，不应作为不可信大规模上传的生产隔离方案。

运行 `backend/.venv/Scripts/python.exe backend/tests/fixtures/generate_meshes.py`（从项目根目录）可重复生成合成测试文件和几何预期清单。

摄像头需要浏览器支持及用户授权，并在安全上下文中运行（本地 `localhost` 或 `127.0.0.1` 可用）。选择图片或拍摄多帧后，点击确认才创建检查并上传。多文件上传中断时，同一页面可重试剩余帧；已保存帧不会重复上传。离开采集页面会清除尚未上传的预览，已保存数据保留在历史记录中。

删除时先把文件移入私有 `pending_deletion`，数据库失败则恢复；数据库提交后如果文件清理失败，接口返回 `STORAGE_CLEANUP_PENDING`，须由操作人员检查该目录并清理。SQLite 数据与文件系统没有跨介质原子事务，进程异常中断时也须检查待清理目录。

目前仅适合本地开发：尚无登录、授权或加密，也不适合对外部署或处理真实患者数据。API 不直接暴露存储目录，已知 ID 的文件可通过受控 API 读取，因此不能把本地访问视作权限控制。
