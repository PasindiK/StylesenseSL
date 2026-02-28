"""Global configuration settings for Data Fabric."""

import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # API Settings
    api_title: str = "Data Fabric API"
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", 8000))
    api_debug: bool = os.getenv("API_DEBUG", "False") == "True"

    # Database Settings
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://user:password@localhost:5432/data_fabric"
    )
    database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", 10))
    database_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", 20))

    # Logging Settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/app.log")
    loki_url: Optional[str] = os.getenv("LOKI_URL")

    # Storage Settings
    storage_bucket: str = os.getenv("STORAGE_BUCKET", "data-fabric")
    storage_region: str = os.getenv("STORAGE_REGION", "us-east-1")
    storage_access_key: Optional[str] = os.getenv("STORAGE_ACCESS_KEY")
    storage_secret_key: Optional[str] = os.getenv("STORAGE_SECRET_KEY")

    # ML Engine Settings
    ml_model_path: str = os.getenv("ML_MODEL_PATH", "./models")
    ml_batch_size: int = int(os.getenv("ML_BATCH_SIZE", 32))
    ml_epochs: int = int(os.getenv("ML_EPOCHS", 10))

    # Security Settings
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    # Environment
    environment: str = os.getenv("ENVIRONMENT", "development")

    class Config:
        """Pydantic config."""

        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
