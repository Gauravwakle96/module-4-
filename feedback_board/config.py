from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["local", "cloud"] = "local"
    database_url: SecretStr | None = None
    database_sslmode: Literal["require", "disable"] = "require"
    local_db_path: Path = Path("feedback.sqlite3")
    allowed_hosts: str = "localhost,127.0.0.1"
    render_external_hostname: str = ""
    feedback_limit: int = Field(default=500, ge=1, le=5000)
    write_limit: int = Field(default=10, ge=1, le=100)

    @field_validator("database_url", mode="before")
    @classmethod
    def empty_database_url(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def require_cloud_database(self) -> Self:
        if self.environment == "cloud" and not self.database_url:
            raise ValueError("Cloud deployment requires DATABASE_URL; SQLite is local only.")
        if self.environment == "cloud" and self.database_sslmode != "require":
            raise ValueError("Cloud database connections require TLS.")
        if self.database_url and not self.database_url.get_secret_value().startswith(
            ("postgres://", "postgresql://")
        ):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")
        return self

    @property
    def hosts(self) -> list[str]:
        hosts = [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]
        if self.render_external_hostname:
            hosts.append(self.render_external_hostname)
        return hosts
