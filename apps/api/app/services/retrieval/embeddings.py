"""Embeddings de texto. Producción: Gemini (gratis) o Voyage AI. Tests: hashing determinista."""

import hashlib
import math
from functools import lru_cache
from typing import Protocol, cast

import voyageai
import voyageai.error
from google import genai
from google.genai import errors, types

from app.core.config import settings


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class VoyageEmbedder:
    # Muy por debajo de los límites por petición (1.000 textos / 320K tokens en voyage-4).
    BATCH_SIZE = 64

    def __init__(self, model: str, dim: int, api_key: str | None) -> None:
        self.dim = dim
        self._model = model
        self._client = voyageai.AsyncClient(api_key=api_key, max_retries=4)

    async def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            try:
                result = await self._client.embed(
                    texts[start : start + self.BATCH_SIZE],
                    model=self._model,
                    input_type=input_type,
                    output_dimension=self.dim,
                )
            except voyageai.error.VoyageError as exc:
                raise EmbeddingError(f"Voyage AI: {exc}") from exc
            vectors.extend([float(v) for v in emb] for emb in result.embeddings)
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "document")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query"))[0]


class GeminiEmbedder:
    """gemini-embedding-001 (multilingüe). Con una dimensión menor a la nativa (3072) los
    vectores no vienen normalizados: se normalizan para que la distancia coseno sea coherente."""

    BATCH_SIZE = 100  # máximo de textos por petición

    def __init__(self, model: str, dim: int, api_key: str | None) -> None:
        self.dim = dim
        self._model = model
        retry = types.HttpRetryOptions(
            attempts=6, initial_delay=2.0, max_delay=60.0, http_status_codes=[429, 500, 503]
        )
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(retry_options=retry)
        )

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            try:
                result = await self._client.aio.models.embed_content(
                    model=self._model,
                    contents=cast(types.ContentListUnion, texts[start : start + self.BATCH_SIZE]),
                    config=types.EmbedContentConfig(
                        task_type=task_type, output_dimensionality=self.dim
                    ),
                )
            except errors.APIError as exc:
                raise EmbeddingError(f"Gemini embeddings: {exc}") from exc
            for emb in result.embeddings or []:
                values = emb.values or []
                norm = math.sqrt(sum(v * v for v in values)) or 1.0
                vectors.append([v / norm for v in values])
        if len(vectors) != len(texts):
            raise EmbeddingError("Gemini devolvió un número inesperado de vectores")
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


class HashEmbedder:
    """Embedder determinista sin red, solo para tests: bolsa de palabras con hashing."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in text.lower().split():
            digest = hashlib.md5(word.strip(".,:;¿?¡!()").encode()).digest()
            vec[int.from_bytes(digest[:4], "little") % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@lru_cache
def get_embedder() -> Embedder:
    if settings.embedding_provider == "hash":
        return HashEmbedder(settings.embedding_dim)
    if settings.embedding_provider == "gemini":
        return GeminiEmbedder(
            settings.gemini_embedding_model, settings.embedding_dim, settings.gemini_api_key
        )
    return VoyageEmbedder(settings.embedding_model, settings.embedding_dim, settings.voyage_api_key)
