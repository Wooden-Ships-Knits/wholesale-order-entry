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

    # Ship windows come from a Google Sheet: one worksheet per season code,
    # read live via a service account (share the sheet with its client_email).
    shipping_window_sheet_id: str = ""
    google_credentials_path: str = "credentials/dialy-report-automation-e20c53e67542.json"

    pdf_output_dir: str = "/output/orders"

    # Nearby-stockist conflict check. Server-side Google key (Distance Matrix)
    # — NOT the browser key in frontend/.env; IP-restrict it. Empty = the
    # endpoint degrades to straight-line distances.
    google_maps_server_api_key: str = ""
    conflict_max_minutes: int = 20
    # Only accounts with a sales order in the last N years count as stockists.
    conflict_order_years: int = 3

    # Admin monitoring page (/admin). Generate the hash with:
    #   docker compose exec backend python -m app.admin.security "your-password"
    # Empty hash disables sign-in entirely (no admin access).
    admin_password_hash: str = ""
    # Signs the admin session cookie. Rotating it logs everyone out.
    session_secret: str = ""
    # Set false only for local http dev; cookies are Secure in production.
    session_cookie_secure: bool = True


settings = Settings()
