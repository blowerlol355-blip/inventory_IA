"""Operaciones sobre archivos que usa el agente: convertir, empaquetar en ZIP y reducir peso.

Regla de seguridad: los archivos de origen se buscan SIEMPRE dentro de la organización del
usuario autenticado; un id de otra organización se trata como inexistente.
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, GeneratedFile
from app.services.files.compress import make_zip, reduce_size
from app.services.files.convert import ConversionError, OutputFile, convert
from app.services.storage import Storage

MAX_ZIP_FILES = 50
MAX_ZIP_BYTES = 200 * 1024 * 1024


@dataclass
class SourceFile:
    id: uuid.UUID
    filename: str
    content_type: str
    storage_key: str
    size_bytes: int


@dataclass
class FileContext:
    db: AsyncSession
    storage: Storage
    organization_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None


async def resolve_sources(ctx: FileContext, ids: list[uuid.UUID]) -> list[SourceFile]:
    """Documentos o archivos generados de la organización, en el orden pedido."""
    docs = await ctx.db.scalars(
        select(Document).where(
            Document.id.in_(ids), Document.organization_id == ctx.organization_id
        )
    )
    generated = await ctx.db.scalars(
        select(GeneratedFile).where(
            GeneratedFile.id.in_(ids), GeneratedFile.organization_id == ctx.organization_id
        )
    )
    found: dict[uuid.UUID, SourceFile] = {
        item.id: SourceFile(
            item.id, item.filename, item.content_type, item.storage_key, item.size_bytes
        )
        for item in [*docs, *generated]
    }
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise ConversionError(
            f"No encontré estos archivos en tu organización: {', '.join(missing)}"
        )
    return [found[i] for i in ids]


async def _save(
    ctx: FileContext, output: OutputFile, operation: str, sources: list[SourceFile]
) -> GeneratedFile:
    file_id = uuid.uuid4()
    key = f"{ctx.organization_id}/generated/{file_id}/{output.filename}"
    await ctx.storage.put(key, output.data, output.content_type)
    generated = GeneratedFile(
        id=file_id,
        organization_id=ctx.organization_id,
        created_by=ctx.user_id,
        conversation_id=ctx.conversation_id,
        filename=output.filename,
        storage_key=key,
        content_type=output.content_type,
        size_bytes=len(output.data),
        operation=operation,
        sources=[{"id": str(s.id), "filename": s.filename} for s in sources],
    )
    ctx.db.add(generated)
    await ctx.db.commit()
    await ctx.db.refresh(generated)
    return generated


async def convert_file(ctx: FileContext, source_id: uuid.UUID, target: str) -> GeneratedFile:
    (source,) = await resolve_sources(ctx, [source_id])
    data = await ctx.storage.get(source.storage_key)
    output = await asyncio.to_thread(convert, data, source.content_type, source.filename, target)
    return await _save(ctx, output, "convert", [source])


async def zip_files(ctx: FileContext, ids: list[uuid.UUID], name: str) -> GeneratedFile:
    if len(ids) > MAX_ZIP_FILES:
        raise ConversionError(f"Máximo {MAX_ZIP_FILES} archivos por ZIP.")
    sources = await resolve_sources(ctx, list(dict.fromkeys(ids)))
    if sum(s.size_bytes for s in sources) > MAX_ZIP_BYTES:
        raise ConversionError("Los archivos suman demasiado para un solo ZIP (máx. 200 MB).")
    contents = await asyncio.gather(*(ctx.storage.get(s.storage_key) for s in sources))
    files = [(s.filename, data) for s, data in zip(sources, contents, strict=True)]
    output = await asyncio.to_thread(make_zip, files, name)
    return await _save(ctx, output, "zip", sources)


async def reduce_file(ctx: FileContext, source_id: uuid.UUID) -> tuple[GeneratedFile | None, int]:
    """Devuelve (archivo reducido o None si ya estaba optimizado, tamaño original)."""
    (source,) = await resolve_sources(ctx, [source_id])
    data = await ctx.storage.get(source.storage_key)
    output, reduced = await asyncio.to_thread(
        reduce_size, data, source.content_type, source.filename
    )
    if not reduced:
        return None, len(data)
    return await _save(ctx, output, "reduce", [source]), len(data)


async def file_url(storage: Storage, item: GeneratedFile) -> str:
    return await storage.signed_url(
        item.storage_key, settings.signed_url_seconds, download=item.filename
    )


def describe(item: GeneratedFile) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "filename": item.filename,
        "content_type": item.content_type,
        "size_bytes": item.size_bytes,
        "operation": item.operation,
    }
