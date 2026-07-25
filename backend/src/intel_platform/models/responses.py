from pydantic import BaseModel


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    classification_level: str
    priority: str
    status: str
    entity_count: int = 0
    relationship_count: int = 0
    document_count: int = 0
    collection_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class PirPlanLink(BaseModel):
    """A collection plan raised against a PIR — the next link in the cycle."""
    id: str
    name: str
    status: str
    source_count: int = 0
    records_acquired: int = 0
    created_at: str = ""


class PirResponse(BaseModel):
    id: str
    project_id: str
    title: str = ""
    text: str = ""
    refined_text: str = ""
    eeis: list[str] = []
    priority: str = "medium"
    status: str = "OPEN"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    plan_count: int = 0
    plans: list[PirPlanLink] = []


class EntityResponse(BaseModel):
    id: str
    name: str
    entity_type: str
    properties: dict = {}
    confidence: float = 0.0
    corroboration_count: int = 0


class GraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    node_count: int
    edge_count: int


class HealthResponse(BaseModel):
    status: str
    neo4j_connected: bool
    ollama_connected: bool = False
    version: str = "0.1.0"
