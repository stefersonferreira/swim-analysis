from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SWIM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://swim:swim@db:5432/swim"
    redis_url: str = "redis://redis:6379/0"
    data_dir: Path = Path("/data")
    static_dir: Path = Path("/app/static")
    # Em testes, as tarefas rodam no próprio processo, sem Redis.
    task_always_eager: bool = False
    # Recusa vídeos abaixo dos requisitos (fps, resolução, duração).
    strict_ingest: bool = True
    max_upload_mb: int = 2048
    # pedidos de clientes
    turnaround_hours: int = 72
    public_max_upload_mb: int = 400
    # senha da área do treinador; vazio = sem login (uso só no próprio computador)
    admin_password: str = ""
    # endereço público (ex.: https://analise.fluxiia.com) para montar os links de entrega
    public_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
