# 数据模型草案

使用 SQLite + SQLAlchemy；标识符建议 UUID 字符串，时间为 UTC ISO 8601，JSON 表示结构化元数据。字段及约束在实现时通过迁移与测试确定。原始文件保存在私有文件存储，数据库只保存受控 storage_key，不存任意路径。所有实体均记录创建时间；可变实体记录更新时间。

## ScanSession

`scan_id: UUID` 主键；`created_at, updated_at: datetime`；`status: enum`（draft、ready、analyzing、partial、completed、failed）；`source_types: string[]` 从关联资产汇总或事务维护；`metadata: JSON`。一对多关联 ScanAsset、AnalysisJob、Finding、Report；同一检查允许多模态。

## ScanAsset

`asset_id: UUID` 主键；`scan_id: UUID` 外键；`modality: enum(image_2d, mesh_3d)`；`source_type: enum(upload, camera, model_import, device)`；`filename: string` 安全展示名；`file_format: string`；`file_size: integer`；`storage_key: string`；`sha256: string`；`created_at: datetime`；`metadata: JSON`（图像尺寸、方向、采集时间，或网格单位与坐标信息）；`parent_asset_id: UUID|null` 指向派生物的来源。原件不可覆盖，删除须清理数据库、原件和派生物，并明确失败恢复策略。

## AnalysisJob

`job_id: UUID`；`scan_id: UUID`；`asset_id: UUID`；`pipeline: enum(image_2d, geometry_3d)`；`status: enum(queued, running, succeeded, failed, model_not_configured)`；`model_id: UUID|null`；`started_at, finished_at: datetime|null`；`parameters, result_summary: JSON`；`error: JSON|null`。一次任务针对一个资产与一个管线，允许重试并保留版本及错误。

## Finding

`finding_id: UUID`；`scan_id, asset_id, job_id: UUID` 外键；`modality: enum(image_2d, mesh_3d)`；`category: string`；`confidence: float|null`（模型分数，不是患病概率）；`location: JSON|null`；`evidence: JSON`；`model_version: string|null`；`review_status: enum(unreviewed, reviewed, dismissed)`；`is_demo: boolean`。位置必须带类型和资产版本：2D 用像素 bbox/mask 与图像坐标系；3D 用 mesh 坐标、顶点或面索引与单位。无真实区域数据则不标区域；无配准则不得跨模态映射。

## Report

`report_id: UUID`；`scan_id: UUID`；`format: enum(pdf, json)`；`storage_key: string`；`created_at: datetime`；`analysis_snapshot: JSON`（资产、任务、模型版本、限制、质量与时间）；`disclaimer: string`。报告是生成时的快照，必须明确辅助筛查、非临床诊断；不可伪造结果。

## ModelRegistry

`model_id: UUID`；`name, version: string`；`task: enum(detection, segmentation)`；`file_key: string`；`sha256: string`；`input_spec, output_spec, labels, preprocessing: JSON`；`runtime, device: string`；`status: enum(unconfigured, configured, loaded, failed)`；`validation_notes: string`。模型版本、实际输出、标签及训练预处理未经验证时不用于真实分析；未配置时返回 `MODEL_NOT_CONFIGURED`。

## DeviceRegistry

`device_id: UUID`；`type: enum(browser_camera, dental_scanner)`；`name: string`；`capabilities: JSON`；`status: enum(unknown, available, disconnected)`；`metadata: JSON`；`last_seen_at: datetime|null`。浏览器设备标识的生命周期和权限受浏览器约束；专业扫描仪适配仅在取得设备及官方 SDK 后设计实现。

## 关系与完整性

ScanSession 一对多关联 ScanAsset、AnalysisJob、Finding 和 Report；ScanAsset 一对多关联 AnalysisJob 与 Finding，派生资产可通过 `parent_asset_id` 自关联。AnalysisJob 可多对一关联 ModelRegistry，几何任务的模型引用为空；Finding 多对一关联其 AnalysisJob 和 ScanAsset。DeviceRegistry 为独立目录，资产如需记录设备来源，应使用可空 `device_id: UUID` 外键，并保留采集时设备元数据快照；导入文件可无设备。数据库应验证 job、finding 与 asset 同属同一 scan，避免跨检查引用。模型版本及报告快照保留历史，即使注册表配置后续变化。
