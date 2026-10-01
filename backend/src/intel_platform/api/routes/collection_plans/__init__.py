"""Collection plan management API routes.

Provides full CRUD for collection plans and sources, file upload ingestion
through the collection pipeline, acquisition logging, and a status dashboard.

One router per concern, mounted here behind the API key:

- ``plans``       plan and source CRUD, status transitions; ``_parse_uuid`` and
                  the plan/source serialisers the other modules share
- ``refinement``  PIR → plan generation (``/collection-plans/from-pir``)
- ``execution``   execute, cancel, execution status, activity trail
- ``uploads``     file upload through a ``file_upload`` source
- ``catalog``     acquisition log, data catalog, dashboard, connector types

Run state that is not HTTP-specific lives in ``services/plan_runs.py``.

Every public name the single-module version had, other than its logger, is
re-exported, as is ``_parse_uuid`` (the PIR and report routes import it), so
``collection_plans.<name>`` keeps working wherever it is used.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from intel_platform.api.deps import verify_api_key
from intel_platform.api.routes.collection_plans import catalog, execution, plans, refinement, uploads
from intel_platform.api.routes.collection_plans.catalog import (
    collection_dashboard,
    get_catalog_entry,
    get_catalog_preview,
    list_acquisitions,
    list_catalog,
    list_connector_types,
    list_source_acquisitions,
)
from intel_platform.api.routes.collection_plans.execution import (
    ExecuteRequest,
    cancel_plan_run,
    execute_plan_endpoint,
    get_activity,
    get_execution_status,
)
from intel_platform.api.routes.collection_plans.plans import (
    AddSourceRequest,
    CreatePlanRequest,
    UpdatePlanRequest,
    UpdateSourceRequest,
    _parse_uuid,
    activate_plan,
    add_source,
    archive_plan,
    complete_plan,
    create_plan,
    delete_plan,
    delete_source,
    get_plan,
    list_plans,
    list_sources,
    pause_plan,
    update_plan,
    update_source,
)
from intel_platform.api.routes.collection_plans.refinement import (
    SubmitPIRRequest,
    create_plan_from_pir,
    refinement_system_prompt,
)
from intel_platform.api.routes.collection_plans.uploads import upload_file_to_source
from intel_platform.services.plan_runs import current_run_events, current_run_state

__all__ = [
    "router",
    # request models
    "AddSourceRequest",
    "CreatePlanRequest",
    "ExecuteRequest",
    "SubmitPIRRequest",
    "UpdatePlanRequest",
    "UpdateSourceRequest",
    # run state (services/plan_runs.py)
    "current_run_events",
    "current_run_state",
    # helpers other modules import
    "_parse_uuid",
    "refinement_system_prompt",
    # route handlers
    "activate_plan",
    "add_source",
    "archive_plan",
    "cancel_plan_run",
    "collection_dashboard",
    "complete_plan",
    "create_plan",
    "create_plan_from_pir",
    "delete_plan",
    "delete_source",
    "execute_plan_endpoint",
    "get_activity",
    "get_catalog_entry",
    "get_catalog_preview",
    "get_execution_status",
    "get_plan",
    "list_acquisitions",
    "list_catalog",
    "list_connector_types",
    "list_plans",
    "list_source_acquisitions",
    "list_sources",
    "pause_plan",
    "update_plan",
    "update_source",
    "upload_file_to_source",
]

router = APIRouter(dependencies=[Depends(verify_api_key)])
for _module in (plans, refinement, execution, uploads, catalog):
    router.include_router(_module.router)
del _module
