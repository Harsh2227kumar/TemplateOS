from pydantic import BaseModel


class StoredFileRead(BaseModel):
    path: str
    filename: str
    size_bytes: int
    content_type: str | None = None
