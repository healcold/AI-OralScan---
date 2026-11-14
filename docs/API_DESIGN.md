# REST API 草案

前缀 `/api`，JSON 使用 snake_case，时间 UTC，ID 为 UUID；资产上传使用 multipart。此文仅为设计，端点尚未实现。成功返回资源对象或 `{items, next_cursor}`；删除成功 204。统一错误：`{"error":{"code":"VALIDATION_ERROR","message":"...","details":{},"request_id":"..."}}`。400 格式错误、404 不存在、409 状态冲突、413 过大、415 类型不支持、422 内容无效、500 内部错误；实际状态码在实现与测试中统一。

| 方法与路径 | 参数/请求 | 成功返回 |
|---|---|---|
| GET /health | 无 | `{status, version}` |
| POST /scans | `{metadata?}` | 201 ScanSession |
| GET /scans | `from?, to?, modality?, scan_id?`，日期为带时区的时间戳，开始包含、结束排除，模态可选 image_2d、mesh_3d、mixed | `{items: [ScanSession]}` |
| GET /scans/{scan_id} | 路径 ID | ScanSession，含资产摘要 |
| DELETE /scans/{scan_id} | 路径 ID | 204；受控删除记录和文件 |
| POST /scans/{scan_id}/assets | multipart `file, source_type, unit?` | 201 ScanAsset；校验类型和大小 |
| GET /scans/{scan_id}/assets | 路径 ID | `{items: [ScanAsset]}` |
| GET /scans/{scan_id}/assets/{asset_id}/content | 归属检查 | 受控文件流，不公开存储目录 |
| DELETE /scans/{scan_id}/assets/{asset_id} | 归属检查 | 204 |
| POST /scans/{scan_id}/analyze | `{asset_ids, pipeline, model_id?, parameters?}`，每次只提交一种管线 | 202 `{jobs: [{job_id, asset_id, status}]}`；二维请求预检无模型时 409 `MODEL_NOT_CONFIGURED`，不创建任务 |
| GET /scans/{scan_id}/analysis | 路径 ID | `{jobs, findings, limitations}`，含各模态状态 |
| GET /scans/{scan_id}/unified-analysis | 路径 ID | 资产、独立任务、统一 findings 与分析限制 |
| GET /jobs/{job_id} | 路径 ID | AnalysisJob 与错误详情 |
| GET /models | 无 | `{items: [ModelRegistry]}`，不暴露本地路径 |
| GET /models/status | 无 | `{status, active_model}` |
| POST /models/load | `{model_id}` | 模型状态；校验配置与文件 |
| GET /devices | 无 | `{items}`；浏览器摄像头在客户端枚举 |
| POST /scans/{scan_id}/reports | `{format: "pdf"|"json"}` | 201 Report 或 202 生成任务 |
| GET /scans/{scan_id}/reports | 路径 ID | `{items: [Report]}` |
| GET /scans/{scan_id}/reports/{report_id}/content | 归属检查 | 受控下载流 |

检查不存在、文件损坏、任务失败、模型不兼容、存储故障应给出可操作且不泄露私有路径的错误。多模态任务应分别记录结果和失败；模型检测结果及几何结果均保留来源资产与各自坐标系。应用面向本地研究；认证、授权、部署边界及敏感数据保护须在对外部署前具体设计，不能视为已实现。

异步任务接受后若模型变为不可用，任务可记录 `model_not_configured`，通过任务查询返回该状态；已完成的其他任务保持不变。无模型时不会生成虚假 findings。
