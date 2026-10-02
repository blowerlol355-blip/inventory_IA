"""Reprocesa todos los documentos con los proveedores configurados: python -m app.scripts.reindex

Necesario al pasar de los embeddings de prueba (hash) a Voyage AI, o al cambiar de modelo de
embeddings: los vectores de modelos distintos no son comparables. Deja cada documento en
`pending` y el worker (dentro de la API) lo vuelve a parsear, clasificar, aplicar OCR y
vectorizar; el pipeline reemplaza los fragmentos anteriores.

    python -m app.scripts.reindex                 # todas las organizaciones
    python -m app.scripts.reindex --email a@b.com # solo la organización de ese usuario
    python -m app.scripts.reindex --failed        # solo los documentos fallidos
"""

import argparse
import asyncio

from sqlalchemy import select, update

from app.core.db import SessionLocal, engine
from app.models import Document, DocumentStatus, User


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", help="Solo la organización de este usuario")
    parser.add_argument("--failed", action="store_true", help="Solo documentos fallidos")
    args = parser.parse_args()

    async with SessionLocal() as db:
        query = update(Document).values(status=DocumentStatus.PENDING, error=None)
        if args.email:
            org_id = await db.scalar(
                select(User.organization_id).where(User.email == args.email.lower())
            )
            if org_id is None:
                raise SystemExit(f"No existe el usuario {args.email}")
            query = query.where(Document.organization_id == org_id)
        if args.failed:
            query = query.where(Document.status == DocumentStatus.FAILED)
        else:
            query = query.where(Document.status != DocumentStatus.PROCESSING)
        result = await db.execute(query)
        await db.commit()
    await engine.dispose()
    print(
        f"{result.rowcount} documentos en cola. El worker de la API los procesará "  # type: ignore[attr-defined]
        "(míralo en la página Documentos)."
    )


if __name__ == "__main__":
    asyncio.run(main())
