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
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.deps import get_neo4j_driver, require_admin, verify_api_key
from intel_platform.db.engine import get_db
from intel_platform.services.attack import embeddings as attack_embeddings
from intel_platform.services.attack import graph_ops
from intel_platform.services.attack import mapping as attack_mapping
from intel_platform.services.attack import vuln_chain
from intel_platform.services.attack.ingest import fetch_and_ingest

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# Serialize each expensive idempotent bulk op against itself (concurrent admin
# triggers shouldn't double-fetch / double-embed). Separate locks so an in-flight
# ingest doesn't needlessly block an embed and vice-versa — they don't conflict.
_ingest_lock = asyncio.Lock()
_embed_lock = asyncio.Lock()
# Serialize the CWE/CAPEC fetch-and-load against itself (concurrent admin triggers
# shouldn't double-fetch the ~40 MB of XML); separate from _ingest_lock — the two
# datasets don't conflict.
_vuln_lock = asyncio.Lock()


@router.get("/attack/status")
async def get_status(driver: Driver = Depends(get_neo4j_driver)):
    """Whether ATT&CK is ingested, at what version, with node counts."""
    return await asyncio.to_thread(graph_ops.attack_status, driver)


@router.post("/attack/ingest", dependencies=[Depends(require_admin)])
async def ingest(driver: Driver = Depends(get_neo4j_driver)):
    """(Admin) Fetch + parse + load the pinned ATT&CK bundle. Idempotent."""
    try:
        async with _ingest_lock:
            result = await fetch_and_ingest(driver)
    except Exception:
        # Never leak fetch/parse internals to the client.
        logger.exception("ATT&CK ingest failed")
        raise HTTPException(status_code=502, detail="Failed to fetch or load the ATT&CK dataset")
    return {"ingested": True, "version": result["version"], "counts": result["counts"]}


@router.post("/attack/ingest-vuln-chain", dependencies=[Depends(require_admin)])
async def ingest_vuln_chain(driver: Driver = Depends(get_neo4j_driver)):
    """(Admin) Fetch CWE + CAPEC, load ``(:Cwe)-[:ENABLES]->(:AttackTechnique)``.

    Idempotent. Requires ATT&CK to be ingested first (edges are only created for
    techniques that already exist). Returns ``{"cwes": int, "edges": int}``.
    """
    try:
        async with _vuln_lock:
            result = await vuln_chain.ingest_vuln_chain(driver)
    except Exception:
        # Never leak fetch/parse internals to the client.
        logger.exception("CVE→ATT&CK chain ingest failed")
        raise HTTPException(status_code=502, detail="Failed to fetch or load the CWE/CAPEC datasets")
    return {"cwes": result["cwes"], "edges": result["edges"]}


@router.post("/attack/resolve-cve")
async def resolve_cve(
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
):
    """Chain this project's CVE ``Vulnerability`` entities to ATT&CK techniques.

    MERGEs ``HAS_WEAKNESS`` to the CWE reference nodes and materializes
    ``(:Vulnerability)-[:ENABLES {via:"cwe-capec"}]->(:AttackTechnique)`` for every
    technique those CWEs enable. Returns
    ``{"vulnerabilities": int, "techniques_linked": int}``.
    """
    try:
        return await asyncio.to_thread(vuln_chain.resolve_cve, driver, project_id)
    except Exception:
        logger.exception("ATT&CK CVE resolve failed")
        raise HTTPException(status_code=502, detail="Failed to resolve CVEs to ATT&CK")


@router.post("/attack/embed", dependencies=[Depends(require_admin)])
async def embed(
    driver: Driver = Depends(get_neo4j_driver),
    db: AsyncSession = Depends(get_db),
):
    """(Admin) Embed the ATT&CK technique catalog into pgvector for RAG mapping.

    Idempotent (upsert). Degrades to ``{"embedded": 0}`` if no embedding provider
    is reachable rather than 500-ing.
    """
    try:
        async with _embed_lock:
            embedded = await attack_embeddings.embed_techniques(db, driver)
            await db.commit()
    except Exception:
        logger.exception("ATT&CK technique embedding failed")
        raise HTTPException(status_code=502, detail="Failed to embed the ATT&CK technique catalog")
    return {"embedded": embedded}


@router.post("/attack/map")
async def map_ttps(
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
    db: AsyncSession = Depends(get_db),
):
    """RAG-map this project's un-T-code-resolved TTPs to ATT&CK techniques.

    Never 500s on a provider outage — degrades to skips (see
    :func:`services.attack.mapping.map_project_ttps`).
    """
    try:
        result = await attack_mapping.map_project_ttps(db, driver, project_id)
    except Exception:
        logger.exception("ATT&CK mapping failed")
        raise HTTPException(status_code=500, detail="Failed to map TTPs to ATT&CK")
    return result


@router.get("/attack/attribution")
async def get_attribution(
    project_id: str = Query(...),
    driver: Driver = Depends(get_neo4j_driver),
):
    """Candidate threat-actor groups ranked by observed-technique overlap.

    Suggestive overlap, not confirmed attribution.
    """
    return await asyncio.to_thread(graph_ops.get_attribution, driver, project_id)


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
