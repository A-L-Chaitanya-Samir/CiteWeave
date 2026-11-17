from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CiteWeave"
    debug: bool = False

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)

    chroma_persist_dir: str = str(PROJECT_ROOT / "data" / "chroma")
    chroma_collection_name: str = "research_docs"

    chunk_size: int = Field(default=1000, ge=200, le=10000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    minimum_relevance_score: float = Field(default=0.15, ge=0, le=1)
    max_history_messages: int = Field(default=12, ge=0, le=100)

    max_upload_size_mb: int = Field(default=25, ge=1, le=250)
    max_files_per_upload: int = Field(default=10, ge=1, le=50)
    uploads_dir: str = str(PROJECT_ROOT / "data" / "uploads")

    database_url: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'data' / 'chat.db'}"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if not self.ollama_base_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must be an http(s) URL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
