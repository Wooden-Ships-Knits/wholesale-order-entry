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

    # Region -> rep territory lookup: a Google Sheet whose first tab maps US
    # state codes to a territory label (columns: Territory | States | Rep).
    # Used to auto-assign a sales territory to NEW accounts from their Ship To
    # state (existing accounts carry SalesTerritory__c from the buyer lookup).
    region_rep_territories_sheet_id: str = ""

    pdf_output_dir: str = "/output/orders"

    # Encrypts the admin-copy order PDF (the only artefact showing the full card
    # number) while it waits for the monitoring team — see CLAUDE.md rule 1.
    # 32 random bytes, base64:
    #   python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
    # Blank = no admin copy is kept at all; the card is discarded at submit.
    card_encryption_key: str = ""
    # Admin copies are purged this many days after submit even if the order was
    # never accepted or declined, so cards never linger.
    card_retention_days: int = 14

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

    # Outbound email (order copies + admin notice). Gmail/Workspace SMTP.
    # Blank host/user/pass = mail disabled: the app logs a warning and skips
    # sending, orders still succeed. See app/email/mailer.py.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    mail_from: str = ""  # From address; falls back to smtp_user when blank
    admin_email: str = "wholesale@wooden-ships.com"

    # Inbound reply capture (conflict replies). IMAP over SSL to the same
    # wholesale@ mailbox. Blank host/user/pass = disabled: run_poll() no-ops.
    # Reps reply to a plus-addressed Reply-To (see app/email/reply_address.py),
    # so their reply lands here carrying the order id.
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_pass: str = ""
    imap_mailbox: str = "INBOX"

    # Conflict-reply classifier (OpenAI). Blank key = disabled: run_classify()
    # no-ops. The model only ever *suggests* a resolution; a human confirms it.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Admin reports (DTO / DMM). Salesforce reuses the connection above — these
    # are the only DTO-specific values (were hardcoded in the standalone script).
    dto_report_name: str = "Daily Total Order"  # Salesforce Report.Name to run
    dto_recap_recipient: str = "Paola"  # greeting name in the recap email

    # DMM (Daily Morning Meeting). Was hardcoded in the standalone script.
    dmm_report_name: str = "UNPAID DAILY MORNING MEETING"
    dmm_recap_recipient: str = "Paola"
    # Google Sheet behind the DMM report: the "WHOLESALE Paid Open Orders" tab
    # (today's shipping plan) and the "Email Schedule" tab (rep chase dates).
    problem_list_reps_sheet_id: str = ""

    @property
    def mail_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass)

    @property
    def mail_sender(self) -> str:
        return self.mail_from or self.smtp_user

    @property
    def imap_configured(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_pass)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
