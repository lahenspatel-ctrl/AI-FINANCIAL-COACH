from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    app_env: str = "development"
    log_level: str = "INFO"

    # OpenRouter / LLM
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_overrides_json: str = "{}"

    # Tavily web search
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    tavily_max_results: int = 3

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # Vector store
    chroma_path: str = "./data/chroma"

    # File uploads
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 26_214_400  # 25 MB

    # Rate limiting (requests per minute per model)
    rate_limit_rpm: int = 20

    @field_validator("openrouter_api_key", mode="before")
    @classmethod
    def _strip_placeholder_openrouter(cls, v: str) -> str:
        if v and v.startswith("sk-or-v1-your"):
            return ""
        return v

    @field_validator("tavily_api_key", mode="before")
    @classmethod
    def _strip_placeholder_tavily(cls, v: str) -> str:
        if v and v.startswith("tvly-your"):
            return ""
        return v

    def model_overrides(self) -> dict[str, list[str]]:
        try:
            return json.loads(self.model_overrides_json)
        except Exception:
            return {}

    def ensure_dirs(self) -> None:
        Path(self.chroma_path).mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path("data").mkdir(parents=True, exist_ok=True)


settings = Settings()
