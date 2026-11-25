
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from urllib.parse import urlsplit


class Settings(BaseSettings):
    app_name: str = "AI Knowledge Base API"
    environment: str = "development"
    security_audit_retention_days: int = Field(default=90, gt=0)
    debug: bool = False
    database_url: str = (
        "postgresql+asyncpg://postgres:CHANGE_ME@localhost:5434/knowledge_base"
    )

    auth_secret_key: str = "CHANGE_ME_USE_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS"
    refresh_token_cookie_secure: bool = False
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_public_url: str = "http://localhost:5173"
    email_verification_required: bool = False
    auth_login_ip_limit: int = Field(default=20, gt=0)
    auth_login_identity_limit: int = Field(default=8, gt=0)
    auth_login_window_seconds: int = Field(default=900, gt=0)
    auth_recovery_ip_limit: int = Field(default=20, gt=0)
    auth_recovery_identity_limit: int = Field(default=4, gt=0)
    auth_recovery_window_seconds: int = Field(default=3600, gt=0)
    auth_registration_ip_limit: int = Field(default=10, gt=0)
    auth_registration_window_seconds: int = Field(default=3600, gt=0)
    ai_ask_ip_limit: int = Field(default=60, gt=0)
    ai_ask_identity_limit: int = Field(default=20, gt=0)
    ai_ask_window_seconds: int = Field(default=60, gt=0)
    ai_search_ip_limit: int = Field(default=120, gt=0)
    ai_search_identity_limit: int = Field(default=60, gt=0)
    ai_search_window_seconds: int = Field(default=60, gt=0)
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

    @staticmethod
    def _is_secure_origin(value: str) -> bool:
        try:
            parsed = urlsplit(value)
            return (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            return False

    @model_validator(mode="after")
    def validate_runtime_configuration(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production")
        if self.smtp_starttls and self.smtp_use_ssl:
            raise ValueError("SMTP_STARTTLS and SMTP_USE_SSL cannot both be enabled")
        if self.environment == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if (
                len(self.auth_secret_key) < 32
                or self.auth_secret_key.strip() != self.auth_secret_key
                or self.auth_secret_key.casefold().startswith("change_me")
            ):
                raise ValueError("AUTH_SECRET_KEY must be a unique random secret of at least 32 characters in production")
            if not self.refresh_token_cookie_secure:
                raise ValueError("REFRESH_TOKEN_COOKIE_SECURE must be true in production")
            origins = [item.strip() for item in self.frontend_origins.split(",") if item.strip()]
            if not origins or any(not self._is_secure_origin(item) for item in origins):
                raise ValueError("FRONTEND_ORIGINS must contain valid HTTPS origins without paths in production")
            if not self._is_secure_origin(self.frontend_public_url):
                raise ValueError("FRONTEND_PUBLIC_URL must be a valid HTTPS origin in production")
            database_url = make_url(self.database_url)
            if (
                not database_url.drivername.startswith("postgresql")
                or not database_url.host
                or not database_url.username
                or not database_url.database
                or not database_url.password
                or "change_me" in database_url.password.casefold()
            ):
                raise ValueError("DATABASE_URL must use PostgreSQL with a host, database, username, and non-placeholder password in production")
            if self.email_verification_required:
                if not (self.smtp_host and self.smtp_from_email):
                    raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required when email verification is enabled in production")
                if self.smtp_username and not self.smtp_password:
                    raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is configured")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
