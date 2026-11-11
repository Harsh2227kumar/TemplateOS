from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import settings
from app.db.session import check_database_connection
from app.schemas.ai_fill import AiConfigRead
from app.services.pdf_service import check_pdf_setup

router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}


@router.get("/db-check")
def db_check() -> dict[str, str | bool]:
    is_connected, detail = check_database_connection()
    return {
        "ok": is_connected,
        "message": detail,
    }


@router.get("/pdf-check")
def pdf_check() -> dict[str, str | bool | None]:
    """Which PDF converter is configured and whether it answers right now."""
    return check_pdf_setup()


@router.get("/ai-config", response_model=AiConfigRead)
def ai_config(_current_user: CurrentUser) -> AiConfigRead:
    """Which AI features the UI may offer (V1.7 P2.2). No secrets, no network call."""
    enabled = settings.ai_is_configured
    return AiConfigRead(enabled=enabled, fill_enabled=enabled and bool(settings.fill_model))
