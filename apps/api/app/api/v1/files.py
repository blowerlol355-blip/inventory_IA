"""Archivos generados por el agente (conversiones, ZIP, versiones comprimidas)."""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, EditorUser
from app.core.errors import not_found
from app.models import GeneratedFile, User
from app.schemas.document import FileUrlOut
from app.services.files.service import file_url
from app.services.storage import Storage, StorageError, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

StorageDep = Annotated[Storage, Depends(get_storage)]


class GeneratedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    operation: str
    sources: list[dict[str, Any]]
    conversation_id: uuid.UUID | None
    created_at: datetime


async def _get_org_file(db: DbSession, user: User, file_id: uuid.UUID) -> GeneratedFile:
    item = await db.get(GeneratedFile, file_id)
    if item is None or item.organization_id != user.organization_id:
        raise not_found("Archivo")
    return item


@router.get("", response_model=list[GeneratedFileOut])
async def list_files(user: CurrentUser, db: DbSession) -> list[GeneratedFile]:
    rows = await db.scalars(
        select(GeneratedFile)
        .where(GeneratedFile.organization_id == user.organization_id)
        .order_by(GeneratedFile.created_at.desc())
    )
    return list(rows)


@router.get("/{file_id}/url", response_model=FileUrlOut)
async def get_file_url(
    file_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> FileUrlOut:
    item = await _get_org_file(db, user, file_id)
    return FileUrlOut(url=await file_url(storage, item), expires_in=settings.signed_url_seconds)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID, user: EditorUser, db: DbSession, storage: StorageDep
) -> None:
    item = await _get_org_file(db, user, file_id)
    await db.delete(item)
    await db.commit()
    try:
        await storage.delete(item.storage_key)
    except StorageError:
        logger.warning("No se pudo borrar %s del storage", item.storage_key, exc_info=True)
