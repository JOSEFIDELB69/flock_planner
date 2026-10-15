"""Configuración de la aplicación, leída de variables de entorno (o de un archivo .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # El .env del backend tiene prioridad sobre el de la raíz; las variables de entorno, sobre ambos.
    model_config = SettingsConfigDict(env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"), extra="ignore")

    app_env: str = Field(default="development", description="development | test | production")
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    # PostgreSQL es el objetivo. SQLite solo se admite para desarrollo local y pruebas.
    database_url: str = "sqlite:///./pm_agent.db"

    # Proveedor de IA: claude_code (por defecto: CLI de Claude Code en modo headless) | demo (heurísticas locales,
    # resultados marcados como simulados) | none (IA deshabilitada; todo lo demás funciona en forma manual).
    ai_provider: str = "claude_code"
    claude_code_path: str | None = None  # si no se indica: PATH o la CLI incluida en la app de escritorio
    claude_code_model: str | None = None  # p. ej. "sonnet" u "opus"; vacío = modelo por defecto de la CLI
    claude_code_timeout_seconds: float = 300.0

    # Clave Fernet (base64 urlsafe de 32 bytes) para cifrar secretos de integraciones.
    secrets_encryption_key: str | None = None

    default_user: str = "Usuario local"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 1_000_000  # archivos de texto (.txt, .md, .csv)
    max_document_bytes: int = 10_000_000  # documentos Word (.docx) y PDF
    ai_rate_limit_per_minute: int = 20

    @field_validator("database_url")
    @classmethod
    def _resolve_sqlite(cls, v: str) -> str:
        """Rutas SQLite relativas se resuelven contra backend/ (independiente del directorio de trabajo)."""
        prefix = "sqlite:///"
        if v.startswith(prefix) and not v.startswith(prefix + "/") and ":" not in v[len(prefix):len(prefix) + 3]:
            return prefix + (BACKEND_DIR / v[len(prefix):]).resolve().as_posix()
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def resolved_ai_provider(self) -> str | None:
        p = (self.ai_provider or "").strip().lower()
        return p if p in ("claude_code", "demo") else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
