from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class CorroborationAgreement(str, Enum):
    AGREE = "AGREE"
    PARTIAL = "PARTIAL"
    CONFLICT = "CONFLICT"


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    target_id: str
    rel_type: str
    # The project both endpoints belong to. When set, the store matches the
    # endpoints inside that project (an edge can never join two projects) and
    # stamps the edge with it. Empty for callers that have not passed it yet,
    # which keep the old unscoped match.
    project_id: str = ""
    confidence: float = 0.5
    source: str = ""
    method: str = ""
    # The source sentence(s) that assert this relationship — the in-context
    # reference surfaced by "Show Evidence". Empty when no span was captured.
    evidence: str = ""
    # Where `evidence` starts in the chunk it was extracted from, so the
    # chunk's text[evidence_offset:evidence_offset + len(evidence)] is the
    # evidence. -1 when unknown: no evidence, an edge written before offsets
    # were recorded, or a span the original text does not contain as written.
    evidence_offset: int = -1
    # The document the evidence came from, so a claim can be traced back to its
    # origin rather than stopping at a floating quotation. Empty for edges built
    # before this was carried through, and for edges with no single source.
    source_doc_id: str = ""
    # Whether this source asserts the relationship or denies it. A denial is
    # intelligence: it is what turns corroboration_agreement into CONFLICT rather
    # than being silently absorbed as further agreement.
    polarity: str = "asserts"
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    admiralty_rating: str = ""
    corroboration_count: int = 1
    corroboration_sources: list[str] = Field(default_factory=list)
    corroboration_agreement: CorroborationAgreement = CorroborationAgreement.AGREE
