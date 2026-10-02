"""Almacenamiento de archivos en Supabase Storage (API REST).

Los archivos van a un bucket PRIVADO: el navegador solo los ve mediante URLs firmadas que
expiran en minutos. La secret key de Supabase viaja en el header `apikey` y solo existe en
el servidor.
"""

import logging
from functools import lru_cache
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def signed_url(
        self, key: str, expires_seconds: int, download: str | None = None
    ) -> str: ...


class SupabaseStorage:
    def __init__(self, base_url: str, secret_key: str, bucket: str) -> None:
        self._storage_url = f"{base_url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._client = httpx.AsyncClient(
            base_url=self._storage_url, headers={"apikey": secret_key}, timeout=60
        )

    def _object_path(self, key: str) -> str:
        return f"/object/{self._bucket}/{quote(key)}"

    @staticmethod
    def _check(response: httpx.Response, action: str) -> None:
        if response.is_error:
            raise StorageError(f"{action} falló ({response.status_code}): {response.text[:200]}")

    async def ensure_bucket(self) -> None:
        """Crea el bucket privado si no existe (idempotente)."""
        response = await self._client.get(f"/bucket/{self._bucket}")
        if response.status_code == 200:
            return
        response = await self._client.post(
            "/bucket",
            json={
                "id": self._bucket,
                "name": self._bucket,
                "public": False,
                "file_size_limit": settings.max_upload_bytes,
            },
        )
        self._check(response, "Crear bucket")
        logger.info("Bucket privado '%s' creado en Supabase Storage", self._bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        response = await self._client.post(
            self._object_path(key),
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        self._check(response, "Subida")

    async def get(self, key: str) -> bytes:
        response = await self._client.get(self._object_path(key))
        self._check(response, "Descarga")
        return response.content

    async def delete(self, key: str) -> None:
        response = await self._client.request(
            "DELETE", f"/object/{self._bucket}", json={"prefixes": [key]}
        )
        self._check(response, "Borrado")

    async def signed_url(self, key: str, expires_seconds: int, download: str | None = None) -> str:
        """URL temporal. Con `download`, el navegador descarga el archivo con ese nombre."""
        response = await self._client.post(
            f"/object/sign/{self._bucket}/{quote(key)}", json={"expiresIn": expires_seconds}
        )
        self._check(response, "URL firmada")
        # La API devuelve una ruta relativa a /storage/v1 ("/object/sign/...?token=...").
        signed: str = response.json()["signedURL"]
        url = f"{self._storage_url}{signed}"
        return f"{url}&download={quote(download)}" if download else url


@lru_cache
def get_storage() -> SupabaseStorage:
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise StorageError("Configura SUPABASE_URL y SUPABASE_SECRET_KEY")
    return SupabaseStorage(
        settings.supabase_url, settings.supabase_secret_key, settings.storage_bucket
    )
