"""
Configuration settings for BimBot AI Wall backend.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://bimbot_user:bimbot_password@bimbot_postgres:5432/bimbot_ai_wall"
    
    # Redis
    redis_url: str = "redis://bimbot_redis:6379/0"
    
    # Application
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "your-secret-key-here"
    
    # File Storage
    upload_dir: str = "/app/uploads"
    artifacts_dir: str = "/app/artifacts"
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    
    # Worker
    worker_concurrency: int = 4
    job_timeout: int = 3600  # 1 hour
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

# Ensure directories exist
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.artifacts_dir, exist_ok=True)