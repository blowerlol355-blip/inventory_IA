"""Carga el set de demostración (50 documentos) en todas las organizaciones existentes.

Uso (desde la raíz del repo, con la API corriendo para que su worker procese la cola):
    uv run --project apps/api python data/generator/seed_demo.py
    uv run --project apps/api python data/generator/seed_demo.py --email usuario@empresa.com

Qué hace:
1. Genera 50 documentos sintéticos en data/demo50 (facturas, 2 escaneadas para OCR, contratos,
   estados de cuenta, Word, Excel, PowerPoint, CSV, TXT, fotos JPG y 3 archivos vacíos).
2. Para cada organización (o solo la del email indicado), sube a Supabase Storage los archivos
   que aún no tenga (por nombre) y los deja en la cola como `pending`.
3. Espera a que el worker los procese y muestra el resultado.
4. Crea archivos generados de ejemplo con las mismas herramientas que usa la IA: un ZIP de
   facturas, Excel → CSV, PowerPoint → PDF y una versión comprimida de un escaneo.

Es idempotente: volver a ejecutarlo no duplica documentos ni archivos generados.
"""

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.db import SessionLocal, engine
from app.models import (
    Document,
    DocumentStatus,
    GeneratedFile,
    Organization,
    User,
    UserRole,
)
from app.services.agent.tools import AgentContext, execute_tool
from app.services.ingestion.filetypes import detect_content_type
from app.services.llm.base import ToolCall
from app.services.storage import get_storage
from generate import generate
from sqlalchemy import func, select

DEMO_DIR = ROOT / "data" / "demo50"
EMPTY_FILES = ["vacio.docx", "vacio.xlsx", "vacio.pdf"]
EXPECTED = 50
WAIT_TIMEOUT_S = 900


def build_demo_set() -> list[Path]:
    generate(
        DEMO_DIR,
        invoices_count=22,
        contracts_count=8,
        statements_count=3,
        scanned_count=2,
        extended=True,
    )
    files = sorted(
        p
        for p in DEMO_DIR.iterdir()
        if p.is_file() and p.suffix not in (".json", ".md")
    )
    files += [DEMO_DIR / "vacios" / name for name in EMPTY_FILES]
    if len(files) != EXPECTED:
        raise SystemExit(
            f"Se esperaban {EXPECTED} documentos y se generaron {len(files)}"
        )
    return files


async def seed_organization(
    org: Organization, uploader: User, files: list[Path]
) -> int:
    storage = get_storage()
    async with SessionLocal() as db:
        existing = set(
            await db.scalars(
                select(Document.filename).where(Document.organization_id == org.id)
            )
        )
        created = 0
        for path in files:
            if path.name in existing:
                continue
            data = path.read_bytes()
            content_type = detect_content_type(data, path.name)
            if content_type is None:
                print(f"  ! {path.name}: tipo no permitido, se omite")
                continue
            doc_id = uuid.uuid4()
            key = f"{org.id}/{doc_id}/{path.name}"
            await storage.put(key, data, content_type)
            db.add(
                Document(
                    id=doc_id,
                    organization_id=org.id,
                    filename=path.name,
                    storage_key=key,
                    content_type=content_type,
                    size_bytes=len(data),
                    status=DocumentStatus.PENDING,
                    uploaded_by=uploader.id,
                )
            )
            created += 1
        await db.commit()
    return created


async def wait_for_processing(org_ids: list[uuid.UUID]) -> None:
    started = time.monotonic()
    while True:
        async with SessionLocal() as db:
            pending = await db.scalar(
                select(func.count())
                .select_from(Document)
                .where(
                    Document.organization_id.in_(org_ids),
                    Document.status.in_(
                        [DocumentStatus.PENDING, DocumentStatus.PROCESSING]
                    ),
                )
            )
        if not pending:
            return
        if time.monotonic() - started > WAIT_TIMEOUT_S:
            raise SystemExit(
                "Tiempo de espera agotado. ¿Está corriendo la API (su worker procesa la cola)?"
            )
        print(f"  … {pending} documentos en cola o procesando", flush=True)
        await asyncio.sleep(5)


async def create_sample_outputs(org: Organization, user: User) -> list[str]:
    """Archivos generados de ejemplo, con las mismas herramientas que usa el agente."""
    async with SessionLocal() as db:
        already = await db.scalar(
            select(func.count())
            .select_from(GeneratedFile)
            .where(GeneratedFile.organization_id == org.id)
        )
        if already:
            return []
        docs = {
            d.filename: d
            for d in await db.scalars(
                select(Document).where(
                    Document.organization_id == org.id,
                    Document.status == DocumentStatus.READY,
                )
            )
        }
        invoices = [
            str(d.id)
            for name, d in sorted(docs.items())
            if name.startswith("factura_0")
        ]
        calls = [
            (
                "compress_files",
                {"file_ids": invoices[:10], "mode": "zip", "zip_name": "facturas_demo"},
            ),
        ]
        for name, target in [
            ("gastos_trimestre.xlsx", "csv"),
            ("plan_comercial_2027.pptx", "pdf"),
        ]:
            if name in docs:
                calls.append(
                    (
                        "convert_document",
                        {"file_id": str(docs[name].id), "target_format": target},
                    )
                )
        scanned = sorted(n for n in docs if n.startswith("factura_0"))[-1:]
        if scanned:
            calls.append(
                (
                    "compress_files",
                    {
                        "file_ids": [str(docs[scanned[0]].id)],
                        "mode": "reduce_size",
                        "zip_name": "",
                    },
                )
            )

        ctx = AgentContext(db, get_storage(), org.id, user.id)
        results = []
        for i, (name, args) in enumerate(calls):
            outcome = await execute_tool(ctx, ToolCall(f"seed-{i}", name, args))
            mark = "x" if outcome.result.is_error else "ok"
            results.append(f"[{mark}] {name}: {outcome.summary}")
        return results


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Solo la organización de este usuario")
    parser.add_argument(
        "--no-wait", action="store_true", help="No esperar al procesamiento"
    )
    args = parser.parse_args()

    files = build_demo_set()
    print(f"Set de demostración: {len(files)} documentos en {DEMO_DIR}")

    async with SessionLocal() as db:
        query = select(User).order_by(User.created_at)
        if args.email:
            query = query.where(User.email == args.email.lower())
        users = list(await db.scalars(query))
        if not users:
            raise SystemExit("No hay usuarios: regístrate primero en la web.")
        # Por organización, sube a nombre de un admin (o editor) existente.
        uploaders: dict[uuid.UUID, User] = {}
        for user in users:
            current = uploaders.get(user.organization_id)
            if current is None or (
                current.role != UserRole.ADMIN and user.role == UserRole.ADMIN
            ):
                uploaders[user.organization_id] = user
        orgs = {
            o.id: o
            for o in await db.scalars(
                select(Organization).where(Organization.id.in_(uploaders))
            )
        }

    for org_id, uploader in uploaders.items():
        created = await seed_organization(orgs[org_id], uploader, files)
        print(
            f"- {orgs[org_id].name.strip()} ({uploader.email}): {created} documentos nuevos en cola"
        )

    if not args.no_wait:
        await wait_for_processing(list(uploaders))
        async with SessionLocal() as db:
            for org_id, uploader in uploaders.items():
                rows = await db.execute(
                    select(Document.status, func.count())
                    .where(Document.organization_id == org_id)
                    .group_by(Document.status)
                )
                summary = ", ".join(f"{status}: {count}" for status, count in rows)
                print(f"- {orgs[org_id].name.strip()}: {summary}")
                for line in await create_sample_outputs(orgs[org_id], uploader):
                    print(f"    {line}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
