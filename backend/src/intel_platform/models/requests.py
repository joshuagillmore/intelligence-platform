from pydantic import BaseModel, Field


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


# Elements per requirement. The refinement asks for 3-5 and the extractor caps
# at 8; this is the outer bound on what the API will accept. It exists because
# assessment now does one retrieval *per element*, so an unbounded list is
# unbounded database work — 300 elements would be 300 sequential pgvector
# queries. A requirement decomposed into more parts than this is not a
# requirement, it is a collection plan.
MAX_EEIS = 32


class CreatePirRequest(BaseModel):
    """Create a Priority Intelligence Requirement for a project."""
    project_id: str
    text: str
    title: str = ""
    refined_text: str = ""
    eeis: list[str] = Field(default_factory=list, max_length=MAX_EEIS)
    priority: str = "medium"
    status: str = "OPEN"
    created_by: str = "analyst"


class UpdatePirRequest(BaseModel):
    """Partial update — only the fields supplied are written."""
    title: str | None = None
    text: str | None = None
    refined_text: str | None = None
    eeis: list[str] | None = Field(default=None, max_length=MAX_EEIS)
    priority: str | None = None
    status: str | None = None


class EntitySearchRequest(BaseModel):
    project_id: str
    query: str = ""
    entity_type: str | None = None
    min_confidence: float = 0.0
    limit: int = 50
    offset: int = 0
