import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, HttpUrl, SecretStr, UrlConstraints
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

CustomMongoDsn = Annotated[
    MultiHostUrl,
    UrlConstraints(allowed_schemes=["mongodb", "mongodb+srv"]),
]
APP_HOME = os.environ.get("APP_HOME")


class AppConfig(BaseModel):
    """Application configurations"""

    BASE_DIR: Path = Path(__file__).resolve().parent

    SETTINGS_DIR: Path = BASE_DIR.joinpath("settings")
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


class GlobalConfig(BaseSettings):
    """Global configurations"""

    APP_CONFIG: AppConfig = AppConfig()

    ENV_STATE: str = Field("dev", env="ENV_STATE")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    HOST: str = Field("0.0.0.0", env="HOST")  # noqa: S104
    PORT: int = Field(8888, env="PORT")
    UVICORN_WORKERS: int = Field(1, env="UVICORN_WORKERS")
    DEFAULT_CONFIG_FILENAME: str = Field("default_config.yaml", env="DEFAULT_CONFIG_FILENAME")

    # Config Authentication
    AUTH_SECRET_KEY: str = Field(env="AUTH_SECRET_KEY")  # openssl rand -hex 32
    AUTH_ALGORITHM: str = Field("HS256", env="AUTH_ALGORITHM")
    AUTH_ACCESS_TOKEN_EXPIRE_HOURS: int = Field(24 * 1, env="AUTH_ACCESS_TOKEN_EXPIRE_HOURS")  # 1 days
    AUTH_REFRESH_TOKEN_EXPIRE_HOURS: int = Field(24 * 3, env="AUTH_ACCESS_TOKEN_EXPIRE_HOURS")  # 3 days
    ENCRYPTION_KEY: SecretStr | None = Field(None, env="ENCRYPTION_KEY")

    # Define API key for thirty party services
    GOOGLE_API_KEY: SecretStr | None = Field(None, env="GOOGLE_API_KEY")
    OPENAI_API_KEY: SecretStr | None = Field(None, env="OPENAI_API_KEY")

    # Define key parameter for Azure OpenAI
    AZURE_OPENAI_API_KEY: SecretStr | None = Field(None, env="AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_ENDPOINT: HttpUrl | None = Field(None, env="AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME: str | None = Field(None, env="AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME")
    AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT_NAME: str | None = Field(None, env="AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT_NAME")
    AZURE_LLM_API_VERSION: str | None = Field(None, env="AZURE_LLM_API_VERSION")

    MONGODB_DSN: CustomMongoDsn | None = Field(None, env="MONGODB_DSN")
    MONGODB_DATABASE_NAME: str = Field("agentic-document-intelligence", env="MONGODB_DATABASE_NAME")

    MINIO_ENDPOINT: str = Field("MINIO_ENDPOINT", env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: SecretStr | None = Field("MINIO_ACCESS_KEY", env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: SecretStr | None = Field("MINIO_SECRET_KEY", env="MINIO_SECRET_KEY")

    PRESIGN_URL_EXPIRATION: int = Field(86400, env="PRESIGN_URL_EXPIRATION")

    # Redis Configuration
    REDIS_HOST: str = Field(None, env="REDIS_HOST")
    REDIS_PORT: int = Field(6379, env="REDIS_PORT")
    REDIS_DB: int = Field(0, env="REDIS_DB")
    REDIS_PASSWORD: SecretStr | None = Field(None, env="REDIS_PASSWORD")

    # MINDSDB
    ENABLE_KNOWNLEDEGE_BASE: bool = Field(False, env="ENABLE_KNOWNLEDEGE_BASE")
    MINDSDB_API_URL: str = Field(None, env="MINDSDB_API_URL")
    MINDSDB_API_KEY: SecretStr | None = Field(None, env="MINDSDB_API_KEY")
    MINDSDB_LOGIN: str = Field("user", env="MINDSDB_LOGIN")
    MINDSDB_PASSWORD: SecretStr | None = Field("password", env="MINDSDB_PASSWORD")

    # PGVECTOR Configuration
    PGVECTOR_HOST: str = Field("localhost", env="PGVECTOR_HOST")
    PGVECTOR_PORT: int = Field(5432, env="PGVECTOR_PORT")
    PGVECTOR_DATABASE: str = Field("dims_vector_db", env="PGVECTOR_DATABASE")
    PGVECTOR_USERNAME: str = Field("postgres", env="PGVECTOR_USERNAME")
    PGVECTOR_PASSWORD: SecretStr | None = Field(None, env="PGVECTOR_PASSWORD")
    PGVECTOR_SCHEMA: str = Field("public", env="PGVECTOR_SCHEMA")
    PGVECTOR_SSL_MODE: str = Field("prefer", env="PGVECTOR_SSL_MODE")

    LICENSE_KEY: SecretStr | None = Field(None, env="LICENSE_KEY")
    VALIDATION_LICENSE_ENDPOINT: str | None = Field(None, env="VALIDATION_LICENSE_ENDPOINT")
    LICENSE_ENCRYPTION_KEY: SecretStr | None = Field(None, env="LICENSE_ENCRYPTION_KEY")
    CUSTOMER_ID: SecretStr | None = Field(None, env="CUSTOMER_ID")

    # Email Configuration
    MAIL_USERNAME: str | None = Field(None, env="MAIL_USERNAME")
    MAIL_PASSWORD: SecretStr | None = Field(None, env="MAIL_PASSWORD")
    MAIL_FROM: str | None = Field(None, env="MAIL_FROM")

    # License configuration
    LICENSE_GRACE_PERIOD_DAYS: int = Field(30, env="LICENSE_GRACE_PERIOD_DAYS")

    # Audit logging configuration
    AUDIT_IGNORE_GET_METHODS: bool = Field(True, env="AUDIT_IGNORE_GET_METHODS")

    BANNED_IPS: list[str] = Field(env="BANNED_IPS", default_factory=list)

    model_config = SettingsConfigDict(
        env_file=Path(APP_HOME) / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def pgvector_dsn(self) -> str:
        """Generate PostgreSQL connection string for pgvector"""
        password = self.PGVECTOR_PASSWORD.get_secret_value() if self.PGVECTOR_PASSWORD else ""

        return (
            f"postgresql+asyncpg://{self.PGVECTOR_USERNAME}:{password}@"
            f"{self.PGVECTOR_HOST}:{self.PGVECTOR_PORT}/"
            f"{self.PGVECTOR_DATABASE}"
        )


@lru_cache
def get_settings() -> tuple[GlobalConfig, dict] | None:
    def read_config_from_file(config_filename: str) -> dict:
        conf_path = Path(__file__).joinpath(settings_.APP_CONFIG.SETTINGS_DIR, config_filename)
        with Path.open(conf_path, encoding="utf-8") as file:
            return yaml.safe_load(file)
        return None

    settings_ = GlobalConfig()
    default_configs_ = read_config_from_file(settings_.DEFAULT_CONFIG_FILENAME)
    return settings_, default_configs_


settings, default_configs = get_settings()
