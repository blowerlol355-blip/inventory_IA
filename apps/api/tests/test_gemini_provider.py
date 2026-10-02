"""Proveedor de Gemini sin red: un cliente simulado devuelve respuestas reales del SDK."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from google.genai import types

from app.services.llm.base import (
    AssistantTurn,
    ChatMessage,
    StreamEnd,
    TextDelta,
    ToolResult,
    ToolResults,
    ToolSpec,
)
from app.services.llm.gemini_provider import GeminiProvider, _to_contents


def response(parts: list[types.Part], finish: str | None = None) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=types.FinishReason(finish) if finish else None,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=5
        ),
    )


class FakeModels:
    def __init__(self, chunks: list[types.GenerateContentResponse]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, Any]] = []

    async def generate_content_stream(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.calls.append(kwargs)

        async def gen() -> AsyncIterator[types.GenerateContentResponse]:
            for chunk in self.chunks:
                yield chunk

        return gen()

    async def generate_content(self, **kwargs: Any) -> types.GenerateContentResponse:
        self.calls.append(kwargs)
        return self.chunks[0]


def provider_with(chunks: list[types.GenerateContentResponse]) -> tuple[GeminiProvider, Any]:
    provider = GeminiProvider(model="gemini-2.5-flash", api_key="x")
    models = FakeModels(chunks)
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=models))  # type: ignore[assignment]
    return provider, models


TOOL = ToolSpec(
    name="search_documents",
    description="Busca",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
)


async def test_stream_text_then_tool_call_and_history_roundtrip() -> None:
    call = types.Part(
        function_call=types.FunctionCall(name="search_documents", args={"query": "marzo"}),
        thought_signature=b"firma",
    )
    provider, models = provider_with(
        [response([types.Part(text="Busco ")]), response([call], "STOP")]
    )
    events = [
        e
        async for e in provider.stream(
            system="s",
            messages=[ChatMessage("user", "¿Total de marzo?")],
            max_tokens=100,
            effort="medium",
            tools=[TOOL],
        )
    ]
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Busco "]
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.stop_reason == "tool_use"
    assert end.usage.input_tokens == 10
    [tool_call] = end.tool_calls
    assert tool_call.name == "search_documents" and tool_call.input == {"query": "marzo"}

    config = models.calls[0]["config"]
    assert config.thinking_config.thinking_budget == 1024
    assert config.tools[0].function_declarations[0].name == "search_documents"

    # El turno del modelo se reenvía intacto (con la firma) y la respuesta lleva el nombre.
    assert end.assistant_turn is not None
    contents = _to_contents(
        [
            ChatMessage("user", "¿Total de marzo?"),
            end.assistant_turn,
            ToolResults([ToolResult(tool_call.id, "[1] factura...")]),
        ]
    )
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[1].thought_signature == b"firma"  # type: ignore[index]
    fr = contents[2].parts[0].function_response  # type: ignore[index]
    assert fr is not None and fr.name == "search_documents"
    assert fr.response == {"result": "[1] factura..."}


async def test_stop_reasons() -> None:
    provider, _ = provider_with([response([types.Part(text="...")], "MAX_TOKENS")])
    events = [
        e
        async for e in provider.stream(
            system="s", messages=[ChatMessage("user", "x")], max_tokens=5, effort="low"
        )
    ]
    assert isinstance(events[-1], StreamEnd) and events[-1].stop_reason == "max_tokens"

    provider, _ = provider_with([response([], "SAFETY")])
    events = [
        e
        async for e in provider.stream(
            system="s", messages=[ChatMessage("user", "x")], max_tokens=5, effort="low"
        )
    ]
    assert isinstance(events[-1], StreamEnd) and events[-1].stop_reason == "refusal"


async def test_complete_json_uses_schema() -> None:
    provider, models = provider_with([response([types.Part(text='{"type": "factura"}')], "STOP")])
    schema = {"type": "object", "properties": {"type": {"type": "string"}}}
    data = await provider.complete_json(
        system="s", messages=[ChatMessage("user", "x")], schema=schema, max_tokens=50, effort="low"
    )
    assert data == {"type": "factura"}
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert config.thinking_config.thinking_budget == 0


def test_tool_error_result_marked() -> None:
    turn = AssistantTurn(
        (types.Content(role="model", parts=[]), {"c1": ("convert_document", None)})
    )
    contents = _to_contents([turn, ToolResults([ToolResult("c1", "no existe", is_error=True)])])
    fr = contents[1].parts[0].function_response  # type: ignore[index]
    assert (
        fr is not None and fr.name == "convert_document" and fr.response == {"error": "no existe"}
    )


async def test_quota_or_overload_switches_model_and_pauses_it() -> None:
    from google.genai import errors

    provider = GeminiProvider(
        model="principal", api_key="x", fallback_models=["respaldo"], task_models=["ligero"]
    )
    models = FakeModels([response([types.Part(text="ok")], "STOP")])
    original_stream = models.generate_content_stream
    original_generate = models.generate_content

    async def flaky_stream(**kwargs: Any) -> AsyncIterator[Any]:
        if kwargs["model"] == "principal":
            models.calls.append(kwargs)
            raise errors.ServerError(503, {"error": {"message": "alta demanda"}})
        return await original_stream(**kwargs)

    async def flaky_generate(**kwargs: Any) -> types.GenerateContentResponse:
        if kwargs["model"] == "ligero":
            models.calls.append(kwargs)
            raise errors.ClientError(429, {"error": {"message": "cuota"}})
        return await original_generate(**kwargs)

    models.generate_content_stream = flaky_stream  # type: ignore[method-assign]
    models.generate_content = flaky_generate  # type: ignore[method-assign]
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=models))  # type: ignore[assignment]

    async def ask() -> StreamEnd:
        events = [
            e
            async for e in provider.stream(
                system="s", messages=[ChatMessage("user", "x")], max_tokens=5, effort="low"
            )
        ]
        assert isinstance(events[-1], StreamEnd)
        return events[-1]

    assert (await ask()).model == "respaldo"
    # El principal queda en pausa: la segunda pregunta va directo al respaldo.
    assert (await ask()).model == "respaldo"
    assert [c["model"] for c in models.calls] == ["principal", "respaldo", "respaldo"]

    # Tareas internas: primero el modelo ligero; sin cuota, el siguiente de la cadena.
    models.calls.clear()
    models.chunks = [response([types.Part(text="{}")], "STOP")]
    await provider.complete_json(
        system="s", messages=[ChatMessage("user", "x")], schema={}, max_tokens=5, effort="low"
    )
    assert [c["model"] for c in models.calls] == ["ligero", "respaldo"]
