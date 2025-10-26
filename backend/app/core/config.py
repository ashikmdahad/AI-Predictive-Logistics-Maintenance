from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DB_URI: str = "sqlite:///./app.db"
    ALERT_PROB_THRESHOLD: float = 0.6
    ALERT_TEMPERATURE_MAX: float = 80.0
    CORS_ORIGINS: str = "http://localhost:5173"
    # AI provider configuration
    MODEL_PROVIDER: str = "local"  # options: local | external | google
    EXTERNAL_MODEL_URL: str = ""
    EXTERNAL_MODEL_API_KEY: str = ""
    EXTERNAL_TIMEOUT_SECONDS: float = 8.0
    GOOGLE_GENAI_API_KEY: str = ""
    GOOGLE_GENAI_MODEL: str = "gemini-1.5-flash"
    CMMS_WEBHOOK_URL: str = ""
    CMMS_WEBHOOK_TOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).resolve().parents[2] / ".env",
            Path(".env"),
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
