"""Agente con herramientas de archivos, contra PostgreSQL real.

Un proveedor "guionado" reemplaza a Claude: devuelve, paso a paso, las llamadas a
herramientas que haría el modelo. Así se prueba el bucle del agente, la ejecución de las
herramientas, los eventos SSE y la persistencia, sin red ni costo.
"""

import io
import zipfile
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.agent import agent as agent_module
from app.services.llm.base import (
    AssistantTurn,
    Message,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolResults,
    Usage,
)
from tests.conftest import MemoryStorage, make_pdf
from tests.test_api_flow import INVOICE_PAGES, parse_sse, register, upload


class ScriptedProvider:
    """Cada elemento del guion es una lista de llamadas a herramientas o un texto final."""

    def __init__(self, script: list[list[tuple[str, dict[str, Any]]] | str]) -> None:
        self.script = script
        self.tool_results: list[ToolResults] = []

    async def stream(self, *, messages: list[Message], **_: Any) -> AsyncIterator[StreamEvent]:
        if isinstance(messages[-1], ToolResults):
            self.tool_results.append(messages[-1])
        step = self.script.pop(0)
        if isinstance(step, str):
            yield TextDelta(step)
            yield StreamEnd(Usage(10, 5), "end_turn", assistant_turn=AssistantTurn([]))
            return
        calls = [ToolCall(f"call-{i}", name, args) for i, (name, args) in enumerate(step)]
        yield StreamEnd(
            Usage(10, 5), "tool_use", tool_calls=calls, assistant_turn=AssistantTurn([])
        )


async def _ask(
    client: AsyncClient, headers: dict[str, str], question: str
) -> list[tuple[str, Any]]:
    conv = (await client.post("/api/v1/conversations", headers=headers, json={})).json()
    response = await client.post(
        f"/api/v1/conversations/{conv['id']}/messages", headers=headers, json={"content": question}
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


async def _upload_csv(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files=[("files", ("movimientos.csv", b"fecha;monto\n2026-01-02;150.5\n", "text/csv"))],
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


async def test_agent_converts_and_zips_files(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await register(client)
    invoice = await upload(client, headers, make_pdf(INVOICE_PAGES))
    movements = await _upload_csv(client, headers)

    provider = ScriptedProvider(
        [
            [("list_documents", {"doc_type": "todos", "name_contains": ""})],
            [("convert_document", {"file_id": movements["id"], "target_format": "xlsx"})],
            [
                (
                    "compress_files",
                    {
                        "file_ids": [invoice["id"], movements["id"]],
                        "mode": "zip",
                        "zip_name": "lote_marzo",
                    },
                )
            ],
            "Listo: creé movimientos.xlsx y lote_marzo.zip.",
        ]
    )
    monkeypatch.setattr(agent_module, "get_llm", lambda: provider)

    events = await _ask(client, headers, "Convierte el CSV a Excel y comprime todo en un ZIP")

    listing = provider.tool_results[0].results[0].content
    assert f"id={movements['id']}" in listing and "convertible a: pdf, txt, xlsx" in listing
    files = [data for name, data in events if name == "file"]
    assert [f["filename"] for f in files] == ["movimientos.xlsx", "lote_marzo.zip"]
    done = next(data for name, data in events if name == "done")
    assert [a["filename"] for a in done["attachments"]] == ["movimientos.xlsx", "lote_marzo.zip"]

    listed = (await client.get("/api/v1/files", headers=headers)).json()
    assert {f["filename"] for f in listed} == {"movimientos.xlsx", "lote_marzo.zip"}
    zip_file = next(f for f in listed if f["operation"] == "zip")
    assert {s["filename"] for s in zip_file["sources"]} == {"factura_777.pdf", "movimientos.csv"}

    url = (await client.get(f"/api/v1/files/{zip_file['id']}/url", headers=headers)).json()
    assert "download=lote_marzo.zip" in url["url"]

    # El ZIP guardado contiene los dos archivos originales.
    storage = client._transport.app.dependency_overrides  # type: ignore[attr-defined]
    memory: MemoryStorage = next(v for v in storage.values() if callable(v))()
    stored = next(data for key, data in memory.files.items() if key.endswith("lote_marzo.zip"))
    assert sorted(zipfile.ZipFile(io.BytesIO(stored)).namelist()) == [
        "factura_777.pdf",
        "movimientos.csv",
    ]


async def test_agent_cannot_touch_files_of_another_organization(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await register(client)
    invoice = await upload(client, owner, make_pdf(INVOICE_PAGES))

    intruder = await register(client)
    provider = ScriptedProvider(
        [
            [("convert_document", {"file_id": invoice["id"], "target_format": "docx"})],
            "No pude.",
        ]
    )
    monkeypatch.setattr(agent_module, "get_llm", lambda: provider)
    events = await _ask(client, intruder, "Convierte la factura 777 a Word")

    finished = [d for n, d in events if n == "tool" and d["status"] != "running"]
    assert finished[0]["status"] == "error"
    result = provider.tool_results[0].results[0]
    assert result.is_error and "No encontré estos archivos" in result.content
    assert not [d for n, d in events if n == "file"]
    assert (await client.get("/api/v1/files", headers=intruder)).json() == []


async def test_invalid_tool_arguments_are_reported_to_the_model(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await register(client)
    provider = ScriptedProvider(
        [
            [("convert_document", {"file_id": "no-es-un-uuid", "target_format": "docx"})],
            "Necesito un id válido.",
        ]
    )
    monkeypatch.setattr(agent_module, "get_llm", lambda: provider)
    await _ask(client, headers, "convierte algo")
    result = provider.tool_results[0].results[0]
    assert result.is_error and "Argumentos inválidos" in result.content
