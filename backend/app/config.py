from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./athletecore.db"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    memory_auth_token: str | None = None
    disable_reranker: bool = False

    extraction_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    planner_model: str = "gpt-4o-mini"
    analyst_model: str = "claude-sonnet-4-20250514"
    health_model: str = "claude-sonnet-4-20250514"
    direct_model: str = "gpt-4o-mini"
    aggregator_model: str = "gpt-4o-mini"

    whisper_model: str = "whisper-1"
    whisper_language: str = "ru"

    graph_checkpoint_path: str = "./graph_checkpoints.sqlite"

    recall_stable_min_cos: float = 0.2
    recall_ranked_min_cos: float = 0.2
    comparison_match_min_score: float = 0.38
    comparison_recall_min_cos: float = 0.28
    memory_timezone: str = "Asia/Almaty"
    development_mode: bool = False

    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_base_url: str | None = None  # alias used in Langfuse UI/docs
    langfuse_env: str = "development"
    langfuse_trace_verbose: bool = False
    langfuse_sample_rate: float = 1.0

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_timeout_sec: int = 30
    qdrant_collection_methodology: str = "sports_methodology"
    methodology_use_qdrant: bool = True
    methodology_fallback_lexical: bool = True
    methodology_min_score: float = 0.25
    methodology_chunk_tokens: int = 900
    methodology_chunk_overlap_tokens: int = 120

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator(
        "disable_reranker",
        "development_mode",
        "langfuse_enabled",
        "langfuse_trace_verbose",
        mode="before",
    )
    @classmethod
    def _bool_from_env(cls, v: object) -> bool:
        if v is None or v == "":
            return False
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def langfuse_host_resolved(self) -> str:
        base = (self.langfuse_base_url or self.langfuse_host or "").strip().strip('"')
        return base or "https://cloud.langfuse.com"

    @field_validator("langfuse_public_key", "langfuse_secret_key", mode="before")
    @classmethod
    def _strip_langfuse_keys(cls, v: object) -> object:
        if v is None:
            return None
        s = str(v).strip().strip('"').strip("'")
        return s or None


def load_settings() -> Settings:
    return Settings()


settings = load_settings()

# Startup visibility (uvicorn reload) — confirms .env DEVELOPMENT_MODE is loaded
print(f"[settings] development_mode={settings.development_mode}")
