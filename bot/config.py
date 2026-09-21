from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TOKEN: str
    ADMIN_TG_ID: int = 0
    DATABASE_URL: str | None = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_DB: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    GIGACHAT_CREDENTIALS: str | None = None
    SBER_AUTHORIZATION_KEY: str | None = None
    SBER_SCOPE: str | None = None
    GIGACHAT_MODEL: str = "GigaChat"
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    REMINDER_MINUTES: int = 30
    TIMEZONE: str = "Europe/Moscow"


    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+asyncpg://", 1)
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url

        return (
            "postgresql+asyncpg://"
            f"{quote(self.POSTGRES_USER, safe='')}:{quote(self.POSTGRES_PASSWORD, safe='')}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def gigachat_credentials(self) -> str:
        credentials = self.SBER_AUTHORIZATION_KEY or self.GIGACHAT_CREDENTIALS
        if not credentials:
            raise ValueError("Укажите GIGACHAT_CREDENTIALS или SBER_AUTHORIZATION_KEY в .env")
        return credentials

    @property
    def gigachat_scope(self) -> str:
        return self.SBER_SCOPE or self.GIGACHAT_SCOPE


settings = Settings()
