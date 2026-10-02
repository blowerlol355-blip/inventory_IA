"""Configuración de tests.

Los tests unitarios no necesitan servicios. Los de integración necesitan PostgreSQL con
pgvector (Supabase sirve): usan TEST_DATABASE_URL o, si no existe, DATABASE_URL del .env.
Trabajan en un esquema propio (`findocs_test`) que se borra y recrea, de modo que nunca
tocan las tablas reales. Si no hay base de datos disponible, se omiten.
Storage, embeddings y LLM se reemplazan por dobles en memoria (sin red ni costo).
"""

import os
from pathlib import Path

from dotenv import dotenv_values

_env = dotenv_values(Path(__file__).resolve().parents[3] / ".env")
_database_url = (
    os.environ.get("TEST_DATABASE_URL")
    or _env.get("TEST_DATABASE_URL")
    or _env.get("DATABASE_URL")
    or "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
)

# Debe ejecutarse antes de importar la app: la configuración se lee al importar.
os.environ.update(
    {
        "APP_ENV": "test",
        "LLM_PROVIDER": "fake",
        "EMBEDDING_PROVIDER": "hash",
        "DATABASE_URL": _database_url,
        "DB_SCHEMA": "findocs_test",
    }
)

import io  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.ingestion import pipeline  # noqa: E402
from app.services.storage import get_storage  # noqa: E402
from app.workers.queue import get_queue  # noqa: E402


class MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.files[key] = data

    async def get(self, key: str) -> bytes:
        return self.files[key]

    async def delete(self, key: str) -> None:
        self.files.pop(key, None)

    async def signed_url(self, key: str, expires_seconds: int, download: str | None = None) -> str:
        suffix = f"&download={download}" if download else ""
        return f"http://storage.test/{key}?expires={expires_seconds}{suffix}"


class InlineQueue:
    """Procesa el documento en el momento, en vez de esperar al worker."""

    async def enqueue_document(self, document_id: uuid.UUID) -> None:
        await pipeline.process_document(document_id)


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for content in pages:
        page = doc.new_page()
        page.insert_htmlbox(pymupdf.Rect(50, 50, 545, 790), content)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def make_scanned_pdf(text: str) -> bytes:
    """PDF cuya única página es una imagen (como un escaneo): no tiene texto extraíble."""
    with pymupdf.open(stream=make_pdf([f"<p>{text}</p>"]), filetype="pdf") as source:
        pixmap = source[0].get_pixmap(dpi=72)
    scanned = pymupdf.open()
    page = scanned.new_page()
    page.insert_image(page.rect, pixmap=pixmap)
    buffer = io.BytesIO()
    scanned.save(buffer)
    return buffer.getvalue()


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[None]:
    schema = settings.db_schema
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS extensions"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions"))
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
    except OSError as exc:
        pytest.skip(f"Base de datos de tests no disponible: {exc}")
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await engine.dispose()


@pytest.fixture
async def client(database: None, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    storage = MemoryStorage()
    monkeypatch.setattr(pipeline, "get_storage", lambda: storage)
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_queue] = InlineQueue
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
