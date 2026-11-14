from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_serializer

class ScanCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metadata: dict[str, Any] = Field(default_factory=dict)

class ScanOut(BaseModel):
    scan_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    source_types: list[str]
    metadata: dict[str, Any]

    @field_serializer('created_at', 'updated_at')
    def utc_datetime(self, value: datetime):
        return value.isoformat() + ('Z' if value.tzinfo is None else '')

class AssetOut(BaseModel):
    asset_id: str
    scan_id: str
    modality: str
    source_type: str
    filename: str
    file_format: str
    file_size: int
    storage_key: str
    sha256: str
    created_at: datetime
    metadata: dict[str, Any]

    @field_serializer('created_at')
    def utc_datetime(self, value: datetime):
        return value.isoformat() + ('Z' if value.tzinfo is None else '')

def scan_out(scan):
    return ScanOut(scan_id=scan.scan_id, created_at=scan.created_at, updated_at=scan.updated_at, status=scan.status, source_types=scan.source_types, metadata=scan.metadata_json)

def asset_out(asset):
    return AssetOut(asset_id=asset.asset_id, scan_id=asset.scan_id, modality=asset.modality, source_type=asset.source_type, filename=asset.filename, file_format=asset.file_format, file_size=asset.file_size, storage_key=asset.storage_key, sha256=asset.sha256, created_at=asset.created_at, metadata=asset.metadata_json)
