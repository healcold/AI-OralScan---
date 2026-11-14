# 技术决策与环境调查

## 环境实测（2026-11-13）

- 项目根目录：`C:\Users\admin\Documents\Codex\2026-11-13\ai-oralscan-reference-object-detect-yolov8n\AI-OralScan`；Windows 10 家庭版 10.0.19045，64 位；PowerShell。
- Node.js v24.22.1（Codex 运行时路径）；`npm` 在当前 PATH 未找到，故无 npm 版本。Phase 1 前需准备可用 Node/npm 并验证版本兼容，不在本阶段安装。
- Python 3.12.10，`py` 可用；`VIRTUAL_ENV` 为空，项目目录未见虚拟环境。当前全局 Python 的 pip 为 25.0.1；已安装 NumPy 2.5.4、opencv-python 5.0.0.93、onnxruntime 1.31.1 等；FastAPI、SQLAlchemy、PyTorch、Trimesh、pytest 不在此次 `pip list` 输出中。全局依赖不是项目锁定依赖，尚未验证兼容性。
- Git 2.56.0.windows.4 可执行；项目及其父目录不是 Git 仓库，`git status` 返回 fatal，因此没有可报告的分支或未提交状态。
- 目前仅有空的 frontend、backend、docs 和空 README/.gitignore，以及参考脚本；不存在项目依赖清单或模型文件。未安装依赖，未创建虚拟环境。

## 决策

遵循用户指定的 React、Vite、TypeScript strict、Tailwind、shadcn/ui、Three.js、ECharts、FastAPI、Pydantic、SQLAlchemy、SQLite 等默认方案；OpenCV、NumPy、YOLO、PyTorch、ONNX Runtime、Trimesh 根据实际管线和模型需要按阶段引入，不为凑技术栈安装。尚未决定模型格式、版本和预处理，依实际模型证据确定；不能自行替换技术栈。shadcn/ui 为组件源码方案，具体版本与兼容性在 Phase 1 核实。

默认本地单机研究架构，SQLite 保存索引和结构化结果，本地私有存储保存原件和派生物；不等于已经满足临床或联网部署的安全要求。3D 坐标单位可为 unknown；二维与三维独立，除非将来引入经验证配准，否则只做结果汇总。项目当前没有专业口腔扫描仪，也没有确认可用的口腔专用模型。模型缺失返回 `MODEL_NOT_CONFIGURED`，模拟必须标记 DEMO。

参考网站由用户提供并说明可在 Edge 打开；本次网页读取工具返回不可访问，本机 computer-use 接口提示 native pipe 不可用，因此未观察其具体页面，不能声称已完成视觉调研。Phase 1 前应通过可用浏览器实查，再参考布局、交互和报告组织，避免复制品牌或设计。
