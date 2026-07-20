"""Provider selection — the single source of truth.

Consolidates the provider-resolution helpers that used to live in
``api/routes/llm.py`` and were re-implemented ad hoc across services. Business
logic (``services/``, ``collection/``) imports provider selection from here, not
from the API layer, so there is no service→api layering inversion. ``api/routes/
llm.py`` re-exports these for backwards compatibility with existing call sites
and route tests.

Runtime DB-backed overrides (active provider/model/key) are read lazily inside
the functions to avoid import cycles.
"""
from __future__ import annotations

from intel_platform.config import settings


async def _resolve_api_key(provider_name: str) -> str | None:
    """Resolve an API key for a provider: check DB first, then env vars."""
    from intel_platform.api.routes.admin_config import get_active_api_key
    db_key = await get_active_api_key(provider_name)
    if db_key:
        return db_key
    env_keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "cohere": settings.cohere_api_key,
    }
    return env_keys.get(provider_name) or None


def _cloud_provider_from_env():
    """Return a cloud provider built from an env-configured key, or None.

    Precedence cohere → anthropic → openai, mirroring the fallback order used
    elsewhere. Env-only and never falls back to Ollama, so callers that should
    simply *skip* LLM work when no cloud key is present (e.g. topic-label
    refinement) can treat ``None`` as "no provider". Kept as a shared helper so
    services no longer hand-roll this chain against ``settings.*_api_key``.
    """
    # Resolve settings at call time so callers that patch
    # ``intel_platform.config.settings`` (e.g. the clustering tests) are honored.
    from intel_platform.config import settings

    if settings.cohere_api_key:
        from intel_platform.llm.cohere_provider import CohereProvider
        return CohereProvider(api_key=settings.cohere_api_key)
    if settings.anthropic_api_key:
        from intel_platform.llm.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if settings.openai_api_key:
        from intel_platform.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key)
    return None


async def _get_collection_provider():
    """Provider for bulk collection work (source resolution + per-doc summaries).

    Routes to a dedicated, rate-limit-free provider (local Ollama) when
    ``collection_llm_provider`` is configured, so heavy collection runs don't
    exhaust a rate-limited cloud key. Falls back to the default provider when
    unset (e.g. deployments without a local Ollama).
    """
    prov = (getattr(settings, "collection_llm_provider", "") or "").strip()
    if prov == "ollama":
        from intel_platform.llm.ollama import OllamaProvider
        model = (getattr(settings, "collection_llm_model", "") or "").strip() or "qwen2.5:14b"
        return OllamaProvider(base_url=settings.ollama_base_url, model=model)
    return await _get_provider()


async def _get_extraction_provider():
    """Provider for LLM/hybrid entity+relationship extraction.

    Routes to a dedicated provider (local Ollama) when ``extraction_llm_provider``
    is configured, so per-document extraction doesn't drain a rate-limited cloud
    key. Falls back to the default provider when unset.
    """
    prov = (getattr(settings, "extraction_llm_provider", "") or "").strip()
    if prov == "ollama":
        from intel_platform.llm.ollama import OllamaProvider
        model = (getattr(settings, "extraction_llm_model", "") or "").strip() or "qwen2.5:14b"
        return OllamaProvider(base_url=settings.ollama_base_url, model=model)
    return await _get_provider()


async def _get_provider():
    """Get the configured LLM provider, respecting runtime overrides and DB keys."""
    from intel_platform.api.routes.admin_config import get_active_provider, get_active_model

    provider_name = get_active_provider()
    model = get_active_model()

    if provider_name == "ollama":
        from intel_platform.llm.ollama import OllamaProvider
        return OllamaProvider(base_url=settings.ollama_base_url, model=model or settings.default_llm_model or "qwen3.5:9b-q4_K_M")

    api_key = await _resolve_api_key(provider_name)
    if api_key:
        if provider_name == "cohere":
            from intel_platform.llm.cohere_provider import CohereProvider
            return CohereProvider(api_key=api_key, model=model or "command-a-plus-05-2026")
        if provider_name == "anthropic":
            from intel_platform.llm.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=api_key, model=model or "claude-sonnet-4-20250514")
        if provider_name == "openai":
            from intel_platform.llm.openai_provider import OpenAIProvider
            return OpenAIProvider(api_key=api_key, model=model or "gpt-4o")

    # Fallback: try any provider with a key (DB or env)
    for fallback in ["cohere", "anthropic", "openai"]:
        key = await _resolve_api_key(fallback)
        if key:
            if fallback == "cohere":
                from intel_platform.llm.cohere_provider import CohereProvider
                return CohereProvider(api_key=key)
            if fallback == "anthropic":
                from intel_platform.llm.anthropic import AnthropicProvider
                return AnthropicProvider(api_key=key)
            if fallback == "openai":
                from intel_platform.llm.openai_provider import OpenAIProvider
                return OpenAIProvider(api_key=key)

    # Last resort: try Ollama
    from intel_platform.llm.ollama import OllamaProvider
    return OllamaProvider(base_url=settings.ollama_base_url, model=model or settings.default_llm_model or "qwen3.5:9b-q4_K_M")
