from fastapi import APIRouter

from app.db.session import check_database_connection
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
