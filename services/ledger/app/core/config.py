from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Stokvel Ledger"
    app_env: str = "dev"
    database_url: str
    test_database_url: str | None = None
    default_currency: str = "ZAR"
    groq_api_key: str | None = None
    groq_proof_model: str = "qwen/qwen3.8-27b"
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_group_id: str | None = None
    whatsapp_graph_version: str = "v26.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
