"""
Application configuration using environment variables.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./tribute.db"

    # Tribute API
    TRIBUTE_API_KEY: str = ""

    # Application
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

