import urllib.request
import urllib.error

from fastapi import APIRouter

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.config import settings
from intel_platform.models.responses import HealthResponse

router = APIRouter()


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

    ollama_ok = _check_ollama() if settings.default_llm_provider == "ollama" else False

    if neo4j_ok and (ollama_ok or settings.default_llm_provider != "ollama"):
        status = "ok"
    else:
        status = "degraded"

    return HealthResponse(status=status, neo4j_connected=neo4j_ok, ollama_connected=ollama_ok)
