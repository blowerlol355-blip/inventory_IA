"""Interfaz común a proveedores de LLM. El resto del código solo depende de esto."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Effort = Literal["low", "medium", "high"]


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class AssistantTurn:
    """Turno del modelo en formato nativo del proveedor. Se reenvía sin modificar dentro del
    bucle del agente (Claude exige devolver intactos sus bloques de razonamiento)."""

    content: Any


@dataclass
class ToolResults:
    results: list[ToolResult]


Message = ChatMessage | AssistantTurn | ToolResults


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass
class TextDelta:
    text: str


@dataclass
class StreamEnd:
    usage: Usage
    # "end_turn", "tool_use", "max_tokens", "refusal", ...
    stop_reason: str | None
    model: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_turn: AssistantTurn | None = None


StreamEvent = TextDelta | StreamEnd


@dataclass
class Completion:
    text: str
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None


class LLMError(Exception):
    pass


class ToolInputError(LLMError):
    """El modelo generó argumentos de herramienta que no se pudieron interpretar."""


class LLMProvider(Protocol):
    def stream(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int,
        effort: Effort,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamEvent]: ...

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int, effort: Effort
    ) -> Completion: ...

    async def complete_json(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        max_tokens: int,
        effort: Effort,
    ) -> dict[str, Any]: ...

    async def transcribe_image(self, *, image_png: bytes) -> str:
        """OCR: devuelve el texto visible en la imagen (página escaneada)."""
        ...
