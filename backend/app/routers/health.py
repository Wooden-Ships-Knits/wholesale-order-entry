from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Liveness, plus which environment this is.

    `dev` drives the banner the frontend shows on every page: the dev and
    production sites are identical to look at, and only one of them can email a
    real rep. It is derived from the safety switches rather than a label, so an
    environment cannot claim to be dev while still able to reach real people.
    """
    dev = settings.dev_mail_rewrite or settings.salesforce_readonly
    return {
        "status": "ok",
        "env": "development" if dev else "production",
        "dev": dev,
        # What is actually neutered, so the banner can say so.
        "mailRedirected": settings.dev_mail_rewrite,
        "salesforceReadonly": settings.salesforce_readonly,
    }
