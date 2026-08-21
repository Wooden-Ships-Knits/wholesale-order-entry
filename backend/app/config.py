from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8080
    cors_origin: str = "http://localhost"

    # Public origin used to build links the buyer clicks (the signature link).
    # Defaults to cors_origin — in production both are the site's own origin —
    # so a deployment that already sets CORS_ORIGIN needs no new variable.
    public_base_url: str = ""
    # How long a signature link stays usable, and what the buyer's email
    # promises as an explicit date. Raised 7 -> 30 on 2026-08-06.
    #
    # Must not EXCEED card_retention_days: the order can't be accepted until it
    # is signed, and Accept is what keys the card into Salesforce — so a link
    # outliving the card copy would leave the team an acceptable order with no
    # card number to charge. At 30/30 the two run out together, which is the
    # tightest this may safely be; raise card_retention_days first if this ever
    # goes higher.
    signature_link_days: int = 36
    # Unsigned orders are chased automatically at these ages, counted from when
    # the first request was emailed. Empty list = no reminders.
    # 2 days, 5, 11, 16, 21, 26, 31 (set 2026-08-19). The last one is short of
    # signature_link_days on purpose: a threshold at or past the link's own
    # expiry can never fire, because the sweep refuses to chase a dead link
    # rather than mail the buyer a URL that 410s. Keep the final entry below
    # signature_link_days * 24 if either is ever changed.
    signature_reminder_hours: list[int] = [48, 120, 264, 384, 504, 624, 744]
    # Nudges to the REP when their order is still unsigned this many hours
    # after the request went out — days 6, 16 and 26. Empty list disables them.
    #
    # Day 6 is one day after the buyer's second chaser, when it is clear the
    # emails alone are not landing. Days 16 and 26 escalate, and carry DIFFERENT
    # wording (order_email.rep_chase_email) — by then the message is no longer
    # "email isn't working" but "we have asked you before".
    #
    # A list rather than one value, matching signature_reminder_hours: the
    # count of nudges already sent is the cursor, so adding a stage here starts
    # firing it for orders already past the earlier ones.
    rep_followup_hours: list[int] = [144, 384, 624]

    # The two notices the team sends itself at ADMIN_EMAIL — "New wholesale
    # order" and "Order signed". Off since 2026-08-06: every order is already
    # in /admin with its PDF, so these only doubled the inbox. A flag rather
    # than deleted code because this was paused once before (2026-07-23) and
    # switched back on the next day.
    #
    # Turning it off does NOT stop the team hearing about orders: MAIL_FROM is
    # wholesale@, so replies to the customer's order copy still land there.
    send_internal_notices: bool = False

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
    # never accepted or declined, so cards never linger. Raised 14 -> 30 on
    # 2026-08-06 to match signature_link_days — see the note there.
    card_retention_days: int = 36

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
    # Rep monitoring page (/reps) — ONE PASSWORD PER REP, as a JSON object of
    # normalized-name -> pbkdf2 hash. Not one shared password: sign-in is a rep
    # name plus a password, so a shared one would let any rep type a
    # colleague's name and read that colleague's book.
    # Build the value with:
    #   docker compose exec backend python -m app.reps_auth "Aviva Landin=..."
    # Empty (or malformed) disables rep sign-in entirely. Kept as a str and
    # parsed in app.reps_auth so a typo here cannot crash the whole app.
    reps_password_hashes: str = ""
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
    # DEV ONLY. Fake recipients, by role: a rep address goes to DEV_REP_EMAIL,
    # anyone else (the buyer) to DEV_BUYER_EMAIL. Keeping them apart preserves
    # the shape of production mail — buyer in To, rep in Cc — so a dev send is
    # worth reading. MAIL_REDIRECT_TO is the simpler catch-all: one inbox for
    # everything, used for any role left blank. ALL BLANK IN PRODUCTION.
    # See app/email/mailer.py.
    dev_buyer_email: str = ""
    dev_rep_email: str = ""
    mail_redirect_to: str = ""

    @property
    def dev_mail_rewrite(self) -> bool:
        """True when outbound mail must not reach its real recipients."""
        return bool(self.dev_buyer_email or self.dev_rep_email or self.mail_redirect_to)
    # DEV ONLY. Blocks the two Salesforce writes — creating an account and
    # pushing an accepted order into Kugamon. Reads (accounts, products,
    # territories, picklists) are unaffected, so a dev environment still shows
    # real customer data. See app/salesforce/client.py.
    salesforce_readonly: bool = False

    # Inbound reply capture (conflict replies). IMAP over SSL to the same
    # wholesale@ mailbox. Blank host/user/pass = disabled: run_poll() no-ops.
    # Reps reply to a plus-addressed Reply-To (see app/email/reply_address.py),
    # so their reply lands here carrying the order id.
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_pass: str = ""
    imap_mailbox: str = "INBOX"
    # How often the backend reads the mailbox by itself, in minutes.
    # 0 (the default) = ONLY when someone presses "Check replies".
    #
    # Off by default since 2026-08-12. wholesale@ is a mailbox people work in,
    # and reading a message marks it \Seen — an unattended login every few
    # minutes from a datacentre IP, quietly marking the team's mail as read,
    # looked like a compromised account and the password was reset. Turn this
    # on only for a mailbox nobody watches.
    # Also disabled automatically on a development instance, which shares the
    # same mailbox — see app/main.py::_mailbox_polling_enabled.
    poll_replies_minutes: int = 0

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
    
    # ---- Payment notice card builder (app/notices) ----
    # Images live on the company shared drive; the service account in
    # google_credentials_path is a Viewer there, so the same code works on the
    # VM (which has no Drive mount) as it does locally.
    drive_shared_drive_name: str = "PTIF SERVER"
    # Folder PATHS inside that drive, walked segment by segment. The season code
    # is appended at run time, e.g. ".../LIBRARY MODEL IMAGE" + "/S27".
    notice_style_images_dir: str = "PPIC/CC OC Salesforce/LIBRARY MODEL IMAGE"
    notice_swatch_images_dir: str = (
        "PPIC/AUTOMATION/Payment Notice 5/Payment Notice 5/thumbnails/swatch-color"
    )
    # Where synced Drive files are cached, and where finished cards are written.
    notice_cache_dir: str = "/output/notices/cache"
    notice_output_dir: str = "/output/notices"

settings = Settings()
