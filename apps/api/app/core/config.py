from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me-dev-secret-change-me"


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (o de .env en la raíz del repo)."""

    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"

    # Supabase Postgres. Usar la cadena del "Session pooler" (IPv4, puerto 5432).
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    # Esquema donde viven las tablas (los tests usan uno propio para no tocar los datos).
    db_schema: str = "public"

    # Supabase Storage (API REST). La secret key solo se usa en el servidor.
    supabase_url: str = ""
    supabase_secret_key: str = ""
    storage_bucket: str = "documents"
    signed_url_seconds: int = 300

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # gemini: Google Gemini (capa gratuita con clave de Google AI Studio). anthropic: Claude.
    llm_provider: Literal["gemini", "anthropic", "fake"] = "gemini"
    gemini_api_key: str | None = None
    # La capa gratuita da una cuota diaria pequeña por modelo: si uno se agota o está saturado
    # se usa el siguiente. Las tareas internas (clasificar, OCR) empiezan por modelos ligeros.
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = "gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview"
    gemini_task_models: str = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-lite-latest"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"
    llm_answer_effort: Literal["low", "medium", "high"] = "medium"

    # Cambiar de proveedor o modelo de embeddings exige reindexar (python -m app.scripts.reindex).
    embedding_provider: Literal["gemini", "voyage", "hash"] = "gemini"
    gemini_embedding_model: str = "gemini-embedding-001"
    voyage_api_key: str | None = None
    embedding_model: str = "voyage-4"
    embedding_dim: int = 1024

    # El worker de ingesta corre dentro del proceso de la API (un solo servicio que desplegar).
    # Con False se ejecuta aparte: python -m app.workers.main
    run_worker_in_api: bool = True
    worker_poll_seconds: float = 2.0
    # Documentos procesados a la vez por el worker.
    worker_concurrency: int = 3
    stale_processing_minutes: int = 15

    max_upload_mb: int = 20
    chunk_tokens: int = 500
    chunk_overlap_tokens: int = 50
    retrieval_top_k: int = 8
    history_messages: int = 6
    questions_per_minute: int = 30

    cors_origins: str = "http://localhost:3000"

    # Demo pública: con DEMO_OWNER_EMAIL, el botón "Probar demo" crea para cada visitante un
    # usuario viewer en la organización de ese email (documentos compartidos, chats propios).
    demo_owner_email: str | None = None
    # En la demo pública se cierra el registro para no agotar la cuota gratuita de la IA.
    allow_registration: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.app_env == "production" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET debe definirse en producción")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
