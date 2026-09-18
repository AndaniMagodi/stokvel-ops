from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Stokvel Ledger"
    app_env: str = "dev"
    database_url: str
    test_database_url: str | None = None
    default_currency: str = "ZAR"
    openai_api_key: str | None = None
    openai_proof_model: str = "gpt-4.1-mini"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
