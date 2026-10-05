from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TOKEN: str
    BACKEND_URL: str = "http://127.0.0.1:8000"
    BOT_API_TOKEN: str
    NOTIFICATION_POLL_SECONDS: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
