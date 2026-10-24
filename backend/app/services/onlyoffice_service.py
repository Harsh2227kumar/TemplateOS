"""
ONLYOFFICE Docs (Community Edition) integration - V1.7 Phase 2.1.

The Document Server is a separate container. The browser loads its editor
with a configuration the backend signs; the Document Server then talks to
the backend directly (no browser cookies):

- GET  {backend}/editor/files/{key}?token=...  fetches the file to open.
  `token` is an HMAC of the session key and its expiry (file_token).
- POST {backend}/editor/callback/{key}          reports edits; status 2/6
  carries the URL of the saved file on the Document Server. The payload is
  a JWT signed with the shared secret (verify_callback).

Security rules:
- every config is signed and every callback verified with
  ONLYOFFICE_JWT_SECRET (HS256 only); the secret never reaches the browser
- the edited file is downloaded only from the configured Document Server
  (scheme, host and port must match), through the internal URL, without
  redirects, with a size cap, and must be a real DOCX
"""

import base64
import calendar
import hashlib
import hmac
import io
import logging
import time
import zipfile
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import jwt

from app.core.config import settings
from app.models.editor_session import EditorSession
from app.models.user import User

logger = logging.getLogger(__name__)

# Test hook (like pdf_service.gotenberg_transport): an httpx transport for
# the Document Server download; None = real network.
document_server_transport: httpx.BaseTransport | None = None
DOWNLOAD_TIMEOUT_SECONDS = 30
JWT_LEEWAY_SECONDS = 60
# Callback statuses (ONLYOFFICE API "callbackUrl").
STATUS_EDITING = 1
STATUS_READY_FOR_SAVING = 2
STATUS_SAVE_ERROR = 3
STATUS_CLOSED_NO_CHANGES = 4
STATUS_FORCE_SAVE = 6
STATUS_FORCE_SAVE_ERROR = 7


class CallbackRejected(Exception):
    """The callback is not signed by our Document Server."""


class EditedFileRejected(Exception):
    """The saved file cannot be accepted; the message is user-facing."""


def editor_enabled() -> bool:
    return bool(
        settings.onlyoffice_enabled
        and settings.onlyoffice_public_base
        and settings.onlyoffice_jwt_secret
    )


def _secret() -> bytes:
    secret = settings.onlyoffice_jwt_secret
    if not secret:
        raise RuntimeError("ONLYOFFICE_JWT_SECRET is not set")
    return secret.encode("utf-8")


def backend_url(path: str) -> str:
    """An API URL the Document Server can reach (BACKEND_URL_FOR_ONLYOFFICE)."""
    return f"{settings.backend_url_for_onlyoffice.rstrip('/')}{settings.api_v1_prefix}{path}"


# ── File tokens ───────────────────────────────────────────────────


def _expiry(session: EditorSession) -> int:
    return calendar.timegm(session.expires_at.timetuple())


def _signature(key: str, expires: int) -> str:
    digest = hmac.new(_secret(), f"{key}:{expires}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def file_token(session: EditorSession) -> str:
    expires = _expiry(session)
    return f"{expires}.{_signature(session.session_key, expires)}"


def verify_file_token(session: EditorSession, token: str | None, now: int | None = None) -> bool:
    """The token was issued for this session and has not expired."""
    if not token or "." not in token:
        return False
    raw_expires, _, signature = token.partition(".")
    try:
        expires = int(raw_expires)
    except ValueError:
        return False
    if expires != _expiry(session):
        return False
    current = now if now is not None else calendar.timegm(time.gmtime())
    if expires < current:
        return False
    return hmac.compare_digest(signature, _signature(session.session_key, expires))


# ── Editor configuration ──────────────────────────────────────────


def build_config(session: EditorSession, *, title: str, user: User) -> dict[str, Any]:
    """The signed configuration the browser passes to DocsAPI.DocEditor unchanged."""
    key = session.session_key
    config: dict[str, Any] = {
        "document": {
            "fileType": "docx",
            "key": key,
            "title": title,
            "url": backend_url(f"/editor/files/{key}?token={file_token(session)}"),
            "permissions": {
                "edit": True,
                "download": True,
                "print": True,
                "comment": False,
                "review": False,
            },
        },
        "documentType": "word",
        "editorConfig": {
            "mode": "edit",
            "callbackUrl": backend_url(f"/editor/callback/{key}"),
            "lang": "en",
            "user": {"id": str(user.id), "name": user.full_name or user.email},
            "customization": {
                "autosave": True,
                "forcesave": False,
                "compactHeader": True,
                "help": False,
                "feedback": False,
                "chat": False,
                "comments": False,
            },
        },
    }
    config["token"] = jwt.encode(config, _secret(), algorithm="HS256")
    return config


# ── Callbacks ─────────────────────────────────────────────────────


def _decode(token: str) -> dict[str, Any]:
    try:
        decoded = jwt.decode(token, _secret(), algorithms=["HS256"], leeway=JWT_LEEWAY_SECONDS)
    except jwt.PyJWTError as exc:
        raise CallbackRejected(f"Invalid callback token: {exc}") from None
    if not isinstance(decoded, dict):
        raise CallbackRejected("Invalid callback token")
    return decoded


def verify_callback(body: dict[str, Any], authorization: str | None) -> dict[str, Any]:
    """
    The verified callback payload. ONLYOFFICE signs it either in the body
    ("token": JWT of the whole payload) or in "Authorization: Bearer <JWT>"
    (payload under "payload"). Unsigned callbacks are rejected.
    """
    token = body.get("token") if isinstance(body, dict) else None
    if isinstance(token, str) and token:
        return _decode(token)
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            decoded = _decode(credentials.strip())
            payload = decoded.get("payload", decoded)
            if isinstance(payload, dict):
                return payload
    raise CallbackRejected("The callback is not signed")


# ── Downloading the saved file ────────────────────────────────────


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port or {"http": 80, "https": 443}.get(scheme)
    return scheme, (parts.hostname or "").lower(), port


def internal_download_url(url: str) -> str:
    """
    The Document Server URL of a saved file, rewritten to the internal base.
    Raises EditedFileRejected for any other host (no SSRF).
    """
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        raise EditedFileRejected("The editor did not send a valid file address")
    allowed = {
        _origin(base)
        for base in (settings.onlyoffice_public_base, settings.onlyoffice_internal_base)
        if base
    }
    if _origin(url) not in allowed:
        raise EditedFileRejected("The saved file does not come from the document editor server")
    internal = urlsplit(settings.onlyoffice_internal_base or "")
    parts = urlsplit(url)
    return urlunsplit((internal.scheme, internal.netloc, parts.path, parts.query, ""))


def validate_docx(content: bytes) -> None:
    """A real Word document (zip with word/document.xml that python-docx opens)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if "word/document.xml" not in archive.namelist():
                raise EditedFileRejected("The saved file is not a Word document")
    except zipfile.BadZipFile:
        raise EditedFileRejected("The saved file is not a Word document") from None
    try:
        from docx import Document as DocxDocument

        DocxDocument(io.BytesIO(content))
    except Exception:
        raise EditedFileRejected("The saved Word document could not be opened") from None


def download_edited_file(url: str) -> bytes:
    """Fetch the saved DOCX from the Document Server (size-capped) and validate it."""
    target = internal_download_url(url)
    limit = settings.editor_max_file_mb * 1024 * 1024
    chunks: list[bytes] = []
    size = 0
    try:
        with httpx.Client(
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=document_server_transport,
        ) as client:
            with client.stream("GET", target) as response:
                if response.status_code != 200:
                    raise EditedFileRejected(
                        f"The document editor server answered {response.status_code} for the saved file"
                    )
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise EditedFileRejected(
                            f"The saved file is larger than {settings.editor_max_file_mb} MB"
                        )
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        logger.warning("Could not download the edited file from the Document Server: %s", exc)
        raise EditedFileRejected("The saved file could not be downloaded from the document editor server") from None
    content = b"".join(chunks)
    validate_docx(content)
    return content
