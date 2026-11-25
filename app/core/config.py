
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Knowledge Base API"
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://postgres:CHANGE_ME@localhost:5434/knowledge_base"
    )

    auth_secret_key: str = "CHANGE_ME_USE_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS"
    refresh_token_cookie_secure: bool = False
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_public_url: str = "http://localhost:5173"
    email_verification_required: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False
    migration_owner_email: str = ""
    migration_owner_password: str = ""
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
