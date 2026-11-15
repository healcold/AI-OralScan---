# AI 口腔扫描工作台

这是一个个人项目，想把口腔影像采集和识别结果放进一个直观、易浏览的工作台里。项目目前以产品展示和交互演示为主，重点呈现二维口腔照片的扫描与结果查看流程。

![口腔影像检测效果示例](frontend/public/assets/scan-detection-example.png)

## 可以看到什么

- **二维影像展示**：查看口腔照片上的区域标记和识别结果示例。
- **多种采集入口**：通过图片上传、浏览器摄像头或导入三维模型开始体验工作流程。
- **结果与档案页面**：浏览分析、检查记录和报告页面，了解这些信息如何组织在一起。
- **三维模型预览**：导入 STL、OBJ 或 PLY 文件，查看模型和基础几何信息。
- **结果陪伴解读**：图像分析完成后，小安在结果旁解释文字标签、结合患者描述整理就医建议；演示和失败任务不作为病情依据。
- **口腔健康 AI 助理**：温和回应担忧，解释健康信息和检查文字结果，提供与当前工作台一致的操作引导。默认使用免费本地 Qwen3.5，也支持可选 DeepSeek 云端服务。

扫描工作台中的动画和结果卡片用于展示交互流程。仓库已经上传 `best.onnx` 模型文件，但目前还没有接入网站推理；页面展示的检测画面是示例，不是网站对当前照片运行模型后得到的结果。

## 项目状态

这是一个用于展示和学习的个人项目，不是医疗产品。页面内容不能用于诊断或代替专业医生的判断。二维检测模型推理尚未接入；文字 AI 助理需单独下载本地模型后启用，三维几何信息也不代表疾病结论。

## 在本地体验

Windows 用户可以安装 Python 3.12、Node.js 22+ 和 pnpm 后，直接双击项目根目录的 **`start-local.cmd`**。首次启动会安装依赖，后端就绪后再启动前端；看到 Vite 就绪提示后打开 `http://127.0.0.1:5173`。保持窗口开启，结束时按 Ctrl+C。

启动器将 Python 环境放在 `%LOCALAPPDATA%\OralScan` 的独立短路径中，避免深层项目目录导致 ONNX 安装出现 `WinError 206`。不用复制项目，也不会删除原有环境或数据。如果端口已被占用，先关闭之前启动的本地服务。后端日志路径会在启动失败时显示。

不要双击 `dist/index.html`：构建文件需要通过网页服务访问，注册登录等功能还需要后端。只执行 `pnpm dev` 不能启动后端。以下是手动启动方式（深层 Windows 路径建议使用上面的启动器）：

需要 Python 3.11 或更新版本（推荐 3.12）、Node.js 22 及 pnpm。先在一个 PowerShell 窗口启动后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再打开另一个 PowerShell 窗口启动前端：

```powershell
cd frontend
pnpm install
pnpm dev
```

打开前端终端显示的本地网址即可。摄像头采集需要浏览器授权；保存检查、上传文件等功能需要后端保持运行。

后端的并发限制、数据库配置及验证命令见 [后端稳定性说明](docs/BACKEND_STABILITY.md)。

## 创建登录账号

患者可在 `/register` 使用中国大陆手机号注册，自行设置至少 6 个字符的密码。手机号用作登录账号，注册不发送验证码。创建成功后，返回 `/login` 输入手机号和密码登录。

维护者也可以从后端目录手动创建账号（包括管理员账号）：

```powershell
.\.venv\Scripts\python.exe -m app.accounts patient-a
.\.venv\Scripts\python.exe -m app.accounts patient-b
.\.venv\Scripts\python.exe -m app.accounts operator --admin
```

按提示设置各自的密码。打开前端并登录后，在「我的检查」查看当前账号的记录。管理员可管理模型，其账号也只能查看自己的检查。已有数据库会增加归属字段，之前的记录保留为未分配，任何账号都不会自动获得访问权；升级前请备份数据库和私有文件。

部署时通过同一个 HTTPS 域名提供前端和 `/api`，代理保留外部 `Host`，并设置 `ORALSCAN_SECURE_SESSION_COOKIE=true`。口腔图片和报告的存储目录应保持私有，由应用校验账号后提供下载。

本地双账号验收：在前端目录运行 `pnpm build`，再运行 `pnpm exec playwright test e2e/patient-access.spec.ts`。测试使用独立临时数据库和模拟图片，验证另一个账号无法访问直接链接。

## 启用免费 AI 助理

安装 [Ollama](https://ollama.com/download/windows) 后，下载本地文字模型：

```powershell
ollama pull qwen3.5:2b-q4_K_M
```

将 `backend/.env.example` 复制为 `backend/.env`，默认使用本地模型。保持 Ollama 服务运行，重启后端后进入侧栏「AI 助理」。本地模式无需 API 密钥、无按次调用费用，对话在运行服务的电脑上处理；模型未就绪时不会伪造回复。文字模型不能直接查看原始影像或完成病理诊断。

具体配置、可选 DeepSeek 接入和对话资料说明见 [AI 助理接入说明](docs/AI_ASSISTANT.md)。

## 想了解实现细节？

- [PR #4 整合记录与旧测试数据处理](docs/PR4_INTEGRATION.md)
- [华为云部署工作日志、Linux 与网络服务教程（含脱敏配置和下载包）](docs/deployment/README.md)
- [系统架构](docs/ARCHITECTURE.md)
- [模型接入说明](docs/MODEL_INTEGRATION.md)
- [AI 助理接入说明](docs/AI_ASSISTANT.md)
- [三维几何分析说明](docs/GEOMETRY_ANALYSIS.md)
- [API 设计](docs/API_DESIGN.md)

