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


class CreatePirRequest(BaseModel):
    """Create a Priority Intelligence Requirement for a project."""
    project_id: str
    text: str
    title: str = ""
    refined_text: str = ""
    eeis: list[str] = []
    priority: str = "medium"
    status: str = "OPEN"
    created_by: str = "analyst"


class UpdatePirRequest(BaseModel):
    """Partial update — only the fields supplied are written."""
    title: str | None = None
    text: str | None = None
    refined_text: str | None = None
    eeis: list[str] | None = None
    priority: str | None = None
    status: str | None = None


class EntitySearchRequest(BaseModel):
    project_id: str
    query: str = ""
    entity_type: str | None = None
    min_confidence: float = 0.0
    limit: int = 50
    offset: int = 0
