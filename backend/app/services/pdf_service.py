"""
DOCX -> PDF conversion (V1.6 Phase 2) behind a small converter interface.

get_pdf_converter() picks the backend from settings (PDF_CONVERTER):
- "auto" (default): Gotenberg when GOTENBERG_URL is set; otherwise a local
  LibreOffice when LIBREOFFICE_PATH is set or soffice/libreoffice is on PATH;
  otherwise None ("not configured").
- "gotenberg" / "libreoffice": that backend only (None if it is unusable).
- "none": PDF conversion off.

A converter raises PdfConversionError on any failure (HTTP error, timeout,
non-zero exit, no output). Callers treat that as a PDF failure only; it must
never fail DOCX generation.
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


class GotenbergConverter:
    """POST the DOCX to Gotenberg's LibreOffice route."""

    name = "gotenberg"

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.endpoint = f"{base_url.rstrip('/')}/forms/libreoffice/convert"
        self.timeout_seconds = timeout_seconds

    def convert(self, docx_bytes: bytes, filename: str) -> bytes:
        try:
            response = httpx.post(
                self.endpoint,
                files={"files": (filename, docx_bytes, DOCX_MEDIA_TYPE)},
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException:
            logger.warning("Gotenberg timed out after %ss", self.timeout_seconds)
            raise PdfConversionError(
                f"The PDF service timed out after {self.timeout_seconds:g} seconds"
            ) from None
        except httpx.HTTPError as exc:
            logger.warning("Gotenberg request failed: %s", exc)
            raise PdfConversionError("The PDF service could not be reached") from None
        if response.status_code != 200:
            logger.warning(
                "Gotenberg returned %s: %s", response.status_code, response.text[:300]
            )
            raise PdfConversionError(
                f"The PDF service returned HTTP {response.status_code}"
            )
        return _check_pdf(response.content, "The PDF service")


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


def get_pdf_converter() -> PdfConverter | None:
    """The configured converter, or None when PDF conversion is not set up."""
    mode = (settings.pdf_converter or "auto").strip().lower()
    if mode == "none":
        return None
    gotenberg_url = (settings.gotenberg_url or "").strip()
    if mode in ("auto", "gotenberg") and gotenberg_url:
        return GotenbergConverter(gotenberg_url, settings.gotenberg_timeout_seconds)
    if mode in ("auto", "libreoffice"):
        binary = find_libreoffice()
        if binary:
            return LibreOfficeConverter(binary, settings.libreoffice_timeout_seconds)
    return None


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
    converter = get_pdf_converter()
    if converter is None:
        return {"converter": None, "ok": False, "message": _NOT_CONFIGURED_HINT}
    if isinstance(converter, GotenbergConverter):
        health_url = converter.endpoint.removesuffix("/forms/libreoffice/convert") + "/health"
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
