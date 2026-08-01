"""Read-only Google Drive access, used by the payment-notice card builder.

Separate from app/sheets/client.py on purpose: same service account, different
scope and a very different job (binary files, not cell values).

Images are streamed straight into memory: `list_images` gives the filenames a
caller needs for matching, and `open_image` fetches only the ones it actually
draws. Nothing is written to disk — mirroring a season locally meant ~170 MB
per season to use about five of the files.

Why this rather than mounting the Drive into the container: the VM has no Drive
mount and never will, so a mounted path could only ever work on one laptop.
The service account can read the shared drive from anywhere.
"""
import io
import logging
import threading
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.config import settings

logger = logging.getLogger(__name__)

# Read-only: this account is a viewer on the company drive and nothing here
# should ever need more than that.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

_lock = threading.Lock()
_service: Any = None


def _client() -> Any:
    global _service
    with _lock:
        if _service is None:
            logger.info("Connecting to Google Drive (service account)")
            creds = Credentials.from_service_account_file(
                settings.google_credentials_path, scopes=SCOPES
            )
            _service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return _service


def _shared_drive_id() -> str:
    """Id of the shared drive holding the image library.

    Looked up by name so the id doesn't have to be configured, and cached for
    the process lifetime — shared drives don't come and go.
    """
    global _drive_id
    if _drive_id:
        return _drive_id
    wanted = settings.drive_shared_drive_name
    for d in _client().drives().list(pageSize=100, fields="drives(id,name)").execute().get(
        "drives", []
    ):
        if d["name"] == wanted:
            _drive_id = d["id"]
            return _drive_id
    raise RuntimeError(
        f"Service account cannot see a shared drive named {wanted!r}. "
        "Share it with the account's client_email as a Viewer."
    )


_drive_id: str | None = None


def _query(q: str, fields: str = "files(id,name,mimeType,size)") -> list[dict]:
    """List files matching a Drive query, scoped to the shared drive.

    The four extra arguments are not optional decoration: without
    corpora/driveId/includeItemsFromAllDrives/supportsAllDrives the API happily
    returns an EMPTY LIST for shared-drive content instead of an error, which
    looks exactly like "the folder doesn't exist".
    """
    return (
        _client()
        .files()
        .list(
            q=q,
            corpora="drive",
            driveId=_shared_drive_id(),
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields=fields,
            pageSize=1000,
        )
        .execute()
        .get("files", [])
    )


def _folders_named(name: str, parent_id: str | None) -> list[str]:
    """Ids of every folder called `name`, optionally inside `parent_id`."""
    q = (
        f"name = '{name.replace(chr(39), chr(92) + chr(39))}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    if parent_id:
        q += f" and '{parent_id}' in parents"
    return [f["id"] for f in _query(q, fields="files(id,name)")]


def resolve_folder(path: str) -> str:
    """'PPIC/CC OC Salesforce/LIBRARY MODEL IMAGE/S27' -> that folder's id.

    Walks every branch rather than taking the first match per segment. Folder
    names repeat all over a company drive — there are four folders called
    'PPIC' in this one — so committing to the first hit picks the wrong branch
    and then fails on the NEXT segment, which reads as "that folder doesn't
    exist" when really it was looked for in the wrong place.

    Keeping all candidates lets the path itself disambiguate: only one 'PPIC'
    contains a 'CC OC Salesforce', so the ambiguity resolves as we descend.
    """
    segments = [p.strip() for p in path.split("/") if p.strip()]
    if not segments:
        raise ValueError("resolve_folder needs a non-empty path")

    candidates: list[str | None] = [None]  # None = the shared drive root
    for depth, segment in enumerate(segments):
        found: list[str] = []
        for parent in candidates:
            found.extend(_folders_named(segment, parent))
        if not found:
            trail = "/".join(segments[:depth]) or "the shared drive"
            raise FileNotFoundError(f"No Drive folder named {segment!r} under {trail}")
        candidates = found  # type: ignore[assignment]

    if len(candidates) > 1:
        logger.warning(
            "Drive path %r matches %d folders; using the first. "
            "Add a segment to disambiguate.", path, len(candidates)
        )
    return candidates[0]  # type: ignore[return-value]


# {drive path: {filename: file id}} for the process lifetime. Listings are
# metadata only (a few KB) and the image libraries don't change mid-session.
_folder_index_cache: dict[str, dict[str, str]] = {}

IMAGE_EXTS = (".jpeg", ".jpg", ".png")


def folder_index(path: str) -> dict[str, str]:
    """{filename: file id} for one Drive folder. No file contents are fetched.

    This is the cheap half of Drive access, and the half the card builder
    actually needs in bulk: it matches a style against ~250 FILENAMES but only
    ever opens the two or three that match. Listing everything and downloading
    nothing keeps that asymmetry.
    """
    if path not in _folder_index_cache:
        files = _query(f"'{resolve_folder(path)}' in parents and trashed = false")
        _folder_index_cache[path] = {
            f["name"]: f["id"]
            for f in files
            if not f.get("mimeType", "").endswith(".folder")
        }
        logger.info("Drive listing %s: %d file(s)", path, len(_folder_index_cache[path]))
    return _folder_index_cache[path]


def list_images(path: str) -> list[str]:
    """Image filenames in a Drive folder, sorted.

    Extension test is case-insensitive on purpose: the library mixes '.jpg' and
    '.JPG', and on Linux a case-sensitive match silently drops half the photos.
    """
    return sorted(n for n in folder_index(path) if n.lower().endswith(IMAGE_EXTS))


def open_image(path: str, filename: str) -> io.BytesIO:
    """Download one file into memory, ready for PIL.Image.open.

    Nothing is written to disk. A card opens a handful of photos, so streaming
    them costs a few seconds and no storage — as opposed to mirroring a whole
    season (~170 MB) to use five of the files.
    """
    file_id = folder_index(path).get(filename)
    if file_id is None:
        raise FileNotFoundError(f"{filename!r} is not in Drive folder {path!r}")
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(
        buf, _client().files().get_media(fileId=file_id, supportsAllDrives=True)
    )
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    buf.seek(0)
    return buf
