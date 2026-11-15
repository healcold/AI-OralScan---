# Phase 5：口腔研究模型接入

仓库根目录的 `best.onnx` 可作为可选的 YOLO11n 研究模型。将它复制到 `ORALSCAN_MODELS_DIR`（默认 `backend/data/models`），设置 `ORALSCAN_ENABLE_BUNDLED_MODEL=true` 后重启后端。服务会校验 SHA-256、注册模型并在启动时加载。未开启时仍可走下方的手动流程。云端部署时，将开关写入后端服务的环境配置，并确保服务账号能读取模型文件。

`MODEL_NOT_CONFIGURED` 表示当前服务进程没有加载模型。已用合成图片验证 CPU 推理链路。检测质量仍需用已知样本验证，模型分数不代表患病概率。

## 参考代码复核

K230 示例使用 `nncase_runtime`、`ulab` 和设备采集显示库，不能用于本地运行。本项目独立实现预处理、推理、解码、筛选、类别感知 NMS 和坐标映射。原示例直接缩放图像、引用全局阈值、跨类别 NMS，并以 `uint8` 保存索引；模型文件未提供，无法验证其实际输入输出。

## 明确支持的 ONNX 契约

只支持 CPU ONNX Runtime、一个 NCHW 输入，单张批次，`float32` 或 `uint8`；输入大小、RGB/BGR、scale、直接 resize 或居中 letterbox、填充值均必须由模型提供方确认。直接缩放和 letterbox 均使用 Pillow 双线性插值。模型有不同插值、归一化、通道或后处理要求时不可使用此适配器。

检测输出必须是一个 float32 tensor，布局显式声明 `BNC`（`[1,N,4+C]`）或 `BCN`（`[1,4+C,N]`）。每候选项为模型输入像素坐标 `cx,cy,w,h`，接着是 C 个已经在 [0,1] 的类别分数；不含 objectness、内置 NMS、归一化坐标或 logits。仅使用与模型实际导出一致的配置。分割输出需要同一候选布局末尾加 M 个 mask 系数，并提供第二个 `[1,M,H,W]` float32 prototype；使用系数与 prototype 相乘、sigmoid、边框裁剪和逆预处理生成显示 mask。与此不同的导出必须先实现并验证专用适配器。

这些约束不是对所有 YOLO 版本或导出的推断。注册前必须从实际模型、导出脚本和训练数据核对版本、标签、预处理和输出语义，并用已知样本验证。加载时验证文件哈希、模型输入输出数量、类型和可验证的静态维度；推理时再次验证实际 tensor。技术校验不等于训练标签或临床性能验证。

## 本地注册与加载

1. 将获得并验证的 ONNX 文件放到 `backend/data/models/`（可设置 `ORALSCAN_MODELS_DIR`）。服务只接受目录内的相对 `.onnx` 路径和匹配 SHA-256；模型字节被读取后加载，外部 ONNX 数据文件不支持。
2. 计算 SHA-256。PowerShell：`Get-FileHash -Algorithm SHA256 <模型文件>`。
3. 向 `POST /api/models` 提交与真实模型一致的 JSON；以下是**不可直接使用的模板**。`contract_verified` 必须由实际审核人确认后改为 true，标签必须来自真实训练清单，不能把 COCO 类别或模板文字当成口腔标签。

```json
{
  "name": "填写已核验模型名", "version": "填写真实版本与导出版本",
  "task": "detection", "device": "CPUExecutionProvider", "purpose": "oral_research", "contract_verified": false,
  "model_key": "填写模型文件.onnx", "sha256": "替换成64位SHA256",
  "input_size": [320, 320], "labels": ["替换成真实训练标签"],
  "resize_mode": "letterbox", "color_order": "RGB", "dtype": "float32",
  "scale": 0.00392156862745098, "pad_value": 114,
  "output_layout": "BCN", "mask_dim": 0,
  "confidence_threshold": 0.25, "nms_threshold": 0.45, "max_detections": 50
}
```

所有示例数值均须按具体模型修改；`input_size` 顺序为宽、高。分割需 `task=segmentation` 且 `mask_dim` 与真实模型一致。模型列表通过 `GET /api/models` 查看，`POST /api/models/load` 接收 `{"model_id":"..."}` 并验证、加载。注册信息持久化于 SQLite；加载状态在当前单个服务进程内，重启后需重新加载，不支持多进程间自动同步。

`POST /api/scans/{scan_id}/analyze` 接受 `{"asset_ids":["..."],"pipeline":"image_2d"}`，本阶段每次处理一个图片资产，响应为已完成任务。未加载模型返回 409 `MODEL_NOT_CONFIGURED`，不会产生任务或结果。推理失败记录失败任务并返回 `INFERENCE_FAILED`。`GET /api/scans/{scan_id}/analysis` 返回任务和 findings；位置使用 EXIF 修正后的图像像素，额外保留原始图像坐标。前端显示最新任务，列表和框均与指定资产关联。测试用 mock adapter 如果启用必须设置 `is_demo=True`；接口强制将它标记为 DEMO。发布的服务不注册任何 mock adapter。
