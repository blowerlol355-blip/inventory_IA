from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

TRANSACTION_POOLER_PORT = ":6543"


def make_engine(url: str = settings.database_url, schema: str = settings.db_schema) -> AsyncEngine:
    connect_args: dict[str, Any] = {}
    if TRANSACTION_POOLER_PORT in url:
        # El pooler de Supabase en modo transacción no admite sentencias preparadas.
        connect_args = {"statement_cache_size": 0, "prepared_statement_cache_size": 0}

    # El esquema de las tablas se escribe explícitamente en cada consulta. No se usa
    # search_path para esto: el pooler de Supabase reutiliza conexiones del servidor entre
    # clientes y un SET de una sesión podría filtrarse a otra.
    execution_options = {"schema_translate_map": {None: schema}} if schema != "public" else {}
    engine = create_async_engine(
        url, pool_pre_ping=True, connect_args=connect_args, execution_options=execution_options
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_search_path(dbapi_connection: Any, _: Any) -> None:
        # Supabase instala las extensiones (pgvector) en el esquema "extensions". Es el mismo
        # valor para todas las conexiones, así que no importa si el pooler lo comparte.
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO public, extensions")
        cursor.close()

    return engine


engine = make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
