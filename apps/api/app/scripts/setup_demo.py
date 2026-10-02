"""Crea la organización de la demo pública: python -m app.scripts.setup_demo

    python -m app.scripts.setup_demo                      # demo@findocs-demo.com
    python -m app.scripts.setup_demo --email otra@x.com

Crea la organización "FinDocs Demo" con un administrador cuya contraseña aleatoria no se
muestra (nadie necesita entrar como él). Después, cárgale los documentos con:

    uv run --project apps/api python data/generator/seed_demo.py --email demo@findocs-demo.com

y en el servidor define DEMO_OWNER_EMAIL con ese email para activar el botón "Probar demo".
"""

import argparse
import asyncio
import secrets

from sqlalchemy import select

from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import Organization, User, UserRole

DEFAULT_EMAIL = "demo@findocs-demo.com"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--name", default="FinDocs Demo")
    args = parser.parse_args()
    email = args.email.lower()

    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.email == email)):
            print(f"Ya existe {email}: la organización demo está creada.")
        else:
            org = Organization(name=args.name)
            db.add(org)
            await db.flush()
            db.add(
                User(
                    organization_id=org.id,
                    email=email,
                    password_hash=hash_password(secrets.token_urlsafe(24)),
                    role=UserRole.ADMIN,
                )
            )
            await db.commit()
            print(f"Organización '{args.name}' creada con el administrador {email}.")
    await engine.dispose()
    print(f"Siguiente paso: python data/generator/seed_demo.py --email {email}")


if __name__ == "__main__":
    asyncio.run(main())
