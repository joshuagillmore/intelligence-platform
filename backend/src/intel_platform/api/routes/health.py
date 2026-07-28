import urllib.request
import urllib.error

from fastapi import APIRouter

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.config import settings
from intel_platform.models.responses import HealthResponse

router = APIRouter()


def _ollama_in_use() -> bool:
    """Is Ollama on a path this deployment actually depends on?

    Gating solely on ``default_llm_provider`` under-reports the common split
    config — a cloud default with collection/extraction/embeddings offloaded to
    a local Ollama. That deployment depends on Ollama for every document it
    ingests, yet health reported ``ollama_connected: false`` with Ollama up and
    answering, which reads as "not wired up" rather than "not consulted".
    """
    return "ollama" in {
        (settings.default_llm_provider or "").strip(),
        (settings.extraction_llm_provider or "").strip(),
        (settings.collection_llm_provider or "").strip(),
        (settings.embedding_provider or "").strip(),
    }


def _check_ollama() -> bool:
    """Check Ollama API reachability (quick GET to /api/tags)."""
    try:
        base = settings.ollama_base_url.rstrip("/")
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health_check():
    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        neo4j_ok = True
    except Exception:
        neo4j_ok = False

    ollama_needed = _ollama_in_use()
    ollama_ok = _check_ollama() if ollama_needed else False

    if neo4j_ok and (ollama_ok or not ollama_needed):
        status = "ok"
    else:
        status = "degraded"

    return HealthResponse(status=status, neo4j_connected=neo4j_ok, ollama_connected=ollama_ok)
