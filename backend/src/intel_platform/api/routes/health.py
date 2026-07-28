import time
import urllib.request
import urllib.error

from fastapi import APIRouter

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.config import settings
from intel_platform.models.responses import HealthResponse

router = APIRouter()


_PROBE_TTL_SECONDS = 20.0
_probe_cache: tuple[float, bool] | None = None


def _ollama_configured() -> bool:
    """Is Ollama named on a path this deployment is configured to use?

    Gating solely on ``default_llm_provider`` under-reports the common split
    config — a cloud default with collection/extraction/embeddings offloaded to
    a local Ollama. That deployment depends on Ollama for every document it
    ingests, yet health reported ``ollama_connected: false`` with Ollama up and
    answering, which reads as "not wired up" rather than "not consulted".

    ``get_active_provider`` is consulted because the admin runtime override, not
    ``default_llm_provider``, is what ``llm/providers.py::_get_provider`` obeys.
    Imported lazily for the same reason it is there — to dodge the import cycle.
    """
    names = {
        (settings.default_llm_provider or "").strip().lower(),
        (settings.extraction_llm_provider or "").strip().lower(),
        (settings.collection_llm_provider or "").strip().lower(),
        (settings.embedding_provider or "").strip().lower(),
    }
    try:
        from intel_platform.api.routes.admin_config import get_active_provider

        names.add((get_active_provider() or "").strip().lower())
    except Exception:
        pass
    return "ollama" in names


def _ollama_is_fallback() -> bool:
    """Would the fallback chains land on Ollama even though nothing names it?

    Both chains end there when no cloud key resolves — ``providers.py`` returns
    an ``OllamaProvider`` as its last resort, and ``embeddings.py`` an
    ``OllamaEmbeddingProvider``. Keys may also live in the database, so this is a
    heuristic: it decides whether to *probe*, never whether to degrade.
    """
    return not any(
        (settings.anthropic_api_key, settings.openai_api_key, settings.cohere_api_key)
    )


def _check_ollama() -> bool:
    """Check Ollama API reachability (quick GET to /api/tags).

    Cached briefly: this is a blocking 3s-timeout call on a threadpool worker,
    and the sidebar and status bar both poll /health every 30s. Before the gate
    was widened it almost never ran; now it runs on every local stack, where
    EXTRACTION_LLM_PROVIDER=ollama.
    """
    global _probe_cache
    now = time.monotonic()
    if _probe_cache is not None and now - _probe_cache[0] < _PROBE_TTL_SECONDS:
        return _probe_cache[1]
    try:
        base = settings.ollama_base_url.rstrip("/")
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            result = True
    except Exception:
        result = False
    _probe_cache = (now, result)
    return result


@router.get("/health", response_model=HealthResponse)
def health_check():
    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        neo4j_ok = True
    except Exception:
        neo4j_ok = False

    configured = _ollama_configured()
    ollama_ok = _check_ollama() if configured or _ollama_is_fallback() else False

    # Only a *configured* Ollama being unreachable is a degradation. The fallback
    # case is inferred from the absence of env keys, which database-stored keys
    # can contradict — a guess must not manufacture a degraded status.
    if neo4j_ok and (ollama_ok or not configured):
        status = "ok"
    else:
        status = "degraded"

    return HealthResponse(status=status, neo4j_connected=neo4j_ok, ollama_connected=ollama_ok)
