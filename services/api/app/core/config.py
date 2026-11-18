from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Meridian Analytics API"
    environment: str = "development"
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_secret_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_jwks_url: str | None = None
    supabase_jwt_secret: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    max_upload_bytes: int = 8_589_934_592
    max_kaggle_import_bytes: int = 53_687_091_200
    kaggle_temp_disk_factor: float = 1.5
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
