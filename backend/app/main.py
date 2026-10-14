import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.services.pdf_service import get_pdf_converter
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure storage directories exist on startup
    storage_service.ensure_storage_tree()
    # Say which PDF converter generation will use, so "PDF not set up" in the
    # UI can be traced to the .env without guessing. GET /system/pdf-check
    # also tests that the converter answers.
    converter = get_pdf_converter()
    if converter is None:
        logger.warning(
            "PDF conversion is NOT configured: set GOTENBERG_URL in the root .env "
            "or install LibreOffice; generated documents will be DOCX only"
        )
    else:
        logger.warning("PDF conversion uses %s", converter.name)
    yield


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # Middleware added last runs first: CORS wraps CSRF so a 403 from the
    # CSRF check still carries CORS headers the browser can read.
    application.add_middleware(CSRFMiddleware)
    application.add_middleware(
        CORSMiddleware,
        # Explicit origins only: credentialed CORS must never use "*".
        allow_origins=[origin for origin in settings.cors_origins if origin != "*"],
        # The browser session lives in httpOnly cookies, so cross-origin
        # requests from the frontend must be credentialed.
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        # Lets the frontend read the download filename of generated files.
        expose_headers=["Content-Disposition"],
    )

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_application()
