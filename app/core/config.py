from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    postgres_user: str = "kpi"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "kpi_command_center"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: SecretStr | None = None
    secret_key: SecretStr
    algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=45, ge=5, le=60)
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    low_cash_threshold: float = Field(default=20, ge=0, le=100)
    stale_after_minutes: int = Field(default=15, ge=1)
    login_max_attempts: int = Field(default=5, ge=1)
    login_lock_minutes: int = Field(default=15, ge=1)
    seed_admin_email: str = "admin@bank.com"
    seed_admin_password: SecretStr = SecretStr("admin123")
    google_maps_api_key: str = ""

    @model_validator(mode="after")
    def secure_configuration(self):
        key = self.secret_key.get_secret_value()
        if len(key) < 32 or key.startswith("replace-with-"):
            raise ValueError("SECRET_KEY debe ser aleatoria, con al menos 32 caracteres")
        if self.app_env == "production" and ("*" in self.cors_origins or "*" in self.trusted_hosts):
            raise ValueError("Producción requiere orígenes y hosts explícitos")
        return self

    @property
    def sqlalchemy_url(self) -> URL | str:
        if self.database_url:
            value = self.database_url.get_secret_value()
            if not value.startswith("postgresql"):
                raise ValueError("Se requiere PostgreSQL")
            return value
        return URL.create(
            "postgresql+psycopg2",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
