"""Flujo completo de la Fase 1 contra PostgreSQL real:
registro → subida de PDF → procesamiento → pregunta → respuesta con cita (documento y página).
"""

import json
import uuid
from typing import Any

from httpx import AsyncClient

from tests.conftest import make_pdf, make_scanned_pdf

INVOICE_PAGES = [
    "<h1>FACTURA N° F-000777</h1><p>Proveedor: Suministros Andinos SpA</p>"
    "<p>Fecha de emisión: 2026-03-14</p>",
    "<h2>Totales</h2><p>Total a pagar: 4.522,10 USD. Vencimiento de la factura: 2026-04-13.</p>",
]


async def register(client: AsyncClient) -> dict[str, str]:
    email = f"admin-{uuid.uuid4().hex[:8]}@findocs-demo.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"organization_name": "Org Test", "email": email, "password": "clave-segura-1"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def parse_sse(body: str) -> list[tuple[str, Any]]:
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


async def upload(client: AsyncClient, headers: dict[str, str], pdf: bytes) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files=[("files", ("factura_777.pdf", pdf, "application/pdf"))],
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


async def ask(client: AsyncClient, headers: dict[str, str], question: str) -> dict[str, Any]:
    conv = await client.post("/api/v1/conversations", headers=headers, json={})
    assert conv.status_code == 201
    response = await client.post(
        f"/api/v1/conversations/{conv.json()['id']}/messages",
        headers=headers,
        json={"content": question},
    )
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    tools = [data for name, data in events if name == "tool"]
    assert tools and tools[0]["name"] == "search_documents", events
    assert {t["status"] for t in tools} == {"running", "done"}
    sources = [s for name, data in events if name == "sources" for s in data]
    done = [data for name, data in events if name == "done"]
    assert done, f"Sin evento done: {events}"
    return {"sources": sources, **done[0]}


async def test_upload_ask_and_get_cited_answer(client: AsyncClient) -> None:
    headers = await register(client)

    doc = await upload(client, headers, make_pdf(INVOICE_PAGES))
    detail = await client.get(f"/api/v1/documents/{doc['id']}", headers=headers)
    assert detail.json()["status"] == "ready", detail.json()["error"]
    assert detail.json()["page_count"] == 2
    assert detail.json()["doc_type"] == "factura"

    answer = await ask(client, headers, "¿Cuál es el total a pagar de la factura?")
    assert answer["citations"], answer
    cited = answer["citations"][0]
    assert cited["filename"] == "factura_777.pdf"
    assert cited["page"] == 2  # el total está en la segunda página
    assert "4.522,10" in answer["content"]

    file_url = await client.get(f"/api/v1/documents/{doc['id']}/file", headers=headers)
    assert file_url.status_code == 200
    assert file_url.json()["url"].startswith("http://storage.test/")


async def test_organizations_are_isolated(client: AsyncClient) -> None:
    owner = await register(client)
    doc = await upload(client, owner, make_pdf(INVOICE_PAGES))

    intruder = await register(client)
    response = await client.get(f"/api/v1/documents/{doc['id']}", headers=intruder)
    assert response.status_code == 404
    listing = await client.get("/api/v1/documents", headers=intruder)
    assert listing.json() == []

    answer = await ask(client, intruder, "¿Cuál es el total a pagar de la factura?")
    assert answer["sources"] == []  # nunca recibe fragmentos de otra organización
    assert answer["citations"] == []


async def test_invalid_upload_and_auth_errors_use_uniform_format(client: AsyncClient) -> None:
    headers = await register(client)
    response = await client.post(
        "/api/v1/documents",
        headers=headers,
        files=[("files", ("virus.pdf", b"MZ esto no es un pdf", "application/pdf"))],
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "invalid_files"
    assert body["details"][0]["filename"] == "virus.pdf"

    unauthorized = await client.get("/api/v1/documents")
    assert unauthorized.status_code == 401
    assert set(unauthorized.json()) == {"code", "message", "details"}


async def test_login_and_refresh(client: AsyncClient) -> None:
    email = f"user-{uuid.uuid4().hex[:8]}@findocs-demo.com"
    await client.post(
        "/api/v1/auth/register",
        json={"organization_name": "Org", "email": email, "password": "clave-segura-1"},
    )
    bad = await client.post("/api/v1/auth/login", json={"email": email, "password": "mala"})
    assert bad.status_code == 401

    login = await client.post(
        "/api/v1/auth/login", json={"email": email.upper(), "password": "clave-segura-1"}
    )
    assert login.status_code == 200
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]}
    )
    assert refreshed.status_code == 200
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    )
    assert me.json()["email"] == email
    assert me.json()["role"] == "admin"


async def test_scanned_pdf_goes_through_ocr(client: AsyncClient) -> None:
    headers = await register(client)
    doc = await upload(client, headers, make_scanned_pdf("Factura escaneada F-9"))
    detail = (await client.get(f"/api/v1/documents/{doc['id']}", headers=headers)).json()
    assert detail["status"] == "ready", detail
    assert detail["page_count"] == 1
