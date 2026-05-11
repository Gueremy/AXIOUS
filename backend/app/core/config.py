from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:5173"])

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7


settings = Settings()

