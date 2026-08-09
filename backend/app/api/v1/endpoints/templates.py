from typing import Annotated

from fastapi import APIRouter, Form, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.services.storage_service import StorageError, storage_service
from app.crud.template_crud import create_template
from app.schemas.template import TemplateCreate, TemplateResponse
from app.models.template import Template

router = APIRouter()

ALLOWED_CATEGORIES = {
    "notice", "mom", "report", "application",
    "letter", "certificate", "proposal", "invoice", "custom",
}
ALLOWED_VISIBILITY = {"private", "public", "organization", "department", "group"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_template(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str | None = Form(default=None),
    category: str = Form(...),
    visibility: str = Form(...),
) -> Template:
    # 1. Validate file type
    filename = file.filename or "template.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX files are accepted")

    # 2. Read + empty check
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # 3. File size check
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds the 10 MB limit")

    # 4. Validate name
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Template name is required")
    if len(clean_name) > 100:
        raise HTTPException(status_code=400, detail="Template name must be 100 characters or fewer")

    # 5. Validate category
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=400, 
            detail="Invalid category. Allowed: notice, mom, report, application, letter, certificate, proposal, invoice, custom"
        )

    # 6. Validate visibility
    if visibility not in ALLOWED_VISIBILITY:
        raise HTTPException(status_code=400, detail="Invalid visibility value")

    # 7. Save file via storage_service
    try:
        stored = storage_service.save_bytes("templates_original", filename, content)
    except StorageError:
        raise HTTPException(
            status_code=500,
            detail="Could not save uploaded file",
        ) from None

    # 8. Insert DB record via create_template
    template_data = TemplateCreate(
        name=clean_name,
        description=description,
        category=category,
        visibility=visibility,
        original_file_path=stored.path,
        original_filename=filename,
        file_size_bytes=stored.size_bytes,
        file_extension=".docx",
        uploaded_by=current_user.id,
    )

    try:
        template = create_template(db, template_data)
    except Exception:
        storage_service.delete_file(stored.path)
        raise HTTPException(status_code=500, detail="Could not save template record") from None

    return template
