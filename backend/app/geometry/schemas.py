from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field

class Measurement(BaseModel):
    status: Literal['ok','warning','unavailable']
    value: Any = None
    reason: str | None = None
    unit: str | None = None

class MeshRegionReference(BaseModel):
    """Reserved contract only; no generated regions or highlight endpoint exists."""
    asset_id: str
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    index_space: Literal['source_vertex_indices','source_face_indices']
    indices: list[Annotated[int,Field(ge=0)]] = Field(min_length=1)
    provenance: str = Field(min_length=1)

class MeshAnalysisResult(BaseModel):
    asset_id: str
    job_id: str | None = None
    geometry_metrics: dict[str, Measurement]
    mesh_quality: dict[str, Measurement]
    coordinate_system: dict[str, Any]
    warnings: list[str]
    processing_time_ms: float
    status: Literal['succeeded','failed']
    source_sha256: str | None = None
    regions: dict[str, Any] = Field(default_factory=lambda: {'status':'not_available','items':[],'reason':'No real segmentation data supplied'})
