from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class DocumentAnalysisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    document_storage_dir: str = str(_BACKEND_DIR / "data" / "documents")
    max_document_mb: int = 25
    allowed_extensions: str = ".pdf,.docx,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.webp"
    document_gemini_model: str = "gemini-2.0-flash"
    google_api_key: str | None = None

    @property
    def storage_root(self) -> Path:
        return Path(self.document_storage_dir)

    @property
    def extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}


doc_settings = DocumentAnalysisSettings()
