from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import SecretStr, Field, AliasChoices, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINN_", env_file=".env", extra="ignore", hide_input_in_errors=True)
    llm_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("HYDE_INFERENCE_API_KEY", "FINN_LLM_API_KEY"))
    llm_model: str = Field(default="", validation_alias=AliasChoices("HYDE_MODEL", "FINN_LLM_MODEL"))
    llm_base_url: str = Field(default="https://api.openai.com/v1", validation_alias=AliasChoices("HYDE_BASE_URL", "FINN_LLM_BASE_URL"))
    auto_refresh_enabled: bool = True
    source_refresh_seconds: int = Field(default=300, ge=300)
    primary_catalog_path: Path | None = None
    reviewed_primary_hosts: list[str] = []
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    ingest_token: SecretStr | None = None
    access_mode: Literal['local', 'reviewer'] = 'local'
    reviewer_token: SecretStr | None = None
    bootstrap_enabled: bool = False
    ephemeral_storage: bool = False
    storage_backend: Literal['local', 'supabase'] = 'local'
    storage_url: str = ''
    storage_bucket: str = 'finn-private'
    storage_key: SecretStr | None = None

    @model_validator(mode='after')
    def deployment_boundary(self):
        if self.access_mode == 'reviewer':
            if not self.reviewer_token or len(self.reviewer_token.get_secret_value()) < 32:
                raise ValueError('Reviewer mode requires FINN_REVIEWER_TOKEN with at least 32 characters')
            if not self.cors_origins or any(o == '*' for o in self.cors_origins):
                raise ValueError('Reviewer mode requires explicit frontend CORS origins')
        if not self.database_url.startswith(('sqlite:', 'postgresql+psycopg:')):
            raise ValueError('Use SQLite locally or postgresql+psycopg for deployment')
        if self.storage_backend == 'supabase':
            from urllib.parse import urlsplit
            import re
            parts = urlsplit(self.storage_url)
            if parts.scheme != 'https' or not (parts.hostname or '').endswith('.supabase.co') or parts.username or parts.password or parts.query or parts.fragment or parts.path not in {'', '/'}:
                raise ValueError('Use the HTTPS Supabase project URL without a path or credentials')
            if not re.fullmatch(r'[a-z0-9-]{1,63}', self.storage_bucket) or not self.storage_key:
                raise ValueError('Private storage requires a bucket name and server-side storage key')
        if self.access_mode == 'reviewer' and (not self.database_url.startswith('postgresql+psycopg:') or self.storage_backend != 'supabase') and not self.ephemeral_storage:
            raise ValueError('Durable reviewer deployment requires Postgres and private object storage')
        return self
    @field_validator("llm_base_url")
    @classmethod
    def safe_llm_url(cls, value: str):
        from urllib.parse import urlsplit
        parts = urlsplit(value)
        local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname or (parts.scheme != "https" and not (local and parts.scheme == "http")):
            raise ValueError("Use a credential-free HTTPS provider base URL, or a local HTTP model server")
        return value.rstrip("/")

    database_url: str = Field(default="sqlite:///./finn.db", repr=False)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

@lru_cache
def get_settings() -> Settings:
    return Settings()
