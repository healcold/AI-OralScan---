from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)

class ScanSession(Base):
    __tablename__ = 'scan_sessions'
    scan_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    status: Mapped[str] = mapped_column(String(30), default='draft')
    source_types: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict)

class ScanAsset(Base):
    __tablename__ = 'scan_assets'
    asset_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scan_id: Mapped[str] = mapped_column(ForeignKey('scan_sessions.scan_id', ondelete='CASCADE'), index=True)
    modality: Mapped[str] = mapped_column(String(30))
    source_type: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(12))
    file_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(150), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSON, default=dict)

class AnalysisJob(Base):
    __tablename__ = 'analysis_jobs'
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scan_id: Mapped[str] = mapped_column(ForeignKey('scan_sessions.scan_id', ondelete='CASCADE'))
    asset_id: Mapped[str] = mapped_column(ForeignKey('scan_assets.asset_id', ondelete='CASCADE'))
    pipeline: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Finding(Base):
    __tablename__ = 'findings'
    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scan_id: Mapped[str] = mapped_column(ForeignKey('scan_sessions.scan_id', ondelete='CASCADE'))
    asset_id: Mapped[str] = mapped_column(ForeignKey('scan_assets.asset_id', ondelete='CASCADE'))
    job_id: Mapped[str] = mapped_column(ForeignKey('analysis_jobs.job_id', ondelete='CASCADE'))
    modality: Mapped[str] = mapped_column(String(30))
    category: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default='unreviewed')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Report(Base):
    __tablename__ = 'reports'
    report_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scan_id: Mapped[str] = mapped_column(ForeignKey('scan_sessions.scan_id', ondelete='CASCADE'))
    format: Mapped[str] = mapped_column(String(10))
    storage_key: Mapped[str] = mapped_column(String(150))
    analysis_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    disclaimer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ModelRegistry(Base):
    __tablename__ = 'model_registry'
    model_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(100))
    task: Mapped[str] = mapped_column(String(30))
    model_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
