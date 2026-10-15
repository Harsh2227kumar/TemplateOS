"""
DOCX -> PDF conversion (V1.6 Phase 2) behind a small converter interface.

get_pdf_converter() picks the backend from settings. PDF_CONVERSION_ENABLED
(default true) is the kill switch; PDF_CONVERTER chooses the engine:
- "auto" (default): Gotenberg when GOTENBERG_URL is set; otherwise a local
  LibreOffice when LIBREOFFICE_PATH is set or soffice/libreoffice is on PATH;
  otherwise None (not set up).
- "gotenberg" / "libreoffice": that backend only (None if it is unusable).
- "none": PDF conversion off (same as PDF_CONVERSION_ENABLED=false).
unavailable_reason() is the user-readable reason recorded when there is no
converter.

A converter raises PdfConversionError on any failure (unreachable service,
timeout, HTTP error, a body that is not a PDF, non-zero exit). The message is
shown to users. Callers treat that as a PDF failure only; it must never fail
DOCX generation.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_PDF_MAGIC = b"%PDF"


class PdfConversionError(Exception):
    """PDF conversion failed; the message is safe to show to the user."""


class PdfConverter(Protocol):
    name: str

    def convert(self, docx_bytes: bytes, filename: str) -> bytes: ...


def _check_pdf(content: bytes, backend: str) -> bytes:
    if not content.startswith(_PDF_MAGIC):
        raise PdfConversionError(f"{backend} did not return a PDF file")
    return content


# Tests inject an httpx.MockTransport here; None means real network I/O.
gotenberg_transport: httpx.BaseTransport | None = None

GOTENBERG_CONNECT_TIMEOUT_SECONDS = 5.0


def _gotenberg_status_reason(status_code: int) -> str:
    if status_code == 400:
        return "The document could not be converted (the PDF service rejected the file)"
    if status_code == 503:
        return "PDF service is busy or timed out. Try again in a moment"
    if status_code >= 500:
        return f"PDF service error (HTTP {status_code}). Try again"
    return f"Unexpected PDF service response (HTTP {status_code})"


class GotenbergConverter:
    """POST the DOCX to Gotenberg's LibreOffice route."""

    name = "gotenberg"

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/forms/libreoffice/convert"
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def convert(self, docx_bytes: bytes, filename: str) -> bytes:
        # Gotenberg picks the LibreOffice import filter from the extension.
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=min(GOTENBERG_CONNECT_TIMEOUT_SECONDS, self.timeout_seconds),
        )
        try:
            with httpx.Client(transport=self.transport, timeout=timeout) as client:
                response = client.post(
                    self.endpoint,
                    files={"files": (filename, docx_bytes, DOCX_MEDIA_TYPE)},
                )
        except httpx.ConnectError:
            logger.warning("Gotenberg is not reachable at %s", self.base_url)
            raise PdfConversionError(
                f"PDF service is not reachable at {self.base_url}. Is Gotenberg running?"
            ) from None
        except httpx.TimeoutException:
            logger.warning("Gotenberg timed out after %ss", self.timeout_seconds)
            raise PdfConversionError(
                f"PDF conversion timed out after {self.timeout_seconds:.0f}s"
            ) from None
        except httpx.HTTPError as exc:
            logger.warning("Gotenberg request failed: %r", exc)
            raise PdfConversionError(
                f"PDF service request failed ({type(exc).__name__})"
            ) from None
        trace = response.headers.get("Gotenberg-Trace", "-")
        if response.status_code != 200:
            logger.error(
                "Gotenberg HTTP %s trace=%s body=%r",
                response.status_code,
                trace,
                response.text[:300],
            )
            raise PdfConversionError(_gotenberg_status_reason(response.status_code))
        if not response.content.startswith(_PDF_MAGIC):
            logger.error(
                "Gotenberg returned a non-PDF body trace=%s content-type=%s",
                trace,
                response.headers.get("Content-Type", "-"),
            )
            raise PdfConversionError("PDF service returned an invalid file")
        logger.info(
            "Gotenberg converted %s (%s bytes) trace=%s",
            filename,
            len(response.content),
            trace,
        )
        return response.content


class LibreOfficeConverter:
    """Run `soffice --headless --convert-to pdf` in a temporary directory."""

    name = "libreoffice"

    def __init__(self, binary: str, timeout_seconds: float) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def convert(self, docx_bytes: bytes, filename: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="templateos-pdf-") as tmp:
            workdir = Path(tmp)
            source = workdir / "document.docx"
            source.write_bytes(docx_bytes)
            # A private profile dir lets conversions run while a desktop
            # LibreOffice is open and keeps parallel conversions apart.
            profile = (workdir / "profile").as_uri()
            command = [
                self.binary,
                f"-env:UserInstallation={profile}",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(workdir),
                str(source),
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                logger.warning("LibreOffice timed out after %ss", self.timeout_seconds)
                raise PdfConversionError(
                    f"LibreOffice timed out after {self.timeout_seconds:g} seconds"
                ) from None
            except OSError as exc:
                logger.warning("LibreOffice could not be started: %s", exc)
                raise PdfConversionError("LibreOffice could not be started") from None
            output = workdir / "document.pdf"
            if completed.returncode != 0 or not output.is_file():
                logger.warning(
                    "LibreOffice failed (exit %s): %s",
                    completed.returncode,
                    (completed.stderr or b"")[:300],
                )
                raise PdfConversionError(
                    f"LibreOffice could not convert the document (exit {completed.returncode})"
                )
            return _check_pdf(output.read_bytes(), "LibreOffice")


def find_libreoffice() -> str | None:
    """LIBREOFFICE_PATH when it points at a file, else soffice/libreoffice on PATH."""
    configured = (settings.libreoffice_path or "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    for candidate in ("soffice", "libreoffice"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


DISABLED_ERROR = "PDF conversion is disabled on this server"
NOT_SET_UP_ERROR = (
    "PDF conversion is not set up on this server "
    "(set GOTENBERG_URL or install LibreOffice)"
)


def _converter_mode() -> str:
    return (settings.pdf_converter or "auto").strip().lower()


def conversion_disabled() -> bool:
    """PDF_CONVERSION_ENABLED=false or PDF_CONVERTER=none."""
    return not settings.pdf_conversion_enabled or _converter_mode() == "none"


def get_pdf_converter() -> PdfConverter | None:
    """The configured converter, or None when PDF conversion is off / not set up."""
    if conversion_disabled():
        return None
    mode = _converter_mode()
    gotenberg_url = (settings.gotenberg_url or "").strip()
    if mode in ("auto", "gotenberg") and gotenberg_url:
        return GotenbergConverter(
            gotenberg_url,
            settings.gotenberg_timeout_seconds,
            transport=gotenberg_transport,
        )
    if mode in ("auto", "libreoffice"):
        binary = find_libreoffice()
        if binary:
            return LibreOfficeConverter(binary, settings.libreoffice_timeout_seconds)
    return None


def unavailable_reason() -> str:
    """Why get_pdf_converter() returned None (recorded as pdf_error)."""
    return DISABLED_ERROR if conversion_disabled() else NOT_SET_UP_ERROR


_NOT_CONFIGURED_HINT = (
    "PDF conversion is not set up: set GOTENBERG_URL (e.g. http://localhost:3000) "
    "in the repository-root .env, or install LibreOffice, then restart the backend"
)


def check_pdf_setup() -> dict[str, str | bool | None]:
    """
    Which converter generation would use right now and whether it answers.
    For Gotenberg this calls its /health route (short timeout). Used by
    GET /system/pdf-check and the startup log; never raises.
    """
    if conversion_disabled():
        return {
            "converter": None,
            "ok": False,
            "message": f"{DISABLED_ERROR} (PDF_CONVERSION_ENABLED=false or PDF_CONVERTER=none)",
        }
    converter = get_pdf_converter()
    if converter is None:
        return {"converter": None, "ok": False, "message": _NOT_CONFIGURED_HINT}
    if isinstance(converter, GotenbergConverter):
        health_url = f"{converter.base_url}/health"
        try:
            response = httpx.get(health_url, timeout=5)
        except httpx.HTTPError as exc:
            return {
                "converter": "gotenberg",
                "ok": False,
                "message": f"Gotenberg is configured but not reachable ({exc.__class__.__name__}); "
                "is the container running and GOTENBERG_URL correct?",
            }
        if response.status_code != 200:
            return {
                "converter": "gotenberg",
                "ok": False,
                "message": f"Gotenberg health check returned HTTP {response.status_code}",
            }
        return {"converter": "gotenberg", "ok": True, "message": "Gotenberg is reachable"}
    return {"converter": converter.name, "ok": True, "message": "LibreOffice was found"}
