"""Acceso de demostración: visitantes viewer en una organización compartida."""

import uuid

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import make_pdf


async def create_owner(client: AsyncClient) -> tuple[str, dict[str, str]]:
    email = f"demo-{uuid.uuid4().hex[:8]}@findocs-demo.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={"organization_name": "FinDocs Demo", "email": email, "password": "clave-segura-1"},
    )
    assert response.status_code == 201, response.text
    return email, {"Authorization": f"Bearer {response.json()['access_token']}"}


async def visit(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/v1/auth/demo")
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_demo_disabled_without_owner(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_owner_email", None)
    options = await client.get("/api/v1/auth/options")
    assert options.json() == {"registration": True, "demo": False}
    response = await client.post("/api/v1/auth/demo")
    assert response.status_code == 404
    assert response.json()["code"] == "demo_unavailable"


async def test_visitors_share_documents_but_not_conversations(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_email, owner = await create_owner(client)
    monkeypatch.setattr(settings, "demo_owner_email", owner_email)
    assert (await client.get("/api/v1/auth/options")).json()["demo"] is True

    upload = await client.post(
        "/api/v1/documents",
        headers=owner,
        files=[("files", ("factura.pdf", make_pdf(["<p>Factura F-1</p>"]), "application/pdf"))],
    )
    assert upload.status_code == 201

    first, second = await visit(client), await visit(client)
    me_first = (await client.get("/api/v1/auth/me", headers=first)).json()
    me_second = (await client.get("/api/v1/auth/me", headers=second)).json()
    owner_org = (await client.get("/api/v1/auth/me", headers=owner)).json()["organization_id"]
    assert me_first["role"] == "viewer" and me_first["organization_id"] == owner_org
    assert me_first["id"] != me_second["id"]

    # Ven los documentos de la organización demo...
    docs = (await client.get("/api/v1/documents", headers=first)).json()
    assert [d["filename"] for d in docs] == ["factura.pdf"]
    # ...pero no pueden subir ni borrar.
    denied = await client.post(
        "/api/v1/documents",
        headers=first,
        files=[("files", ("otra.pdf", make_pdf(["<p>x</p>"]), "application/pdf"))],
    )
    assert denied.status_code == 403
    assert (
        await client.delete(f"/api/v1/documents/{docs[0]['id']}", headers=first)
    ).status_code == 403

    # Cada visitante tiene sus propias conversaciones.
    await client.post("/api/v1/conversations", headers=first, json={})
    assert len((await client.get("/api/v1/conversations", headers=first)).json()) == 1
    assert (await client.get("/api/v1/conversations", headers=second)).json() == []


async def test_registration_can_be_closed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "allow_registration", False)
    assert (await client.get("/api/v1/auth/options")).json()["registration"] is False
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Otra",
            "email": f"x-{uuid.uuid4().hex[:6]}@findocs-demo.com",
            "password": "clave-segura-1",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "registration_closed"
