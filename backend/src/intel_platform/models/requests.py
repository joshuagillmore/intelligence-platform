from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    classification_level: str = "UNCLASSIFIED"
    priority: str = "medium"


class IngestDocumentRequest(BaseModel):
    project_id: str
    content: str | None = None
    url: str | None = None
    reliability_rating: str = "C3"


class EntitySearchRequest(BaseModel):
    project_id: str
    query: str = ""
    entity_type: str | None = None
    min_confidence: float = 0.0
    limit: int = 50
    offset: int = 0
