"""Herramientas del agente: buscar en documentos, listarlos, convertirlos y comprimirlos.

Seguridad:
- Los argumentos del modelo se validan con Pydantic antes de ejecutar nada.
- Toda herramienta actúa con el `organization_id` del usuario autenticado (AgentContext),
  nunca con uno que venga del modelo.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentStatus, GeneratedFile
from app.services.agent.sources import Source, build_sources, format_sources
from app.services.files.convert import TARGET_TYPES, ConversionError, supported_targets
from app.services.files.service import (
    FileContext,
    convert_file,
    describe,
    reduce_file,
    zip_files,
)
from app.services.llm.base import ToolCall, ToolResult, ToolSpec
from app.services.retrieval.embeddings import EmbeddingError, get_embedder
from app.services.retrieval.search import vector_search
from app.services.storage import Storage, StorageError

DOC_TYPES = ["todos", "factura", "contrato", "estado_de_cuenta", "otro"]
TARGET_FORMATS = sorted(TARGET_TYPES)
MAX_LISTED = 50


# ------------------------------------------------------------------------- definiciones

TOOL_SPECS = [
    ToolSpec(
        name="search_documents",
        description=(
            "Busca en el contenido de los documentos de la organización y devuelve fragmentos "
            "numerados con su documento y página. Úsala SIEMPRE antes de responder cualquier "
            "pregunta sobre lo que dicen los documentos (montos, fechas, cláusulas, proveedores, "
            "políticas). Puedes llamarla varias veces con consultas distintas."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta autónoma en lenguaje natural (resuelve referencias "
                    "al historial, p. ej. 'total de la factura F-000001').",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="list_documents",
        description=(
            "Lista los documentos subidos y los archivos generados de la organización, con su id, "
            "nombre, tipo, formato y los formatos a los que se pueden convertir. Úsala cuando el "
            "usuario pregunte qué archivos tiene, o para obtener el id de un archivo antes de "
            "convertirlo o comprimirlo."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": DOC_TYPES,
                    "description": "Filtra por tipo de documento ('todos' para no filtrar).",
                },
                "name_contains": {
                    "type": "string",
                    "description": "Texto que debe contener el nombre del archivo ('' para no "
                    "filtrar).",
                },
            },
            "required": ["doc_type", "name_contains"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="convert_document",
        description=(
            "Convierte un archivo (documento subido o archivo generado) a otro formato y crea un "
            "archivo descargable. Úsala cuando el usuario pida cambiar el formato de un archivo. "
            "Si no conoces el id, llama antes a list_documents. Office → PDF conserva texto y "
            "tablas, no el diseño original."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "format": "uuid"},
                "target_format": {"type": "string", "enum": TARGET_FORMATS},
            },
            "required": ["file_id", "target_format"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="compress_files",
        description=(
            "Comprime archivos. mode='zip' empaqueta uno o varios archivos en un ZIP descargable. "
            "mode='reduce_size' crea una versión más liviana de cada PDF o imagen (reduce la "
            "calidad de las imágenes). Úsala cuando el usuario pida comprimir, agrupar o "
            "aligerar archivos. Si no conoces los ids, llama antes a list_documents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                "mode": {"type": "string", "enum": ["zip", "reduce_size"]},
                "zip_name": {
                    "type": "string",
                    "description": "Nombre del ZIP sin extensión (solo en mode='zip'; '' para "
                    "usar 'archivos').",
                },
            },
            "required": ["file_ids", "mode", "zip_name"],
            "additionalProperties": False,
        },
    ),
]

TOOL_LABELS = {
    "search_documents": "Buscando en los documentos",
    "list_documents": "Revisando tus archivos",
    "convert_document": "Convirtiendo archivo",
    "compress_files": "Comprimiendo archivos",
}


class SearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class ListInput(BaseModel):
    doc_type: Literal["todos", "factura", "contrato", "estado_de_cuenta", "otro"] = "todos"
    name_contains: str = Field(default="", max_length=200)


class ConvertInput(BaseModel):
    file_id: uuid.UUID
    target_format: Literal["pdf", "docx", "txt", "csv", "xlsx", "png", "jpg", "webp"]


class CompressInput(BaseModel):
    file_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    mode: Literal["zip", "reduce_size"]
    zip_name: str = Field(default="", max_length=100)


# --------------------------------------------------------------------------- ejecución


@dataclass
class AgentContext:
    db: AsyncSession
    storage: Storage
    organization_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    sources: list[Source] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def files(self) -> FileContext:
        return FileContext(
            self.db, self.storage, self.organization_id, self.user_id, self.conversation_id
        )


@dataclass
class ToolOutcome:
    """Resultado de una herramienta: lo que ve el modelo y lo que se muestra al usuario."""

    result: ToolResult
    summary: str
    new_sources: list[Source] = field(default_factory=list)
    new_files: list[dict[str, Any]] = field(default_factory=list)


def _size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


async def _search(ctx: AgentContext, args: SearchInput) -> tuple[str, str, list[Source]]:
    vector = await get_embedder().embed_query(args.query)
    chunks = await vector_search(ctx.db, ctx.organization_id, vector, settings.retrieval_top_k)
    if not chunks:
        return "Sin resultados: no hay documentos procesados que coincidan.", "0 fragmentos", []
    sources = build_sources(chunks, start=len(ctx.sources) + 1)
    ctx.sources.extend(sources)
    return format_sources(sources), f"{len(sources)} fragmentos", sources


async def _list(ctx: AgentContext, args: ListInput) -> tuple[str, str]:
    stmt = select(Document).where(Document.organization_id == ctx.organization_id)
    if args.doc_type != "todos":
        stmt = stmt.where(Document.doc_type == args.doc_type)
    if args.name_contains:
        stmt = stmt.where(Document.filename.ilike(f"%{args.name_contains}%"))
    docs = list(await ctx.db.scalars(stmt.order_by(Document.created_at.desc()).limit(MAX_LISTED)))

    gen_stmt = select(GeneratedFile).where(GeneratedFile.organization_id == ctx.organization_id)
    if args.name_contains:
        gen_stmt = gen_stmt.where(GeneratedFile.filename.ilike(f"%{args.name_contains}%"))
    generated = list(
        await ctx.db.scalars(gen_stmt.order_by(GeneratedFile.created_at.desc()).limit(MAX_LISTED))
    )

    lines = ["Documentos subidos:"] if docs else ["No hay documentos subidos que coincidan."]
    for d in docs:
        status = "" if d.status == DocumentStatus.READY else f" [estado: {d.status}]"
        targets = ", ".join(supported_targets(d.content_type)) or "ninguno"
        lines.append(
            f"- id={d.id} | {d.filename} | tipo={d.doc_type or 'sin clasificar'} | "
            f"{_size(d.size_bytes)} | convertible a: {targets}{status}"
        )
    if generated:
        lines.append("Archivos generados:")
        for g in generated:
            targets = ", ".join(supported_targets(g.content_type)) or "ninguno"
            lines.append(
                f"- id={g.id} | {g.filename} | {_size(g.size_bytes)} | convertible a: {targets}"
            )
    return "\n".join(lines), f"{len(docs)} documentos, {len(generated)} generados"


async def _convert(ctx: AgentContext, args: ConvertInput) -> tuple[str, str, list[dict[str, Any]]]:
    item = await convert_file(ctx.files, args.file_id, args.target_format)
    info = describe(item)
    text = f"Archivo creado: {item.filename} ({_size(item.size_bytes)}), id={item.id}."
    return text, item.filename, [info]


async def _compress(
    ctx: AgentContext, args: CompressInput
) -> tuple[str, str, list[dict[str, Any]]]:
    if args.mode == "zip":
        item = await zip_files(ctx.files, args.file_ids, args.zip_name.strip() or "archivos")
        text = (
            f"ZIP creado: {item.filename} con {len(item.sources)} archivos "
            f"({_size(item.size_bytes)}), id={item.id}."
        )
        return text, item.filename, [describe(item)]
    created: list[dict[str, Any]] = []
    lines: list[str] = []
    for file_id in dict.fromkeys(args.file_ids):
        try:
            reduced, original = await reduce_file(ctx.files, file_id)
        except ConversionError as exc:
            lines.append(f"- {exc}")
            continue
        if reduced is None:
            lines.append(f"- id={file_id}: ya estaba optimizado ({_size(original)}), sin cambios.")
            continue
        lines.append(
            f"- {reduced.filename}: {_size(original)} → {_size(reduced.size_bytes)}, "
            f"id={reduced.id}."
        )
        created.append(describe(reduced))
    if not created and lines and all("ya estaba" not in line for line in lines):
        raise ConversionError("\n".join(lines))
    return "Resultado:\n" + "\n".join(lines), f"{len(created)} archivos reducidos", created


async def execute_tool(ctx: AgentContext, call: ToolCall) -> ToolOutcome:
    def fail(message: str) -> ToolOutcome:
        return ToolOutcome(ToolResult(call.id, message, is_error=True), summary=message[:120])

    try:
        if call.name == "search_documents":
            text, summary, sources = await _search(ctx, SearchInput.model_validate(call.input))
            return ToolOutcome(ToolResult(call.id, text), summary, new_sources=sources)
        if call.name == "list_documents":
            text, summary = await _list(ctx, ListInput.model_validate(call.input))
            return ToolOutcome(ToolResult(call.id, text), summary)
        if call.name == "convert_document":
            text, summary, files = await _convert(ctx, ConvertInput.model_validate(call.input))
        elif call.name == "compress_files":
            text, summary, files = await _compress(ctx, CompressInput.model_validate(call.input))
        else:
            return fail(f"Herramienta desconocida: {call.name}")
    except ValidationError as exc:
        return fail(f"Argumentos inválidos: {exc.errors(include_url=False)}")
    except ConversionError as exc:
        return fail(str(exc))
    except (EmbeddingError, StorageError) as exc:
        return fail(f"Servicio no disponible: {exc}")
    ctx.attachments.extend(files)
    return ToolOutcome(ToolResult(call.id, text), summary, new_files=files)
