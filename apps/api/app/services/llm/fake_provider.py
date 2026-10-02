"""Proveedor falso y determinista: tests y demos sin API key (LLM_PROVIDER=fake).

Con herramientas: primero llama a `search_documents` con la pregunta del usuario y, cuando
recibe el resultado, responde con el comienzo de la primera fuente citándola como [n].
"""

import re
from collections.abc import AsyncIterator
from typing import Any

from app.services.llm.base import (
    AssistantTurn,
    ChatMessage,
    Completion,
    Effort,
    Message,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolResults,
    ToolSpec,
    Usage,
)

SOURCE_RE = re.compile(r'<fuente id="(\d+)"[^>]*>\s*(.+?)\s*</fuente>', re.DOTALL)
NO_INFO = "No encontré información sobre eso en los documentos disponibles."


def _answer_from_sources(text: str) -> str:
    match = SOURCE_RE.search(text)
    if match is None:
        return NO_INFO
    snippet = " ".join(match.group(2).split())[:200]
    return f"Según los documentos: {snippet} [{match.group(1)}]"


class FakeProvider:
    def _next_step(
        self, messages: list[Message], tools: list[ToolSpec] | None
    ) -> tuple[str, list[ToolCall]]:
        last = messages[-1]
        tool_names = {t.name for t in tools or []}
        if isinstance(last, ToolResults):
            return _answer_from_sources("\n".join(r.content for r in last.results)), []
        if isinstance(last, ChatMessage) and "search_documents" in tool_names:
            call = ToolCall(
                id=f"fake-{len(messages)}", name="search_documents", input={"query": last.content}
            )
            return "", [call]
        content = last.content if isinstance(last, ChatMessage) else ""
        return _answer_from_sources(content), []

    async def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int,
        effort: Effort,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        text, calls = self._next_step(messages, tools)
        for word in text.split(" ") if text else []:
            yield TextDelta(word + " ")
        content: list[dict[str, Any]] = [{"type": "text", "text": text}] if text else []
        content += [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls
        ]
        yield StreamEnd(
            usage=Usage(100, len(text) // 4),
            stop_reason="tool_use" if calls else "end_turn",
            model="fake",
            tool_calls=calls,
            assistant_turn=AssistantTurn(content),
        )

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int, effort: Effort
    ) -> Completion:
        return Completion(text=messages[-1].content, stop_reason="end_turn")

    async def complete_json(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        max_tokens: int,
        effort: Effort,
    ) -> dict[str, Any]:
        # Solo el contenido del documento, no la instrucción (que menciona todos los tipos).
        match = re.search(r"<documento>(.*?)</documento>", messages[-1].content, re.DOTALL)
        text = (match.group(1) if match else messages[-1].content).lower()
        if "factura" in text:
            doc_type = "factura"
        elif "contrato" in text:
            doc_type = "contrato"
        elif "estado de cuenta" in text or "saldo" in text:
            doc_type = "estado_de_cuenta"
        else:
            doc_type = "otro"
        return {"doc_type": doc_type}

    async def transcribe_image(self, *, image_png: bytes) -> str:
        return "Texto transcrito por OCR de prueba: documento escaneado sin contenido real."
