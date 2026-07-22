"""MITRE ATT&CK® API — graph-grounded matrix, technique detail, TTP resolution,
and Navigator-layer export.

The canonical ATT&CK model lives in Neo4j as global reference nodes (see
``services/attack/``). These routes read that model joined to a project's
observed TTP/ThreatActor entities. ``POST /attack/ingest`` (admin) fetches and
loads the pinned STIX bundle; all other routes are analyst-facing reads plus the
on-demand resolver.

MITRE ATT&CK® is used under the ATT&CK Terms of Use — see
``data/attack/ATTRIBUTION.md``.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from neo4j import Driver

from intel_platform.api.deps import get_neo4j_driver, require_admin, verify_api_key
from intel_platform.services.attack import graph_ops
from intel_platform.services.attack.ingest import fetch_and_ingest

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/attack/status")
async def get_status(driver: Driver = Depends(get_neo4j_driver)):
    """Whether ATT&CK is ingested, at what version, with node counts."""
    return await asyncio.to_thread(graph_ops.attack_status, driver)


@router.post("/attack/ingest", dependencies=[Depends(require_admin)])
async def ingest(driver: Driver = Depends(get_neo4j_driver)):
    """(Admin) Fetch + parse + load the pinned ATT&CK bundle. Idempotent."""
    try:
        result = await fetch_and_ingest(driver)
    except Exception:
        # Never leak fetch/parse internals to the client.
        logger.exception("ATT&CK ingest failed")
        raise HTTPException(status_code=502, detail="Failed to fetch or load the ATT&CK dataset")
    return {"ingested": True, "version": result["version"], "counts": result["counts"]}


@router.post("/attack/resolve")
async def resolve(
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
):
    """Link this project's TTP/ThreatActor entities to canonical ATT&CK nodes."""
    return await asyncio.to_thread(graph_ops.resolve_ttps, driver, project_id)


@router.get("/attack/matrix")
async def get_matrix(
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
):
    """Full tactic → technique model with per-technique observed coverage."""
    return await asyncio.to_thread(graph_ops.get_matrix, driver, project_id)


@router.get("/attack/technique/{tid}")
async def get_technique(
    tid: str,
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
):
    """Technique detail: tactics, platforms, detection, mitigations, groups, and
    this project's entities mapped to it."""
    detail = await asyncio.to_thread(graph_ops.get_technique, driver, tid, project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Technique not found")
    return detail


@router.get("/attack/navigator-layer")
async def get_navigator_layer(
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
):
    """Download a Navigator layer v4.5 JSON scored by observed coverage."""
    layer = await asyncio.to_thread(graph_ops.navigator_layer, driver, project_id)
    filename = f"attack-navigator-{project_id[:8]}.json"
    return JSONResponse(
        content=layer,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
