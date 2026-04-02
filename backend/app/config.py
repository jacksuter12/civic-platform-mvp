from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # Supabase Auth
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str  # Project Settings → API → JWT Secret

    # App
    APP_NAME: str = "Civic Power Consortium"
    DEBUG: bool = False
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # Observability
    SENTRY_DSN: str = ""

    # Feature flags
    SIMULATED_POOLS: bool = True  # MVP: all funding pools are simulated


settings = Settings()
