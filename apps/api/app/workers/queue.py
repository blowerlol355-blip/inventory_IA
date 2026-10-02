"""Encolado de documentos. La cola es la propia tabla `documents` (estado `pending`)."""

import uuid
from typing import Protocol

from app.workers.ingestion import worker


class TaskQueue(Protocol):
    async def enqueue_document(self, document_id: uuid.UUID) -> None: ...


class PostgresQueue:
    async def enqueue_document(self, document_id: uuid.UUID) -> None:
        # El documento ya está guardado como `pending`; solo despertamos al worker local.
        # Si el worker corre en otro proceso, lo recogerá en su siguiente sondeo.
        worker.wake()


_queue = PostgresQueue()


def get_queue() -> TaskQueue:
    return _queue
