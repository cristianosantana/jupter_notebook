from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict  # pyright: ignore[reportMissingImports]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = ""

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
