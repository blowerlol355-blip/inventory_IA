import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    doc_type: str | None
    status: str
    error: str | None
    page_count: int | None
    created_at: datetime
    updated_at: datetime


class FileUrlOut(BaseModel):
    url: str
    expires_in: int
