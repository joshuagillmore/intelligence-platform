from fastapi import APIRouter
from intel_platform.api.deps import get_neo4j_driver
from intel_platform.models.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        neo4j_ok = True
    except Exception:
        neo4j_ok = False
    return HealthResponse(status="ok" if neo4j_ok else "degraded", neo4j_connected=neo4j_ok)
