"""Comprueba que las claves de IA funcionan: python -m app.scripts.check_ai

Hace una llamada mínima al LLM y otra al modelo de embeddings configurados.
"""

import asyncio
import sys

from app.core.config import settings
from app.services.llm import get_llm
from app.services.llm.base import ChatMessage
from app.services.retrieval.embeddings import get_embedder


async def check_llm() -> bool:
    if settings.llm_provider == "fake":
        print("- LLM: LLM_PROVIDER=fake (modo de prueba, no se llama a la API)")
        return False
    provider, model, key, key_name = {
        "gemini": ("Gemini", settings.gemini_model, settings.gemini_api_key, "GEMINI_API_KEY"),
        "anthropic": (
            "Claude",
            settings.llm_model,
            settings.anthropic_api_key,
            "ANTHROPIC_API_KEY",
        ),
    }[settings.llm_provider]
    if not key:
        print(f"- {provider}: falta {key_name} en .env")
        return False
    try:
        result = await get_llm().complete(
            system="Responde en una sola palabra.",
            messages=[ChatMessage(role="user", content="¿Funciona la conexión? Di 'sí'.")],
            max_tokens=200,
            effort="low",
        )
    except Exception as exc:
        print(f"- {provider}: ERROR {exc}")
        return False
    print(f"- {provider} ({model}): OK -> {result.text.strip()!r}")
    return True


async def check_embeddings() -> bool:
    if settings.embedding_provider == "hash":
        print("- Embeddings: EMBEDDING_PROVIDER=hash (modo de prueba, no se llama a la API)")
        return False
    provider, model, key, key_name = {
        "gemini": (
            "Gemini embeddings",
            settings.gemini_embedding_model,
            settings.gemini_api_key,
            "GEMINI_API_KEY",
        ),
        "voyage": ("Voyage", settings.embedding_model, settings.voyage_api_key, "VOYAGE_API_KEY"),
    }[settings.embedding_provider]
    if not key:
        print(f"- {provider}: falta {key_name} en .env")
        return False
    try:
        vector = await get_embedder().embed_query("total facturado en marzo")
    except Exception as exc:
        print(f"- {provider}: ERROR {exc}")
        return False
    print(f"- {provider} ({model}): OK -> vector de {len(vector)} dimensiones")
    return True


async def main() -> int:
    llm_ok, emb_ok = await asyncio.gather(check_llm(), check_embeddings())
    return 0 if llm_ok and emb_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
