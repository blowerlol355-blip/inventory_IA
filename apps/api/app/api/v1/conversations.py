import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.deps import CurrentUser, DbSession
from app.core.errors import not_found
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.models import Conversation, Message, User
from app.schemas.chat import ConversationCreate, ConversationOut, MessageCreate, MessageOut
from app.services.agent.agent import AgentResult, run_agent
from app.services.agent.tools import AgentContext
from app.services.llm.base import ChatMessage, LLMError
from app.services.storage import Storage, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])

TITLE_CHARS = 60


async def _get_own_conversation(
    db: DbSession, user: User, conversation_id: uuid.UUID
) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id or conv.organization_id != user.organization_id:
        raise not_found("Conversación")
    return conv


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, db: DbSession
) -> Conversation:
    conv = Conversation(organization_id=user.organization_id, user_id=user.id)
    if body.title:
        conv.title = body.title
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUser, db: DbSession) -> list[Conversation]:
    rows = await db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
    )
    return list(rows)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[Message]:
    await _get_own_conversation(db, user, conversation_id)
    rows = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(rows)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    user: CurrentUser,
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> EventSourceResponse:
    """Envía una pregunta y responde por SSE con los eventos:

    - `token`: trozo de texto de la respuesta.
    - `tool`: una herramienta empieza (`running`) o termina (`done` / `error`).
    - `sources`: fragmentos recuperados (numerados) que el modelo puede citar.
    - `file`: archivo generado por una herramienta (conversión, ZIP, compresión).
    - `done`: id del mensaje guardado, citas usadas, tokens y latencia.
    - `error`: algo falló; la pregunta queda guardada pero no la respuesta.
    """
    conv = await _get_own_conversation(db, user, conversation_id)
    await limiter.check(user.id)

    previous = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc())
        .limit(settings.history_messages)
    )
    history = [
        ChatMessage("user" if m.role == "user" else "assistant", m.content)
        for m in reversed(list(previous))
    ]

    question = body.content.strip()
    if not history and conv.title == "Nueva conversación":
        conv.title = question[:TITLE_CHARS]
    db.add(Message(conversation_id=conv.id, role="user", content=question))
    await db.commit()

    organization_id, user_id = user.organization_id, user.id

    async def events() -> AsyncIterator[ServerSentEvent]:
        def sse(name: str, data: Any) -> ServerSentEvent:
            return ServerSentEvent(data=json.dumps(data, ensure_ascii=False), event=name)

        result = AgentResult()
        # La sesión de la petición ya se cerró al empezar el stream: abrimos una propia.
        async with SessionLocal() as stream_db:
            ctx = AgentContext(stream_db, storage, organization_id, user_id, conversation_id)
            try:
                async for name, data in run_agent(ctx, question, history, result):
                    yield sse(name, data)
            except LLMError as exc:
                yield sse("error", {"message": str(exc)})
                return
            except Exception:
                logger.exception("Error respondiendo en la conversación %s", conversation_id)
                yield sse("error", {"message": "Error interno al generar la respuesta"})
                return

            message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=result.text,
                citations=result.citations,
                tool_calls=result.tool_log or None,
                attachments=result.attachments or None,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                latency_ms=result.latency_ms,
            )
            stream_db.add(message)
            await stream_db.commit()
            yield sse(
                "done",
                {
                    "message_id": str(message.id),
                    "content": result.text,
                    "citations": result.citations,
                    "attachments": result.attachments,
                    "usage": {
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                    },
                    "latency_ms": result.latency_ms,
                },
            )

    return EventSourceResponse(events(), ping=15)
