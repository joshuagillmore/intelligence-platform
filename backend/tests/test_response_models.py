"""Every API operation declares the JSON it returns, and declaring it changed nothing.

The OpenAPI schema is the frontend's contract (`npm run gen:api` builds
`api.generated.ts` from it). A route without a `response_model` publishes an
empty schema there, and the frontend can only type its body as `unknown`.

1. Every operation in `app.openapi()` declares a schema for its success status.
2. Against a seeded project, every GET that takes only path and query
   parameters is called through the TestClient, and:
   - it answers 200 and its body validates against the declared model;
   - the declared model changed nothing. FastAPI validates a handler's return
     value through the model and sends what the model serialises, so a model
     missing a field would silently delete it from the response, and an
     optional field would add a `null` the handler never sent. Each response is
     compared with the handler's own value (`jsonable_encoder`, what FastAPI
     sent before any model was declared): no key dropped, none added, no value
     changed. A route that leaves keys out declares them optional and sets
     `response_model_exclude_unset`, so what it sends stays what it returned.

Graph data is written under this run's prefix (`tests/ids.py`); Postgres rows
are removed by project id. The Postgres-backed routes skip without an exported
`POSTGRES_URL`, as `tests/pg.py` does. Nothing here reaches the network: the
Overpass reply is canned and the D3FEND lookup is served from its cache.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fastapi.routing as fastapi_routing
import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from pydantic import TypeAdapter

from intel_platform.api.app import app
from intel_platform.config import settings
from tests import pg
from tests.ids import tp

client = TestClient(app)
HEADERS = {"Authorization": f"Bearer {settings.api_key}"}

PROJECT = tp("response-models")
# A technique id no real ATT&CK release uses, so its cached D3FEND row is ours.
D3FEND_TID = "T9999.998"
API_KEY_PROVIDER = tp("provider")

SPEC = app.openapi()


# ---------------------------------------------------------------------------
# 1. Every operation declares its response
# ---------------------------------------------------------------------------

def _success_schema(operation: dict) -> dict | None:
    for status, response in operation.get("responses", {}).items():
        if status.startswith("2"):
            for media in (response.get("content") or {}).values():
                if media.get("schema"):
                    return media["schema"]
    return None


def test_every_operation_declares_its_response():
    missing = [
        f"{method.upper()} {path}"
        for path, item in SPEC["paths"].items()
        for method, operation in item.items()
        if not _success_schema(operation)
    ]
    assert not missing, f"{len(missing)} operation(s) declare no response schema: {missing}"


# ---------------------------------------------------------------------------
# 2. Every GET, called against a seeded project
# ---------------------------------------------------------------------------

def _plain_get_paths() -> list[str]:
    """GET operations whose parameters are only path and query parameters."""
    out = []
    for path, item in SPEC["paths"].items():
        operation = item.get("get")
        if operation is None or "requestBody" in operation:
            continue
        if all(p.get("in") in ("path", "query") for p in operation.get("parameters", [])):
            out.append(path)
    return sorted(out)


GET_PATHS = _plain_get_paths()

# The routes that read Postgres; they skip when none is exported.
POSTGRES_PATHS = {
    "/api/admin/api-keys",
    "/api/admin/llm/models",  # lists stored provider keys, so it reads Postgres too
    "/api/attack/technique/{tid}/d3fend",
    "/api/collection-dashboard",
    "/api/collection-plans",
    "/api/collection-plans/{plan_id}",
    "/api/collection-plans/{plan_id}/acquisitions",
    "/api/collection-plans/{plan_id}/activity",
    "/api/collection-plans/{plan_id}/catalog",
    "/api/collection-plans/{plan_id}/execution-status",
    "/api/collection-plans/{plan_id}/sources",
    "/api/collection-plans/{plan_id}/sources/{source_id}/acquisitions",
    "/api/data-catalog/{catalog_id}",
    "/api/data-catalog/{catalog_id}/preview",
    "/api/pirs",
    "/api/pirs/{pir_id}",
    "/api/pirs/{pir_id}/requirements",
}

# The routes that read the global ATT&CK catalogue (tests/neo4j_lock.py).
ATTACK_PATHS = {
    "/api/attack/attribution",
    "/api/attack/matrix",
    "/api/attack/navigator-layer",
    "/api/attack/report",
    "/api/attack/status",
    "/api/attack/technique/{tid}",
}


def _calls(s: SimpleNamespace) -> dict[str, list[tuple[dict, dict]]]:
    """Each GET path -> the (path params, query) variants to call it with.

    Variants cover the shapes a route has: an unknown id where the route answers
    200 with an empty body, a filter, a second output format.
    """
    p = {"project_id": s.project}
    missing = tp("no-such-entity")
    calls = {
        "/health": [({}, {})],
        "/api/admin/api-keys": [({}, {})],
        "/api/admin/config": [({}, {})],
        "/api/admin/degraded": [({}, {})],
        "/api/admin/enrichment": [({}, {})],
        "/api/admin/llm/models": [({}, {})],
        "/api/admin/proxy": [({}, {})],
        "/api/admin/vpn/status": [({}, {})],
        "/api/attack/attribution": [({}, p)],
        "/api/attack/matrix": [({}, p)],
        "/api/attack/navigator-layer": [({}, p)],
        "/api/attack/report": [({}, p)],
        "/api/attack/status": [({}, {})],
        "/api/attack/technique/{tid}": [({"tid": "T1566"}, p), ({"tid": "T1566.001"}, p)],
        "/api/attack/technique/{tid}/d3fend": [({"tid": D3FEND_TID}, {})],
        "/api/auth/me": [({}, {})],
        "/api/collection-dashboard": [({}, p)],
        "/api/collection-plans": [({}, p)],
        "/api/collection-plans/{plan_id}": [({"plan_id": s.plan_id}, {})],
        "/api/collection-plans/{plan_id}/acquisitions": [({"plan_id": s.plan_id}, {})],
        "/api/collection-plans/{plan_id}/activity": [
            ({"plan_id": s.plan_id}, {}),
            ({"plan_id": s.plan_id}, {"since": "2000-01-01T00:00:00+00:00"}),
        ],
        "/api/collection-plans/{plan_id}/catalog": [({"plan_id": s.plan_id}, {})],
        "/api/collection-plans/{plan_id}/execution-status": [
            ({"plan_id": s.plan_id}, {}),
            ({"plan_id": s.idle_plan_id}, {}),
        ],
        "/api/collection-plans/{plan_id}/sources": [({"plan_id": s.plan_id}, {})],
        "/api/collection-plans/{plan_id}/sources/{source_id}/acquisitions": [
            ({"plan_id": s.plan_id, "source_id": s.upload_source_id}, {}),
        ],
        "/api/collections": [({}, p)],
        "/api/collections/count/{project_id}": [({"project_id": s.project}, {})],
        "/api/collections/{task_id}": [({"task_id": s.collection_id}, {})],
        "/api/collections/{task_id}/progress": [({"task_id": s.collection_id}, {})],
        "/api/collections/{task_id}/status": [({"task_id": s.collection_id}, {})],
        "/api/communities": [({}, p)],
        "/api/connector-types": [({}, {})],
        "/api/data-catalog/{catalog_id}": [({"catalog_id": s.catalog_id}, {})],
        "/api/data-catalog/{catalog_id}/preview": [({"catalog_id": s.catalog_id}, {"limit": 2})],
        "/api/documents": [({}, p)],
        "/api/documents/{doc_id}": [({"doc_id": s.doc_id}, {})],
        "/api/documents/{doc_id}/evidence": [({"doc_id": s.doc_id}, {"entity_name": s.mentioned_name})],
        "/api/enrichment/entities/{entity_id}": [({"entity_id": s.ip_id}, {}), ({"entity_id": s.person_id}, {})],
        "/api/enrichment/providers": [({}, {})],
        "/api/entities": [({}, p), ({}, {**p, "query": "rotterdam", "limit": 5})],
        "/api/entities/{entity_id}": [({"entity_id": s.person_id}, {})],
        "/api/entities/{entity_id}/documents": [({"entity_id": s.mentioned_id}, {})],
        "/api/entity-types": [({}, {})],
        "/api/export/entities": [({}, p)],
        "/api/export/graph": [({}, p)],
        "/api/export/mindmap": [({}, p), ({}, {**p, "format": "markdown"}), ({}, {**p, "format": "mermaid"})],
        "/api/export/report/{report_id}": [({"report_id": s.report_id}, {})],
        "/api/export/stix": [({}, p)],
        "/api/geo/entity-timeline": [
            ({}, {"entity_id": s.person_id, "project_id": s.project}),
            ({}, {"entity_id": missing, "project_id": s.project}),
        ],
        "/api/geo/locations": [({}, p)],
        "/api/geo/nearby/{entity_id}": [({"entity_id": s.location_id}, {}), ({"entity_id": s.person_id}, {})],
        "/api/geo/within": [({}, {**p, "min_lat": 40, "min_lng": -10, "max_lat": 60, "max_lng": 40})],
        "/api/graph": [({}, p)],
        "/api/graph/centrality": [({}, p)],
        "/api/graph/ego-network/{entity_id}": [
            ({"entity_id": s.person_id}, p),
            ({"entity_id": missing}, p),
        ],
        "/api/graph/statistics": [({}, p)],
        "/api/graph/structural-holes": [({}, p)],
        "/api/llm/skills": [({}, {})],
        "/api/notebook": [({}, p)],
        "/api/notebook/{note_id}": [({"note_id": s.note_id}, {})],
        "/api/paths/{entity_id_1}/{entity_id_2}": [
            ({"entity_id_1": s.person_id, "entity_id_2": s.location_id}, {}),
            ({"entity_id_1": s.person_id, "entity_id_2": s.report_id}, p),
        ],
        "/api/personas": [({}, {})],
        "/api/personas/active": [({}, {})],
        "/api/pirs": [({}, p)],
        "/api/pirs/{pir_id}": [({"pir_id": s.pir_id}, {})],
        "/api/pirs/{pir_id}/requirements": [({"pir_id": s.pir_id}, {})],
        "/api/projects": [({}, {})],
        "/api/projects/{project_id}": [({"project_id": s.project}, {})],
        "/api/projects/{project_id}/activity": [({"project_id": s.project}, {})],
        "/api/reports": [({}, p)],
        "/api/reports/{report_id}": [({"report_id": s.report_id}, {}), ({"report_id": s.report_id}, p)],
        "/api/search": [({}, {**p, "q": "a"})],
        "/api/snapshots": [({}, p)],
        "/api/snapshots/{snapshot_id}": [({"snapshot_id": s.snapshot_id}, {})],
        "/api/subgraph/{entity_id}": [({"entity_id": s.person_id}, {"hops": 2}), ({"entity_id": missing}, {})],
        "/api/timeline": [({}, p)],
        "/api/timeline/histogram": [({}, p), ({}, {**p, "bucket": "day"})],
        "/api/topics": [({}, p)],
        "/api/topics/{entity_id}": [({"entity_id": s.topic_id}, p), ({"entity_id": s.person_id}, p)],
        "/api/watchlist": [({}, p)],
    }
    return calls


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_DOCUMENTS = [
    ("Ministry briefing", (
        "On 12 March 2024 Yevgeny Volkov met Maria Santos in Rotterdam. Volkov leads procurement "
        "for Nord Industrial Group, which ships dual-use parts through the Port of Rotterdam. "
        "Santos works for Baltic Freight Services in Hamburg."
    )),
    ("Shipping report", (
        "Baltic Freight Services moved containers from Hamburg to Rotterdam in April 2024. "
        "Nord Industrial Group paid the invoices through a bank in Cyprus. Yevgeny Volkov signed them."
    )),
    ("Cyber note", (
        "APT28 used spearphishing attachments against Nord Industrial Group in May 2024. "
        "The implant beaconed to 45.83.12.7 and to nord-industrial.example. "
        "CVE-2024-3400 was exploited on the perimeter firewall."
    )),
    ("Port security", (
        "The Port of Rotterdam reported a security incident on 2 June 2024. "
        "Maria Santos was questioned by Dutch police in Rotterdam about Baltic Freight Services."
    )),
]

_OVERPASS_REPLY = {"elements": [
    {"type": "way", "center": {"lat": 51.95, "lon": 4.14}, "tags": {"harbour": "yes", "name": "Maasvlakte"}},
    {"type": "node", "lat": 51.92, "lon": 4.48, "tags": {"amenity": "police", "name": "Politie Rotterdam"}},
]}


def _post(path: str, **kwargs):
    resp = client.post(path, headers=HEADERS, **kwargs)
    assert resp.status_code in (200, 202), f"seeding {path}: {resp.status_code} {resp.text}"
    return resp.json()


def _seed_graph(store, s: SimpleNamespace) -> None:
    from intel_platform.models.entities import (
        TTP, Event, IPAddress, Location, Person, ThreatActor, Vulnerability,
    )
    from intel_platform.models.relationships import Relationship

    now = datetime.now(timezone.utc).isoformat()
    with store._driver.session() as session:
        # The shape GraphStore.create_project writes, with this run's id.
        session.run(
            "CREATE (p:Project:Entity $props)",
            props={
                "id": s.project, "name": "Response models", "description": "seeded",
                "classification_level": "UNCLASSIFIED", "priority": "medium", "status": "active",
                "created_at": now, "updated_at": now, "entity_type": "Project", "project_id": "",
            },
        )

    for name, content in _DOCUMENTS:
        result = _post("/api/ingest", data={"project_id": s.project, "content": content, "source_name": name})
        s.doc_ids.append(result["document_id"])
    s.doc_id = s.doc_ids[0]

    def entity(model) -> str:
        return store.create_entity(model)["id"]

    s.person_id = entity(Person(name="Pieter de Vries", project_id=s.project, roles=["Harbour master"]))
    s.location_id = entity(Location(name="Rotterdam Europoort", project_id=s.project,
                                    latitude=51.95, longitude=4.13, location_type="port"))
    s.location2_id = entity(Location(name="Hamburg Waltershof", project_id=s.project,
                                     latitude=53.53, longitude=9.93, location_type="port"))
    s.ip_id = entity(IPAddress(name="198.51.100.24", project_id=s.project, asn="AS64500",
                               geolocation=json.dumps({"lat": 52.37, "lon": 4.9, "city": "Amsterdam",
                                                       "country": "NL", "org": "ExampleHost"})))
    s.event_id = entity(Event(name="Europoort container seizure", project_id=s.project,
                              event_datetime=datetime(2024, 6, 2, tzinfo=timezone.utc),
                              date_precision="day", date_text="2 June 2024"))
    s.actor_id = entity(ThreatActor(name="APT-Response", project_id=s.project, aliases=["Fancy Bear"]))
    s.ttp_id = entity(TTP(name="T1566.001 Spearphishing Attachment", project_id=s.project))
    s.vuln_id = entity(Vulnerability(name="CVE-2024-3400", cve_id="CVE-2024-3400", cvss_score=10.0,
                                     project_id=s.project))
    for source, target, rel in [
        (s.person_id, s.location_id, "LOCATED_AT"),
        (s.person_id, s.location2_id, "LOCATED_AT"),
        (s.actor_id, s.ttp_id, "USES"),
        (s.actor_id, s.ip_id, "COMMUNICATES_WITH"),
        (s.person_id, s.event_id, "ASSOCIATED_WITH"),
        (s.actor_id, s.vuln_id, "EXPLOITS"),
    ]:
        store.create_relationship(Relationship(
            source_id=source, target_id=target, rel_type=rel, project_id=s.project,
            confidence=0.8, source="test", method="analyst", evidence="seeded",
        ))

    # The entity the first document mentions most, for the evidence routes.
    mentioned = store.entities_mentioned_in(s.doc_id, s.project)
    assert mentioned, "ingest produced no entities to seed the evidence routes with"
    s.mentioned_id, s.mentioned_name = mentioned[0]["id"], mentioned[0]["name"]

    report = _post("/api/reports", json={
        "project_id": s.project, "title": "INTSUM Rotterdam", "content": "## Summary\n\nSeeded.",
        "report_type": "INTSUM", "entity_ids": [s.person_id],
    })
    s.report_id = report["report_id"]
    note = _post("/api/notebook", json={
        "project_id": s.project, "title": "Follow up", "content": "Who pays Santos?",
        "entity_ids": [s.person_id, tp("no-such-entity")], "note_type": "question",
    })
    s.note_id = note["note_id"]
    snapshot = _post("/api/snapshots", json={
        "project_id": s.project, "name": "Port cell", "entity_ids": [s.person_id, s.location_id, s.event_id],
    })
    s.snapshot_id = snapshot["id"]
    _post("/api/watchlist/add", json={"project_id": s.project, "entity_id": s.person_id})
    collection = _post("/api/collections", json={
        "project_id": s.project, "pir": "Who moves the parts?",
        "plan": [{"query": "Nord Industrial Group shipping", "approved": True}],
    })
    s.collection_id = collection["id"]

    tree = client.get("/api/topics", params={"project_id": s.project}, headers=HEADERS).json()
    s.topic_id = _first_topic_id(tree) or s.person_id


def _first_topic_id(node: dict) -> str | None:
    if str(node.get("id", "")).startswith("topic-"):
        return node["id"]
    for child in node.get("children") or []:
        found = _first_topic_id(child)
        if found:
            return found
    return None


async def _seed_postgres(s: SimpleNamespace) -> None:
    from intel_platform.db import jobs
    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import AttackD3fendCache, CollectionActivity
    from intel_platform.enrichment.cache import EnrichmentCache

    async with get_session_factory()() as db:
        db.add(CollectionActivity(plan_id=uuid.UUID(s.plan_id), source_id=uuid.UUID(s.web_source_id),
                                  event="source_succeeded", message="Collected 1 page"))
        db.add(CollectionActivity(plan_id=uuid.UUID(s.plan_id), event="execution_completed",
                                  message="Collection run complete"))
        await db.merge(AttackD3fendCache(
            technique_id=D3FEND_TID, fetched_at=datetime.now(timezone.utc),
            countermeasures=[{"id": "D3-DI", "label": "Data Inventory", "name": "DataInventory"}],
        ))
        await db.commit()
        job_id = await jobs.insert_job(db, plan_id=uuid.UUID(s.plan_id), project_id=s.project,
                                       kind=jobs.KIND_AGENTIC, claimed_by="worker:test:1")
        await db.commit()
        s.job_id = str(job_id)
    await EnrichmentCache().set("geoip", "198.51.100.24", {"country": "NL", "city": "Amsterdam", "asn": 64500},
                                entity_type="IPAddress")


def _seed_postgres_routes(s: SimpleNamespace) -> None:
    pir = _post("/api/pirs", json={
        "project_id": s.project, "text": "Who finances Nord Industrial Group's procurement?",
        "eeis": ["Which banks process the payments?", "Who signs the invoices?"],
    })
    s.pir_id = pir["id"]
    plan = _post("/api/collection-plans", json={"project_id": s.project, "name": "Finance", "pir_id": s.pir_id})
    s.plan_id = plan["id"]
    idle = _post("/api/collection-plans", json={"project_id": s.project, "name": "Idle"})
    s.idle_plan_id = idle["id"]
    web = _post(f"/api/collection-plans/{s.plan_id}/sources", json={
        "name": "Registry", "source_type": "web_scrape", "config": {"url": "https://example.com/registry"},
    })
    s.web_source_id = web["id"]
    upload = _post(f"/api/collection-plans/{s.plan_id}/sources", json={
        "name": "Invoices", "source_type": "file_upload", "config": {},
    })
    s.upload_source_id = upload["id"]
    csv_bytes = b"invoice,payer,amount\n1001,Nord Industrial Group,25000\n1002,Baltic Freight Services,3100\n"
    uploaded = _post(f"/api/collection-plans/{s.plan_id}/sources/{s.upload_source_id}/upload",
                     files={"file": ("invoices.csv", csv_bytes, "text/csv")})
    s.catalog_id = uploaded["catalog_id"]
    _post("/api/topics/root/children", json={"project_id": s.project, "name": "Analyst topic"})
    client.put("/api/topics/root", json={"project_id": s.project, "description": "Renamed by the seed"},
               headers=HEADERS)
    created = _post("/api/admin/api-keys", json={"provider": API_KEY_PROVIDER, "label": "seed",
                                                  "api_key": "sk-test-0000000000"})
    s.api_key_id = created["id"]


async def _remove_postgres(s: SimpleNamespace) -> None:
    from sqlalchemy import delete, select

    from intel_platform.db import jobs
    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import (
        AcquisitionLog, ApiKey, AttackD3fendCache, CollectionActivity, CollectionPlan, CollectionSource,
        DataCatalog, EnrichmentRecord, Pir, PirRequirement, TopicEdit,
    )

    async with get_session_factory()() as db:
        await db.execute(delete(jobs.CollectionJob).where(jobs.CollectionJob.project_id == s.project))
        plan_ids = select(CollectionPlan.id).where(CollectionPlan.project_id == s.project)
        for child in (AcquisitionLog, CollectionActivity, DataCatalog, CollectionSource):
            await db.execute(delete(child).where(child.plan_id.in_(plan_ids)))
        await db.execute(delete(CollectionPlan).where(CollectionPlan.project_id == s.project))
        await db.execute(delete(PirRequirement).where(PirRequirement.project_id == s.project))
        await db.execute(delete(Pir).where(Pir.project_id == s.project))
        await db.execute(delete(TopicEdit).where(TopicEdit.project_id == s.project))
        await db.execute(delete(AttackD3fendCache).where(AttackD3fendCache.technique_id == D3FEND_TID))
        await db.execute(delete(EnrichmentRecord).where(EnrichmentRecord.observable == "198.51.100.24"))
        await db.execute(delete(ApiKey).where(ApiKey.provider == API_KEY_PROVIDER))
        await db.commit()


@pytest.fixture(scope="module")
def seeded():
    """A project with documents, typed entities, edges, a report, a note, a
    snapshot, a watchlist entry and a legacy collection; with Postgres, a PIR,
    two plans, sources, an uploaded file, activity, a job, topic edits and
    cached enrichment."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from intel_platform.db import engine as engine_module
    from intel_platform.graph.store import GraphStore

    s = SimpleNamespace(
        project=PROJECT, doc_ids=[], postgres=pg.postgres_configured(),
        plan_id=None, idle_plan_id=None, upload_source_id=None, catalog_id=None, pir_id=None,
    )
    saved = (engine_module._engine, engine_module._session_factory)
    engine = None
    if s.postgres:
        # NullPool, as tests/pg.py does: every TestClient request runs on its
        # own event loop, and a pooled asyncpg connection belongs to one loop.
        engine = create_async_engine(pg._engine_url(), poolclass=NullPool)
        engine_module._engine = engine
        engine_module._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        asyncio.run(_create_schema(engine))

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    store = GraphStore(driver)
    try:
        if s.postgres:
            _seed_postgres_routes(s)
            asyncio.run(_seed_postgres(s))
        _seed_graph(store, s)
        yield s
    finally:
        with driver.session() as session:
            session.run("MATCH (n) WHERE n.project_id = $pid OR n.id = $pid DETACH DELETE n", pid=s.project)
        driver.close()
        if s.postgres:
            asyncio.run(_remove_postgres(s))
            asyncio.run(engine.dispose())
        engine_module._engine, engine_module._session_factory = saved


async def _create_schema(engine) -> None:
    from sqlalchemy import text

    from intel_platform.db import jobs  # noqa: F401  (registers collection_jobs)
    from intel_platform.db.models import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def attack_catalog():
    """The synthetic ATT&CK model test_attack_graph ingests, resolved against the project."""
    from intel_platform.graph.schema import initialize_schema
    from intel_platform.services.attack import graph_ops
    from intel_platform.services.attack.stix_parser import parse_bundle
    from tests.test_attack_graph import _bundle

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    initialize_schema(driver)
    parsed = parse_bundle(_bundle())
    graph_ops.ingest_model(driver, parsed, version="19.1")
    graph_ops.resolve_ttps(driver, PROJECT)
    attack_ids = [
        n["attack_id"]
        for coll in (parsed.tactics, parsed.techniques, parsed.groups, parsed.software, parsed.mitigations)
        for n in coll
    ]
    try:
        yield
    finally:
        with driver.session() as session:
            session.run("MATCH (n) WHERE n.attack_id IN $ids DETACH DELETE n", ids=attack_ids)
            session.run("MATCH (m:AttackMeta {id: 'attack-meta'}) DETACH DELETE m")
        driver.close()


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

def _differences(raw, sent, where: str = "$") -> list[str]:
    """How `sent` (what the declared model serialised) differs from `raw` (the
    handler's own value as FastAPI encodes it without a model)."""
    if isinstance(raw, dict) and isinstance(sent, dict):
        out = [f"{where}.{k}: dropped" for k in raw if k not in sent]
        out += [f"{where}.{k}: added {sent[k]!r}" for k in sent if k not in raw]
        for k in raw:
            if k in sent:
                out += _differences(raw[k], sent[k], f"{where}.{k}")
        return out
    if isinstance(raw, list) and isinstance(sent, list):
        if len(raw) != len(sent):
            return [f"{where}: {len(raw)} items became {len(sent)}"]
        return [d for i, (a, b) in enumerate(zip(raw, sent)) for d in _differences(a, b, f"{where}[{i}]")]
    if isinstance(raw, bool) or isinstance(sent, bool):
        same = type(raw) is type(sent) and raw == sent
    elif isinstance(raw, (int, float)) and isinstance(sent, (int, float)):
        same = raw == sent
    else:
        same = type(raw) is type(sent) and raw == sent
    return [] if same else [f"{where}: {raw!r} became {sent!r}"]


@pytest.fixture
def model_differences(monkeypatch):
    """Every difference a declared model made to a response during the test."""
    found: list[str] = []
    original = fastapi_routing.serialize_response

    async def compared(**kwargs):
        result = await original(**kwargs)
        if kwargs.get("field") is not None:
            raw = jsonable_encoder(kwargs["response_content"])
            sent = json.loads(result) if isinstance(result, (bytes, bytearray)) else result
            route = (kwargs.get("endpoint_ctx") or {}).get("path", "?")
            found.extend(f"{route} {d}" for d in _differences(raw, sent))
        return result

    monkeypatch.setattr(fastapi_routing, "serialize_response", compared)
    return found


def _route(path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path_format == path and "GET" in route.methods:
            return route
    raise AssertionError(f"no GET route {path}")


def _params(path: str):
    marks = [pytest.mark.neo4j_global] if path in ATTACK_PATHS else []
    return pytest.param(path, marks=marks, id=path)


def test_the_sweep_covers_every_get():
    """A GET added without a call here would go unchecked."""
    names = SimpleNamespace(**{k: "x" for k in (
        "project", "plan_id", "idle_plan_id", "upload_source_id", "catalog_id", "pir_id", "collection_id",
        "doc_id", "mentioned_name", "mentioned_id", "ip_id", "person_id", "location_id", "report_id",
        "note_id", "snapshot_id", "topic_id",
    )})
    assert sorted(set(GET_PATHS) - set(_calls(names))) == []
    assert sorted(set(_calls(names)) - set(GET_PATHS)) == []


@pytest.mark.parametrize("path", [_params(p) for p in GET_PATHS])
def test_get_returns_its_declared_model_unchanged(path, seeded, model_differences, monkeypatch, request):
    if path in POSTGRES_PATHS and not seeded.postgres:
        pytest.skip(pg._SKIP_REASON)
    if path in ATTACK_PATHS:
        request.getfixturevalue("attack_catalog")
    reply = MagicMock()
    reply.json = MagicMock(return_value=_OVERPASS_REPLY)
    monkeypatch.setattr("intel_platform.api.routes.geo.ProxiedClient",
                        lambda: MagicMock(post=AsyncMock(return_value=reply)))

    model = _route(path).response_model
    assert model is not None, f"GET {path} declares no response_model"
    adapter = TypeAdapter(model)
    for path_params, query in _calls(seeded)[path]:
        url = path.format(**path_params)
        resp = client.get(url, params=query, headers=HEADERS)
        assert resp.status_code == 200, f"GET {url} {query}: {resp.status_code} {resp.text[:500]}"
        adapter.validate_python(resp.json())
    assert model_differences == []


# ---------------------------------------------------------------------------
# 3. The write routes the rest of the suite never calls for real
# ---------------------------------------------------------------------------

def _send(method: str, template: str, url: str, status: int = 200, **kwargs) -> dict:
    """Call a route, check its status, validate the body against its declared model."""
    resp = client.request(method, url, headers=HEADERS, **kwargs)
    assert resp.status_code == status, f"{method} {url}: {resp.status_code} {resp.text[:500]}"
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path_format == template and method in route.methods:
            TypeAdapter(route.response_model).validate_python(resp.json())
            return resp.json()
    raise AssertionError(f"no {method} {template}")


def test_graph_write_routes_return_their_declared_model_unchanged(seeded, model_differences):
    """Each writes only under the seeded project, which the fixture removes."""
    p = seeded.project
    _send("POST", "/api/graph/influence", "/api/graph/influence",
          json={"project_id": p, "seed_ids": [seeded.person_id], "steps": 2, "threshold": 0.1})
    _send("POST", "/api/entities/{entity_id}/assess", f"/api/entities/{seeded.location_id}/assess",
          json={"entity_id": seeded.location_id, "project_id": p, "judgment": "A transit port", "probability": 0.7})
    # One known entity and one unknown: the assessments list holds both shapes.
    multi = _send("POST", "/api/assess/multi", "/api/assess/multi", json={
        "entity_ids": [seeded.person_id, tp("no-such-entity")], "project_id": p,
        "judgment": "Linked to the port", "probability": 0.6,
    })
    assert [("error" in a) for a in multi["assessments"]] == [False, True]
    body = {"project_id": p, "entity_id": seeded.location_id}
    _send("POST", "/api/watchlist/add", "/api/watchlist/add", json=body)
    _send("POST", "/api/watchlist/remove", "/api/watchlist/remove", json=body)
    _send("POST", "/api/collections/parse-plan", "/api/collections/parse-plan",
          json={"plan_text": "1. Search the port registry\n2. Monitor the shipping RSS feed"})
    note = _send("POST", "/api/notebook", "/api/notebook",
                 json={"project_id": p, "title": "Scratch", "content": "Delete me"})
    _send("DELETE", "/api/notebook/{note_id}", f"/api/notebook/{note['note_id']}")
    assert model_differences == []


def test_postgres_write_routes_return_their_declared_model_unchanged(seeded, model_differences, monkeypatch):
    if not seeded.postgres:
        pytest.skip(pg._SKIP_REASON)
    from intel_platform.collection import job_runner

    # Worker mode: /execute only queues the job, so nothing is collected here.
    monkeypatch.setattr(job_runner, "worker_mode", lambda: job_runner.WORKER)
    p = seeded.project

    plan = _send("POST", "/api/collection-plans", "/api/collection-plans", json={"project_id": p, "name": "Lifecycle"})
    base = f"/api/collection-plans/{plan['id']}"
    _send("PUT", "/api/collection-plans/{plan_id}", base, json={"description": "Edited"})
    source = _send("POST", "/api/collection-plans/{plan_id}/sources", f"{base}/sources", json={
        "name": "Registry", "source_type": "web_scrape", "config": {"url": "https://example.com/registry"},
    })
    _send("PUT", "/api/collection-plans/{plan_id}/sources/{source_id}", f"{base}/sources/{source['id']}",
          json={"name": "Port registry"})
    started = _send("POST", "/api/collection-plans/{plan_id}/execute", f"{base}/execute", status=202)
    assert started["execution_status"] == "queued"
    _send("POST", "/api/collection-plans/{plan_id}/cancel", f"{base}/cancel", status=202)
    _send("POST", "/api/collection-plans/{plan_id}/pause", f"{base}/pause")
    _send("POST", "/api/collection-plans/{plan_id}/activate", f"{base}/activate")
    _send("POST", "/api/collection-plans/{plan_id}/complete", f"{base}/complete")
    _send("POST", "/api/collection-plans/{plan_id}/archive", f"{base}/archive")
    _send("DELETE", "/api/collection-plans/{plan_id}/sources/{source_id}", f"{base}/sources/{source['id']}")
    _send("DELETE", "/api/collection-plans/{plan_id}", base)

    # The fallback provider cannot be reached: the plan says what failed.
    generated = _send("POST", "/api/collection-plans/from-pir", "/api/collection-plans/from-pir",
                      json={"project_id": p, "pir": "Who insures the vessels calling at Europoort?"})
    assert generated["generation_failures"] and "llm_requirements" not in generated

    # No provider at all: the plan carries what one would need.
    async def no_provider():
        return None

    monkeypatch.setattr("intel_platform.api.routes.llm._get_collection_provider", no_provider)
    generated = _send("POST", "/api/collection-plans/from-pir", "/api/collection-plans/from-pir",
                      json={"project_id": p, "pir": "Who crews the vessels calling at Europoort?"})
    assert generated["llm_available"] is False and "llm_requirements" in generated
    pir = _send("POST", "/api/pirs", "/api/pirs", json={"project_id": p, "text": "A requirement to delete"})
    _send("DELETE", "/api/pirs/{pir_id}", f"/api/pirs/{pir['id']}")
    _send("DELETE", "/api/topics/{node_id}", "/api/topics/topic-user-none", params={"project_id": p})
    _send("POST", "/api/search/semantic", "/api/search/semantic", json={"project_id": p, "query": "procurement"})
    key = _send("POST", "/api/admin/api-keys", "/api/admin/api-keys",
                json={"provider": API_KEY_PROVIDER, "label": "spare", "api_key": "sk-test-1111111111"})
    _send("DELETE", "/api/admin/api-keys/{key_id}", f"/api/admin/api-keys/{key['id']}")
    assert model_differences == []
