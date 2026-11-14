from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='ORALSCAN_', env_file=ROOT / '.env', extra='ignore')
    database_url: str = f'sqlite:///{(ROOT / "data" / "oralscan.db").as_posix()}'
    storage_dir: Path = ROOT / 'data' / 'private'
    cors_origins: str = 'http://127.0.0.1:5173,http://localhost:5173'
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    upload_body_timeout_seconds: float = Field(default=60, gt=0)
    sqlite_busy_timeout_seconds: float = Field(default=10, gt=0, le=60)
    report_font: Path | None = None
    models_dir: Path = ROOT / 'data' / 'models'
    assistant_provider: Literal['ollama', 'deepseek'] = 'ollama'
    assistant_max_concurrent_requests: int = Field(default=2, gt=0, le=32)
    ollama_model: str = Field(default='qwen3.5:2b-q4_K_M', min_length=1, max_length=100)
    ollama_timeout_seconds: float = Field(default=120, gt=0, le=180)
    deepseek_api_key: SecretStr = SecretStr('')
    deepseek_model: str = Field(default='deepseek-flash', min_length=1, max_length=100)
    deepseek_timeout_seconds: float = Field(default=45, gt=0, le=120)

    @field_validator("report_font", mode="before")
    @classmethod
    def blank_font_uses_default(cls, value):
        return None if value == "" else value

@lru_cache
def get_settings() -> Settings:
    return Settings()
