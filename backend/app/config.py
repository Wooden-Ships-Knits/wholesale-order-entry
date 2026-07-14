from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8080
    cors_origin: str = "http://localhost"

    database_url: str = "postgresql+psycopg://woodenships:woodenships@db:5432/woodenships"

    salesforce_username: str = ""
    salesforce_password: str = ""
    salesforce_security_token: str = ""
    salesforce_domain: str = "login"
    # No price book id setting: wholesale price books are resolved per season
    # by name ("<season> Wholesale") — see app/salesforce/mapping.py.

    pdf_output_dir: str = "/output/orders"


settings = Settings()
