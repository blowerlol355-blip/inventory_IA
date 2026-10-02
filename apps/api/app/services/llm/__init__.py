from functools import lru_cache

from app.core.config import settings
from app.services.llm.base import LLMProvider


def _split(value: str) -> list[str]:
    return [m.strip() for m in value.split(",") if m.strip()]


@lru_cache
def get_llm() -> LLMProvider:
    """Elige el proveedor según LLM_PROVIDER. Cambiar de proveedor es solo configuración."""
    if settings.llm_provider == "fake":
        from app.services.llm.fake_provider import FakeProvider

        return FakeProvider()
    if settings.llm_provider == "gemini":
        from app.services.llm.gemini_provider import GeminiProvider

        return GeminiProvider(
            model=settings.gemini_model,
            api_key=settings.gemini_api_key,
            fallback_models=_split(settings.gemini_fallback_models),
            task_models=_split(settings.gemini_task_models),
        )
    from app.services.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(model=settings.llm_model, api_key=settings.anthropic_api_key)
