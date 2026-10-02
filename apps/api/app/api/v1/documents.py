import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import or_, select
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.deps import CurrentUser, DbSession, EditorUser
from app.core.errors import AppError, not_found
from app.models import Document, DocumentStatus, User
from app.schemas.document import DocumentOut, FileUrlOut
from app.services.ingestion.filetypes import detect_content_type
from app.services.storage import Storage, StorageError, get_storage
from app.workers.queue import TaskQueue, get_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

StorageDep = Annotated[Storage, Depends(get_storage)]
QueueDep = Annotated[TaskQueue, Depends(get_queue)]

STATUS_POLL_SECONDS = 1.5


def _safe_filename(name: str | None) -> str:
    base = (name or "documento").replace("\\", "/").split("/")[-1]
    return re.sub(r"[^\w.\- ]", "_", base)[:200] or "documento"


async def _get_org_document(db: DbSession, user: User, document_id: uuid.UUID) -> Document:
    doc = await db.get(Document, document_id)
    # Un documento de otra organización se trata como inexistente (no se revela que existe).
    if doc is None or doc.organization_id != user.organization_id:
        raise not_found("Documento")
    return doc


@router.post("", response_model=list[DocumentOut], status_code=status.HTTP_201_CREATED)
async def upload_documents(
    user: EditorUser,
    db: DbSession,
    storage: StorageDep,
    queue: QueueDep,
    files: Annotated[list[UploadFile], File(description="Uno o varios archivos")],
) -> list[Document]:
    # 1. Validar todos los archivos antes de guardar ninguno.
    accepted: list[tuple[str, bytes, str]] = []
    rejected: list[dict[str, str]] = []
    for upload in files:
        name = _safe_filename(upload.filename)
        data = await upload.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            rejected.append({"filename": name, "reason": f"Supera {settings.max_upload_mb} MB"})
            continue
        content_type = detect_content_type(data, name)
        if content_type is None:
            rejected.append(
                {
                    "filename": name,
                    "reason": "Tipo no permitido (PDF, Word, Excel, PowerPoint, CSV, TXT o imagen)",
                }
            )
            continue
        accepted.append((name, data, content_type))
    if rejected:
        raise AppError(400, "invalid_files", "Algunos archivos no son válidos", rejected)

    # 2. Guardar en S3, crear registros "pending" y encolar el procesamiento.
    docs: list[Document] = []
    for name, data, content_type in accepted:
        doc_id = uuid.uuid4()
        key = f"{user.organization_id}/{doc_id}/{name}"
        await storage.put(key, data, content_type)
        doc = Document(
            id=doc_id,
            organization_id=user.organization_id,
            filename=name,
            storage_key=key,
            content_type=content_type,
            size_bytes=len(data),
            status=DocumentStatus.PENDING,
            uploaded_by=user.id,
        )
        db.add(doc)
        docs.append(doc)
    await db.commit()
    for doc in docs:
        await db.refresh(doc)
        await queue.enqueue_document(doc.id)
    return docs


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    doc_type: str | None = None,
) -> list[Document]:
    stmt = select(Document).where(Document.organization_id == user.organization_id)
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    result = await db.scalars(stmt.order_by(Document.created_at.desc()))
    return list(result)


@router.get("/events")
async def document_events(user: CurrentUser, request: Request) -> EventSourceResponse:
    """Stream SSE con cada cambio de estado de los documentos de la organización.

    Un solo stream por usuario (en vez de uno por documento) evita agotar el límite de
    conexiones simultáneas del navegador al subir muchos archivos a la vez.
    """
    org_id = user.organization_id

    async def events() -> AsyncIterator[ServerSentEvent]:
        seen: dict[uuid.UUID, tuple[str, datetime]] = {}
        while not await request.is_disconnected():
            recent = datetime.now(UTC) - timedelta(minutes=10)
            async with SessionLocal() as db:
                rows = await db.scalars(
                    select(Document).where(
                        Document.organization_id == org_id,
                        or_(
                            Document.updated_at >= recent,
                            Document.status.in_(
                                [DocumentStatus.PENDING, DocumentStatus.PROCESSING]
                            ),
                        ),
                    )
                )
                for doc in rows:
                    state = (doc.status, doc.updated_at)
                    if seen.get(doc.id) != state:
                        seen[doc.id] = state
                        payload = DocumentOut.model_validate(doc).model_dump_json()
                        yield ServerSentEvent(data=payload, event="document")
            await asyncio.sleep(STATUS_POLL_SECONDS)

    return EventSourceResponse(events(), ping=15)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Document:
    return await _get_org_document(db, user, document_id)


@router.get("/{document_id}/file", response_model=FileUrlOut)
async def get_document_file(
    document_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> FileUrlOut:
    doc = await _get_org_document(db, user, document_id)
    url = await storage.signed_url(doc.storage_key, settings.signed_url_seconds)
    return FileUrlOut(url=url, expires_in=settings.signed_url_seconds)


@router.post("/{document_id}/retry", response_model=DocumentOut)
async def retry_document(
    document_id: uuid.UUID, user: EditorUser, db: DbSession, queue: QueueDep
) -> Document:
    doc = await _get_org_document(db, user, document_id)
    if doc.status != DocumentStatus.FAILED:
        raise AppError(409, "not_failed", "Solo se pueden reintentar documentos fallidos")
    doc.status = DocumentStatus.PENDING
    doc.error = None
    await db.commit()
    await db.refresh(doc)
    await queue.enqueue_document(doc.id)
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: EditorUser, db: DbSession, storage: StorageDep
) -> None:
    doc = await _get_org_document(db, user, document_id)
    await db.delete(doc)  # los fragmentos se borran en cascada
    await db.commit()
    try:
        await storage.delete(doc.storage_key)
    except StorageError:
        # El registro ya no existe; un archivo huérfano no debe hacer fallar la petición.
        logger.warning("No se pudo borrar %s del storage", doc.storage_key, exc_info=True)
