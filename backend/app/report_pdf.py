from base64 import b64decode
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import os

from .config import get_settings

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

METRIC_LABELS = {
    "vertex_count": "顶点数", "face_count": "面数", "bounding_box": "包围盒",
    "surface_area": "表面积", "volume": "体积", "connected_components": "连通分量",
    "empty_mesh": "空网格", "invalid_vertices": "无效顶点", "degenerate_faces": "退化面",
    "duplicate_vertices": "重复顶点", "holes": "闭合边界环", "watertight": "封闭性",
    "winding_consistency": "绕序一致性", "disconnected_components": "连通分量检查",
    "invalid_normals": "无效计算法线", "source_normals": "源法线检查",
}
STATUS_LABELS = {"ok": "正常", "warning": "警告", "unavailable": "不可用"}


def report_font():
    configured = get_settings().report_font
    if configured:
        paths = [Path(configured)]
    else:
        paths = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"]
    for path in paths:
        if path.is_file():
            pdfmetrics.registerFont(TTFont("OralScanReport", str(path)))
            return "OralScanReport"
    if configured:
        raise ValueError("Configured PDF font is unavailable")
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def render_pdf(snapshot: dict) -> bytes:
    font = report_font()
    ink = colors.HexColor("#163b4b")
    accent = colors.HexColor("#16728a")
    body = ParagraphStyle("Report body", fontName=font, fontSize=10, leading=16,
                          spaceAfter=6, textColor=ink, alignment=TA_LEFT, wordWrap="CJK")
    title = ParagraphStyle("Report title", parent=body, fontSize=22, leading=29, spaceAfter=16)
    heading = ParagraphStyle("Report heading", parent=body, fontSize=13, leading=19,
                             textColor=accent, spaceBefore=11, keepWithNext=True)
    story = []

    def line(text, style=body):
        story.append(Paragraph(escape(str(text)), style))

    def page_frame(canvas, document):
        canvas.setStrokeColor(accent)
        canvas.line(45, 53, A4[0] - 45, 53)
        canvas.setFont(font, 8)
        canvas.setFillColor(ink)
        canvas.drawString(45, 38, "口腔医学影像智能分析系统  /  辅助分析参考")
        canvas.drawRightString(A4[0] - 45, 38, f"{document.page}")

    line("口腔医学影像智能分析系统 检查报告", title)
    if snapshot["is_demo"]:
        line("DEMO · 此报告含演示分析，不能作为临床依据", heading)
    for label, value in (
        ("检查编号", snapshot["scan_id"]),
        ("检查时间 (UTC)", snapshot["created_at"]),
        ("报告生成时间 (UTC)", snapshot["generated_at"]),
        ("扫描来源", ", ".join(snapshot["source_types"]) or "暂无资产"),
        ("资产数量", len(snapshot["assets"])),
    ):
        line(f"{label}  {value}")
    line("免责声明", heading)
    line(snapshot["disclaimer"])
    line("分析限制", heading)
    for limitation in snapshot["limitations"]:
        line(limitation)
    line("后续复核建议", heading)
    line(snapshot["review_recommendation"])
    line("资产概览", heading)
    findings_by_asset = {}
    for finding in snapshot["findings"]:
        findings_by_asset.setdefault(finding["asset_id"], []).append(finding)
    for asset in snapshot["assets"]:
        line(f'{asset["filename"]} · {asset["modality"]} · {asset["analysis_status"]}')

    for asset in snapshot["assets"]:
        story.append(PageBreak())
        line(asset["filename"], title)
        line(f'{asset["modality"]} · 来源 {asset["source_type"]} · 状态 {asset["analysis_status"]}')
        line(f'资产编号  {asset["asset_id"]}')
        preview = asset["preview"]
        if preview["status"] == "available":
            image_bytes = b64decode(preview["base64"])
            with Image.open(BytesIO(image_bytes)) as image:
                width, height = image.size
            scale = min(470 / width, 245 / height)
            drawing = PdfImage(BytesIO(image_bytes), width=width * scale, height=height * scale)
            drawing.hAlign = "LEFT"
            story.extend([drawing, Spacer(1, 8)])
            line("原始图像预览" if asset["modality"] == "image_2d" else "三维模型固定视角预览")
        else:
            line(f'预览不可用  {preview["reason"]}')

        metadata = asset.get("metadata", {})
        if asset["modality"] == "image_2d":
            if metadata.get("width") and metadata.get("height"):
                line(f'原始图像尺寸  {metadata["width"]} × {metadata["height"]} px，未对图像质量作临床判断。')
        else:
            unit = metadata.get("unit", "unknown")
            line(f'网格单位  {unit}')
            if not any(j["result_summary"].get("geometry_metrics") for j in asset["jobs"]):
                line("导入时记录的几何信息", heading)
                for key in ("vertex_count", "face_count", "bounding_box", "surface_area", "volume"):
                    if key in metadata:
                        value = metadata[key]
                        if isinstance(value, float):
                            value = f"{value:.7g}"
                        line(f'{METRIC_LABELS[key]}  {value if value is not None else "不可用"}')
                for warning in metadata.get("warnings", []):
                    line(warning)
        if not asset["jobs"]:
            line("未运行分析。模型与处理时间暂无记录。")
        for job in asset["jobs"]:
            summary = job["result_summary"]
            prefix = "DEMO · " if summary.get("is_demo") else ""
            line(f'{prefix}{job["pipeline"]} · {job["status"]}', heading)
            line(f'分析时间 (UTC)  {job["created_at"]}')
            if job["pipeline"] == "image_2d":
                version = summary.get("model_version") or job["parameters"].get("model_version")
                line(f'模型名称  {summary.get("model_name") or "未记录"}  /  版本  {version or "未记录"}')
            else:
                line(f'几何算法  {job["parameters"].get("algorithm") or "未记录"}')
            elapsed = summary.get("processing_time_ms")
            line(f'处理时间  {f"{elapsed} ms" if elapsed is not None else "未记录"}')
            if summary.get("error"):
                line(summary["error"])
            for group in ("geometry_metrics", "mesh_quality"):
                if summary.get(group):
                    line("几何指标" if group == "geometry_metrics" else "数据质量", heading)
                for key, metric in summary.get(group, {}).items():
                    value = metric.get("value")
                    suffix = metric.get("unit") or ""
                    reason = metric.get("reason") or ""
                    if isinstance(value, float):
                        value = f"{value:.7g}"
                    label = METRIC_LABELS.get(key, key)
                    status = STATUS_LABELS.get(metric["status"], metric["status"])
                    line(f'{label}  {value if value is not None else "不可用"} {suffix} · {status} {reason}')
            for warning in summary.get("warnings", []):
                line(warning)
            for finding in findings_by_asset.get(asset["asset_id"], []):
                if finding["job_id"] != job["job_id"]:
                    continue
                flag = "DEMO · " if finding["evidence"].get("is_demo") else ""
                score = finding["confidence"]
                score_text = f" · 模型分数 {score:.1%}" if score is not None else ""
                category = METRIC_LABELS.get(finding["category"], finding["category"]) if asset["modality"] == "mesh_3d" else finding["category"]
                line(f'{flag}{category}{score_text} · 复核状态 {finding["review_status"]}')
                if finding.get("location"):
                    line(f'位置  {finding["location"]}')
    out = BytesIO()
    document = SimpleDocTemplate(out, pagesize=A4, topMargin=44, bottomMargin=68,
                                 leftMargin=45, rightMargin=45, title="口腔医学影像智能分析系统检查报告")
    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return out.getvalue()
