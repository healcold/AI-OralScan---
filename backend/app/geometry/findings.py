from uuid import NAMESPACE_URL, uuid5

from ..models import AnalysisJob


def geometry_findings(job: AnalysisJob) -> list[dict]:
    """Express observed mesh-wide checks without inventing a location or model score."""
    if job.pipeline != "geometry_3d" or job.status != "succeeded":
        return []
    quality = job.result_summary.get("mesh_quality", {})
    return [
        {
            "finding_id": str(uuid5(NAMESPACE_URL, f"oralscan:{job.job_id}:{check}")),
            "scan_id": job.scan_id, "asset_id": job.asset_id, "job_id": job.job_id,
            "modality": "mesh_3d", "category": check, "confidence": None, "location": None,
            "evidence": {"measurement": measurement, "scope": "whole_mesh", "is_demo": False},
            "model_version": None, "review_status": "unreviewed",
        }
        for check, measurement in quality.items()
        if measurement.get("status") == "warning"
    ]
