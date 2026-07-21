from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser
from app.schemas.storage import StoredFileRead
from app.services.storage_service import (
    LocalStorageService,
    StorageError,
    storage_service,
)

router = APIRouter()


def get_storage_service() -> LocalStorageService:
    return storage_service


StorageService = Annotated[LocalStorageService, Depends(get_storage_service)]


@router.post(
    "/templates/original",
    response_model=StoredFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_original_template(
    current_user: CurrentUser,
    service: StorageService,
    file: UploadFile = File(...),
) -> StoredFileRead:
    filename = file.filename or "template.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX files can be uploaded")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        stored_file = service.save_bytes("templates_original", filename, content)
    except StorageError:
        raise HTTPException(
            status_code=500,
            detail="Could not save uploaded file",
        ) from None

    return StoredFileRead(
        path=stored_file.path,
        filename=stored_file.filename,
        size_bytes=stored_file.size_bytes,
        content_type=file.content_type,
    )
