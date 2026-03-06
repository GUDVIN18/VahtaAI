from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # AVITO API
    AVITO_API_BASE_URL: str = Field(..., env="AVITO_API_BASE_URL")
    AVITO_API_KEY: str = Field(..., env="AVITO_API_KEY")
    AUTHORIZATION_TOKEN: str = Field(..., env="AUTHORIZATION_TOKEN")
    AVITO_USER_ID: int = Field(..., env="AVITO_USER_ID")
    AVITO_ITEM_IDS: list[int] = Field(..., env="AVITO_ITEM_IDS")

    # БД
    DB_HOST: str = Field("localhost", env="DB_HOST")
    DB_PORT: int = Field(5432, env="DB_PORT")
    DB_NAME: str = Field(..., env="DB_NAME")
    DB_USER: str = Field(..., env="DB_USER")
    DB_PASSWORD: str = Field(..., env="DB_PASSWORD")

    #AI & YANDEX
    QWEN_API_KEY: str = Field(..., env="QWEN_API_KEY")
    YANDEX_API_KEY: str = Field(..., env="YANDEX_API_KEY")
    FOLDER_LLM_YANDEX_ID: str = Field(..., env="FOLDER_LLM_YANDEX_ID")
    FOLDER_TTS_YANDEX_ID: str = Field(..., env="FOLDER_TTS_YANDEX_ID")
    YANDEX_SERVICE_ACCOUNT_API: str = Field(..., env="YANDEX_SERVICE_ACCOUNT_API")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


config = Settings()
