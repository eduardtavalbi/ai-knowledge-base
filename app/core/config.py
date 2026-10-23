from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "AI Knowledge Base API"
    debug: bool = True
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5434/knowledge_base"


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
