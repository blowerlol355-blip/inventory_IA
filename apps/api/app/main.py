import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AppError, register_error_handlers
from app.services.storage import get_storage
from app.workers.ingestion import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    worker_task: asyncio.Task[None] | None = None
    if settings.app_env != "test":
        try:
            await get_storage().ensure_bucket()
        except Exception:
            logger.exception("No se pudo verificar el bucket de Supabase Storage")
        if settings.run_worker_in_api:
            worker_task = asyncio.create_task(worker.run())
    yield
    if worker_task is not None:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task


app = FastAPI(
    title="FinDocs AI API",
    version="0.1.0",
    description="Consulta documentos financieros en lenguaje natural con respuestas citadas.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError(503, "unhealthy", "Base de datos no disponible") from exc
    return {"status": "ok"}
