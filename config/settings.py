"""Central configuration. The ONLY module allowed to read environment variables.

Everything else does `from config.settings import settings`. Values come from real
environment variables first, then from `.env`. Keys must never be logged: use
`mask()` for anything that could reach a log, an error message or the UI.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


def _split(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def mask(secret: str | None) -> str:
    """Safe display form of a key, e.g. AIza****."""
    if not secret:
        return "(unset)"
    return f"{secret[:4]}****" if len(secret) > 8 else "****"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Provider keys. Comma-separated lists rotate on 429/quota errors.
    gemini_api_keys: str = ""
    groq_api_keys: str = ""
    openrouter_api_keys: str = ""
    huggingface_api_keys: str = ""
    mistral_api_keys: str = ""

    # Model routing. Overridable, since free-tier model names change.
    gemini_model_fast: str = ""
    gemini_model_strong: str = ""
    groq_model_fast: str = ""
    groq_model_strong: str = ""
    openrouter_model_fast: str = ""
    openrouter_model_strong: str = ""

    # Local LLM: free, no key, no quota.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # Provider order. "deterministic" is always the implicit final link.
    llm_chain: str = "gemini,groq,openrouter,ollama"

    # OFFLINE=true: no external network calls. Local Ollama is still allowed.
    offline: bool = False
    # DEMO_CACHE=true: replay LLM answers recorded from real runs, labelled in the UI.
    demo_cache: bool = False
    # Redact PII before any external LLM call. Never turn off for a real deployment.
    redact_pii_external: bool = True
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2

    # Paths and limits
    data_dir: Path = REPO_ROOT / "var"
    demo_cases_dir: Path = REPO_ROOT / "data" / "synthetic_cases"
    llm_cache_dir: Path = REPO_ROOT / "data" / "llm_cache"
    render_dpi: int = 200
    max_upload_mb: int = 25
    max_pages_per_doc: int = 20
    low_ocr_confidence: float = 0.55
    rate_limit_per_minute: int = 120
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    audit_tamper_demo: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_path(self) -> Path:
        return self.data_dir / "docuforensic.sqlite3"

    def keys_for(self, provider: str) -> list[str]:
        raw = getattr(self, f"{provider}_api_keys", "")
        return _split(raw)

    def chain(self) -> list[str]:
        return _split(self.llm_chain)

    def cors_list(self) -> list[str]:
        return _split(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()

__all__ = ["REPO_ROOT", "Field", "Settings", "get_settings", "mask", "settings"]
