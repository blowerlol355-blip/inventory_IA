"""Worker de ingesta con cola en PostgreSQL (sin Redis).

La tabla `documents` es la cola: un documento `pending` es un trabajo pendiente. Cada worker
reclama el siguiente con `FOR UPDATE SKIP LOCKED`, de modo que varios workers (o varias
réplicas de la API) nunca procesan el mismo documento.
"""

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Document, DocumentStatus
from app.services.ingestion.pipeline import process_document

logger = logging.getLogger(__name__)

STALE_CHECK_SECONDS = 60


async def claim_next_document() -> uuid.UUID | None:
    next_pending = (
        select(Document.id)
        .where(Document.status == DocumentStatus.PENDING)
        .order_by(Document.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    stmt = (
        update(Document)
        .where(Document.id == next_pending)
        .values(status=DocumentStatus.PROCESSING, updated_at=func.now())
        .returning(Document.id)
    )
    async with SessionLocal() as db:
        document_id = await db.scalar(stmt)
        await db.commit()
    return document_id


async def requeue_stale_documents() -> int:
    """Devuelve a la cola los documentos que quedaron 'processing' (p. ej. el proceso murió)."""
    limit = datetime.now(UTC) - timedelta(minutes=settings.stale_processing_minutes)
    stmt = (
        update(Document)
        .where(Document.status == DocumentStatus.PROCESSING, Document.updated_at < limit)
        .values(status=DocumentStatus.PENDING)
        .returning(Document.id)
    )
    async with SessionLocal() as db:
        ids = list(await db.scalars(stmt))
        await db.commit()
    if ids:
        logger.warning("Reencolados %d documentos atascados en 'processing'", len(ids))
    return len(ids)


class IngestionWorker:
    def __init__(
        self,
        poll_seconds: float = settings.worker_poll_seconds,
        concurrency: int = settings.worker_concurrency,
    ) -> None:
        self._poll_seconds = poll_seconds
        self._concurrency = max(1, concurrency)
        self._wake = asyncio.Event()

    def wake(self) -> None:
        """Avisa de que hay un documento nuevo (evita esperar al siguiente sondeo)."""
        self._wake.set()

    async def run(self) -> None:
        """Varios bucles en paralelo: un documento lento (p. ej. muchas páginas con OCR) no
        bloquea al resto. SKIP LOCKED garantiza que no reclamen el mismo documento."""
        logger.info("Worker de ingesta iniciado (%d en paralelo)", self._concurrency)
        async with asyncio.TaskGroup() as group:
            for slot in range(self._concurrency):
                group.create_task(self._loop(check_stale=slot == 0))

    async def _loop(self, *, check_stale: bool) -> None:
        last_stale_check = 0.0
        while True:
            try:
                if check_stale and time.monotonic() - last_stale_check > STALE_CHECK_SECONDS:
                    await requeue_stale_documents()
                    last_stale_check = time.monotonic()
                document_id = await claim_next_document()
                if document_id is not None:
                    await process_document(document_id)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                # Un fallo de conexión no debe matar el worker: se reintenta tras el sondeo.
                logger.exception("Error en el worker de ingesta")
            self._wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self._poll_seconds)


worker = IngestionWorker()
