from fastapi import APIRouter, Depends
from intel_platform.api.deps import verify_api_key
from intel_platform.config import settings

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/admin/config")
def get_config():
    """Return non-sensitive configuration info."""
    return {
        "llm_provider": "cohere" if settings.cohere_api_key else
                        "anthropic" if settings.anthropic_api_key else
                        "openai" if settings.openai_api_key else "none",
        "extraction_mode": settings.extraction_mode,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "neo4j_uri": settings.neo4j_uri.split("@")[-1] if "@" in settings.neo4j_uri else settings.neo4j_uri,
    }
