"""Recuperación de fragmentos. Fase 1: similitud vectorial (la búsqueda híbrida llega en la Fase 3).

Regla de seguridad: el filtro por organización se aplica DENTRO de la consulta, antes de
que ningún fragmento llegue al LLM.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document, DocumentStatus


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page: int
    content: str
    score: float  # similitud coseno: 1 = idéntico
    content_type: str = ""


async def vector_search(
    db: AsyncSession,
    organization_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
) -> list[RetrievedChunk]:
    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Document.filename,
            Document.content_type,
            Chunk.page,
            Chunk.content,
            distance.label("distance"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.organization_id == organization_id,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(distance)
        .limit(top_k)
    )
    rows = await db.execute(stmt)
    return [
        RetrievedChunk(
            chunk_id=r.id,
            document_id=r.document_id,
            filename=r.filename,
            page=r.page,
            content=r.content,
            score=1 - float(r.distance),
            content_type=r.content_type,
        )
        for r in rows
    ]
