
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Knowledge Base API"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://postgres:CHANGE_ME@localhost:5434/knowledge_base"
    )

    auth_secret_key: str = "CHANGE_ME_USE_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
