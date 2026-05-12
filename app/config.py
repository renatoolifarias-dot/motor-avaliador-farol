"""Configurações da aplicação — Pydantic Settings (lê de .env)."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Geral
    app_name: str = "Avaliador Farol Público"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me"
    session_secret: str = "change-me-too"

    # Banco
    database_url: str = "sqlite+aiosqlite:///./farol.db"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model_default: str = "claude-haiku-4-5-20251001"

    # Crawler
    crawler_timeout_s: int = 30
    crawler_pages_per_url_max: int = 8
    crawler_total_pages_max: int = 120
    crawler_download_pdf: bool = True
    crawler_user_agent: str = "Farol-Publico-Avaliador/1.0"

    # Portal Locaweb (FTP)
    portal_ftp_host: str = ""
    portal_ftp_port: int = 21
    portal_ftp_user: str = ""
    portal_ftp_pass: str = ""
    portal_ftp_remote_dir: str = "/web/farolpublico/relatorios-2026"

    # SMTP (opcional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
