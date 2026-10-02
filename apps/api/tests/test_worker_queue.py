"""Cola de ingesta en PostgreSQL: reclamo con SKIP LOCKED y recuperación de atascados."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus, Organization
from app.workers.ingestion import claim_next_document, requeue_stale_documents


async def _create_documents(count: int) -> list[uuid.UUID]:
    async with SessionLocal() as db:
        org = Organization(name="Org cola")
        db.add(org)
        await db.flush()
        docs = [
            Document(
                organization_id=org.id,
                filename=f"doc{i}.pdf",
                storage_key=f"k/{i}",
                content_type="application/pdf",
                size_bytes=1,
                status=DocumentStatus.PENDING,
            )
            for i in range(count)
        ]
        db.add_all(docs)
        await db.commit()
        return [d.id for d in docs]


async def test_concurrent_claims_never_take_the_same_document(database: None) -> None:
    created = set(await _create_documents(5))
    claimed = await asyncio.gather(*(claim_next_document() for _ in range(8)))
    taken = [c for c in claimed if c in created]
    assert len(taken) == len(set(taken)) == 5

    async with SessionLocal() as db:
        statuses = {(await db.get(Document, d)).status for d in created}  # type: ignore[union-attr]
    assert statuses == {DocumentStatus.PROCESSING}


async def test_stale_processing_documents_are_requeued(database: None) -> None:
    (doc_id,) = await _create_documents(1)
    old = datetime.now(UTC) - timedelta(hours=1)
    async with SessionLocal() as db:
        await db.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(status=DocumentStatus.PROCESSING, updated_at=old)
        )
        await db.commit()

    assert await requeue_stale_documents() >= 1
    async with SessionLocal() as db:
        doc = await db.get(Document, doc_id)
        assert doc is not None and doc.status == DocumentStatus.PENDING
