"""Límite de preguntas por usuario y minuto, para controlar el costo de la IA.

Se calcula contando las preguntas guardadas en `messages` durante el último minuto: no
necesita Redis y funciona igual con una o varias réplicas de la API.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Conversation, Message


class RateLimiter(Protocol):
    async def check(self, user_id: uuid.UUID) -> None: ...


class DbRateLimiter:
    def __init__(self, db: AsyncSession, limit_per_minute: int) -> None:
        self._db = db
        self._limit = limit_per_minute

    async def check(self, user_id: uuid.UUID) -> None:
        since = datetime.now(UTC) - timedelta(minutes=1)
        count = await self._db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.role == "user",
                Message.created_at >= since,
            )
        )
        if (count or 0) >= self._limit:
            raise AppError(
                429,
                "rate_limited",
                f"Máximo {self._limit} preguntas por minuto. Espera unos segundos.",
            )


def get_rate_limiter(db: Annotated[AsyncSession, Depends(get_db)]) -> RateLimiter:
    return DbRateLimiter(db, settings.questions_per_minute)
