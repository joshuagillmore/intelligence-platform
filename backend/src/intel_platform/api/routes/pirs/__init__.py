"""Priority Intelligence Requirement (PIR) routes — the requirements spine.

A PIR is what a project is trying to answer. It is persisted per project and
carries the chain forward: every collection plan raised against it stores its
`pir_id`, so a PIR reports back the plans it drove and what they acquired.

Lives in Postgres alongside `collection_plans` (see `db/models.Pir`): the plan is
the thing a PIR drives, and keeping both in one store makes PIR → plan a join
rather than a cross-datastore lookup.

One router per concern, mounted here behind the API key:

- ``crud``          create, list, read, update, delete; ``get_or_create_pir``
- ``requirements``  per-element (EEI) collection state
- ``assess``        the satisfaction judge's route; the judging itself is
                    ``services/pir_judge``

Every public name the single-module version had, other than its logger, is
re-exported, so ``pirs.<name>`` keeps working wherever it is used.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from intel_platform.api.deps import verify_api_key
from intel_platform.api.routes.pirs import assess, crud, requirements
from intel_platform.api.routes.pirs.assess import AssessPirRequest, assess_pir
from intel_platform.api.routes.pirs.crud import (
    TITLE_MAX,
    create_pir,
    delete_pir,
    derive_title,
    get_or_create_pir,
    get_pir,
    list_pirs,
    update_pir,
)
from intel_platform.api.routes.pirs.requirements import get_pir_requirements
from intel_platform.services.pir_judge import PassageEvidence, extract_eeis, parse_verdicts

__all__ = [
    "router",
    "AssessPirRequest",
    "PassageEvidence",
    "TITLE_MAX",
    "assess_pir",
    "create_pir",
    "delete_pir",
    "derive_title",
    "extract_eeis",
    "get_or_create_pir",
    "get_pir",
    "get_pir_requirements",
    "list_pirs",
    "parse_verdicts",
    "update_pir",
]

router = APIRouter(dependencies=[Depends(verify_api_key)])
for _module in (crud, requirements, assess):
    router.include_router(_module.router)
del _module
