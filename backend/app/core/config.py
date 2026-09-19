from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "Multi-Hospital Post-Discharge Outreach Platform"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment & Database
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DATABASE_URL: str = Field(
        default="sqlite:///./healthcare_platform.db", 
        env="DATABASE_URL"
    )
    # Comma-separated origins, or * for any (Netlify + local)
    CORS_ORIGINS: str = Field(default="*", env="CORS_ORIGINS")
    
    # Authentication & JWT
    JWT_SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7", 
        env="JWT_SECRET_KEY"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours for prototype demo
    
    # Operational & Calling Defaults
    DEFAULT_CALLING_START_HOUR: int = 8  # 08:00
    DEFAULT_CALLING_END_HOUR: int = 20   # 20:00
    DEFAULT_MAX_RETRIES: int = 3
    DEFAULT_HOSPITAL_CAPACITY: int = 10
    
    # AI Engine Configuration
    AI_PROVIDER: str = Field(default="mock_local", env="AI_PROVIDER") # mock_local, openai, gemini
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    GEMINI_API_KEY: str = Field(default="", env="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", env="GEMINI_MODEL")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        # Render/Heroku provide postgres://; SQLAlchemy 2 needs postgresql+psycopg2://
        if value.startswith("postgres://"):
            value = "postgresql+psycopg2://" + value[len("postgres://"):]
        elif value.startswith("postgresql://") and "+psycopg2" not in value.split("://", 1)[0]:
            value = "postgresql+psycopg2://" + value[len("postgresql://"):]
        return value
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
