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

import logging

from intel_platform.config import settings

logger = logging.getLogger(__name__)

_CLOUD_PROVIDERS = ("cohere", "anthropic", "openai")


def _runtime_override() -> tuple[str, str]:
    """(provider, model) an admin chose at runtime in the LLM hub, else ("", "").

    Distinct from the configured default: choosing a provider in the UI is an
    explicit act, and it is the one thing precedence rules must never overrule.
    ``get_active_provider`` merges the two, so the override is read directly.
    """
    from intel_platform.api.routes import admin_config

    override = getattr(admin_config, "_llm_override", None) or {}
    return (
        (override.get("provider") or "").strip().lower(),
        (override.get("model") or "").strip(),
    )


def _build_cloud(name: str, key: str, model: str = ""):
    kw = {"model": model} if model else {}
    if name == "cohere":
        from intel_platform.llm.cohere_provider import CohereProvider
        return CohereProvider(api_key=key, **kw)
    if name == "anthropic":
        from intel_platform.llm.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=key, **kw)
    if name == "openai":
        from intel_platform.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=key, **kw)
    return None


async def _key_or_env(name: str) -> str | None:
    """``_resolve_api_key`` (DB, then env), degrading to the env key alone when
    the key store cannot be read — a Postgres outage should not hide a key
    that is sitting in the environment."""
    try:
        return await _resolve_api_key(name)
    except Exception:
        logger.warning("API key store unavailable; using env key for %s if set", name, exc_info=True)
        # Read at call time, like _cloud_provider_from_env, so callers that
        # patch intel_platform.config.settings are honoured.
        from intel_platform.config import settings as current

        return getattr(current, f"{name}_api_key", "") or None


async def _first_cloud_provider(preferred: str = "", preferred_model: str = ""):
    """A cloud provider from DB or env keys: ``preferred`` first (with its model),
    then cohere -> anthropic -> openai at their default models. None if no key."""
    order = [preferred] if preferred in _CLOUD_PROVIDERS else []
    order += [p for p in _CLOUD_PROVIDERS if p not in order]
    for name in order:
        key = await _key_or_env(name)
        if key:
            return _build_cloud(name, key, preferred_model if name == preferred else "")
    return None


def _collection_preference() -> str:
    """``collection_llm_preference``: "cloud-first" (default) or "local-first"."""
    raw = (getattr(settings, "collection_llm_preference", "cloud-first") or "cloud-first")
    value = raw.strip().lower().replace("_", "-")
    return "local-first" if value.startswith("local") else "cloud-first"


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
    """Provider for bulk collection work (source resolution, per-doc summaries,
    and the agentic loop's structured steps). The one place collection
    precedence is decided — ``collection/agentic.py`` should call this rather
    than re-deriving it.

    In order:

    1. ``collection_llm_provider=ollama`` → local Ollama (``collection_llm_model``),
       so heavy runs don't exhaust a rate-limited cloud key. Any other non-empty
       value is an explicit collection choice too and disables step 3.
    2. The default provider (``_get_provider``: runtime override, DB keys, env).
    3. If that is Ollama *only because it is the configured default*, and
       ``collection_llm_preference`` is "cloud-first" (the default), a cloud key
       from the key store or env replaces it — structured collection output is
       more reliable from a cloud model. "local-first" turns this off.

    An admin's runtime choice of Ollama is never overridden: that is an explicit
    act, and swapping it for whichever cloud key exists is what
    ``_get_agentic_provider`` used to do.
    """
    prov = (getattr(settings, "collection_llm_provider", "") or "").strip()
    if prov == "ollama":
        from intel_platform.llm.ollama import OllamaProvider
        model = (getattr(settings, "collection_llm_model", "") or "").strip() or "qwen2.5:14b"
        return OllamaProvider(base_url=settings.ollama_base_url, model=model)

    provider = await _get_provider()
    if prov or not provider.name().startswith("ollama"):
        return provider
    if _runtime_override()[0] == "ollama":
        logger.info("Collection provider: %s (chosen at runtime)", provider.name())
        return provider
    if _collection_preference() == "local-first":
        return provider

    try:
        cloud = await _first_cloud_provider()
    except Exception:
        logger.warning("Cloud provider lookup failed; collection stays on %s", provider.name(), exc_info=True)
        return provider
    if cloud is not None:
        logger.info("Collection provider: %s (cloud-first over %s)", cloud.name(), provider.name())
        return cloud
    return provider


async def _get_topics_provider():
    """Provider for topic-label refinement, or None to keep keyword labels.

    Refinement is one call per node — 31 for a thirty-child tree — which is the
    same shape as collection work: high volume, low value per call, and the
    first thing to exhaust a rate-limited cloud key. On a live run every one of
    31 refinements failed with HTTP 429 from a Cohere trial key (20/min), the
    endpoint spent 19.3s of a 20.6s response failing, and the analyst saw topics
    named "wikipedia / wiki / org" — raw TF-IDF keywords off URL fragments.

    In order: ``topics_llm_provider=ollama`` or an admin's runtime choice of
    Ollama → local Ollama; otherwise a cloud provider — the active one first
    (runtime override, else ``default_llm_provider``) with its model, then
    cohere → anthropic → openai — using keys from the key store as well as the
    environment. None when there is no key, so the caller keeps keyword labels
    and reports ``label_source`` accordingly; the configured-default Ollama is
    deliberately not a fallback here.
    """
    from intel_platform.config import settings

    override_provider, override_model = _runtime_override()
    prov = (getattr(settings, "topics_llm_provider", "") or "").strip().lower()
    if prov == "ollama" or override_provider == "ollama":
        from intel_platform.llm.ollama import OllamaProvider
        model = (
            (getattr(settings, "topics_llm_model", "") or "").strip()
            or (override_model if override_provider == "ollama" else "")
            or "qwen2.5:14b"
        )
        return OllamaProvider(base_url=settings.ollama_base_url, model=model)

    if override_provider:
        active, active_model = override_provider, override_model
    else:
        active = (getattr(settings, "default_llm_provider", "") or "").strip().lower()
        active_model = (getattr(settings, "default_llm_model", "") or "").strip()
    return await _first_cloud_provider(active, active_model)


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
