from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.services.storage_service import storage_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure storage directories exist on startup
    storage_service.ensure_storage_tree()
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
    )

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_application()
