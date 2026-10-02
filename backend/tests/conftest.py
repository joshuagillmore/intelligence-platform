import os
import pytest
from neo4j import GraphDatabase

from tests.ids import TEST_RUN

# Connection targets stay `setdefault` — CI and docker-compose legitimately
# point the suite at a different Neo4j, and overriding those would break them.
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "changeme")

# These two are *assigned*, not `setdefault`. They are correctness guarantees for
# the suite, and `setdefault` silently yielded to any ambient value: run the
# tests anywhere the project's own .env is loaded and API_KEY became the shipped
# `dev-api-key-change-in-production`, which auth.py deliberately refuses — 49
# route tests failed 401 — while EXTRACTION_MODE became `hybrid`, defeating the
# very determinism this line exists to provide. A test guarantee that any
# environment can revoke is not a guarantee.
os.environ["API_KEY"] = "test-key"
# One Postgres connection per checkout: the sync TestClient runs each request
# on its own event loop and a pooled connection must never cross loops.
os.environ["POSTGRES_NULL_POOL"] = "true"
# Extraction defaults to hybrid (NLP + LLM) in production; force NLP for the
# test suite so unit tests stay deterministic and never depend on a live LLM.
os.environ["EXTRACTION_MODE"] = "nlp"

# A developer's repo-root .env reaches the suite by two routes, and both are
# closed here. The first is the process environment: crawl4ai/config.py calls
# load_dotenv() at import, walks up from site-packages to the repo root and
# copies that .env into os.environ, so provider choices, cloud keys and
# POSTGRES_URL arrive as if exported — and made tests such as
# test_topic_label_provenance call a real OllamaProvider. load_dotenv never
# overrides a variable that is already set, so these are *assigned* explicit
# test values before anything imports intel_platform or crawl4ai.
for _name in (
    "DEFAULT_LLM_PROVIDER", "DEFAULT_LLM_MODEL",
    "EXTRACTION_LLM_PROVIDER", "EXTRACTION_LLM_MODEL",
    "COLLECTION_LLM_PROVIDER", "COLLECTION_LLM_MODEL",
    "TOPICS_LLM_PROVIDER", "TOPICS_LLM_MODEL",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "COHERE_API_KEY",
    "EMBEDDING_PROVIDER",
):
    os.environ[_name] = ""
# Exported POSTGRES_URL (CI) is kept; otherwise a `.invalid` host fails in ms. Not localhost:5432: on a
# workstation it was the SeeStar telescope app (accepts TCP, never answers), costing 60 s per DB-touching test.
os.environ["POSTGRES_URL"] = os.environ.get("POSTGRES_URL") or (
    "postgresql+asyncpg://intel:changeme@postgres-disabled-in-tests.invalid:5432/intel_platform"
)
# With every provider blank, provider selection ends at its Ollama fallback, so
# where that points decides whether a test talks to a real model. A developer's
# .env names the compose host (`ollama`, 2.7 s per failed Windows lookup) and a
# workstation often runs a real Ollama on localhost:11434 (live, slow,
# nondeterministic generation). An RFC 6761 `.invalid` host can never resolve
# and fails in milliseconds everywhere, as CI's empty localhost port does.
os.environ["OLLAMA_BASE_URL"] = "http://ollama-disabled-in-tests.invalid:11434"

# The second route is Settings' own env file: contract 20 resolves env_file to
# the repository-root .env from config.py's location, so it is found from any
# working directory. Loaded into the suite it would make billed LLM calls and
# write to a real database. Tests never read it; this is set before anything
# instantiates Settings.
from intel_platform import config as _config  # noqa: E402

_config.Settings.model_config["env_file"] = None


@pytest.fixture
def neo4j_driver():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    yield driver
    with driver.session() as session:
        # Only this run's prefix (tests/ids.py): a second suite on the same Neo4j
        # keeps its fixtures.
        session.run("MATCH (n) WHERE n.project_id STARTS WITH $prefix DETACH DELETE n", prefix=TEST_RUN)
    driver.close()


@pytest.fixture
def graph_store(neo4j_driver):
    from intel_platform.graph.store import GraphStore
    store = GraphStore(neo4j_driver)
    return store


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "neo4j_global: the module writes Neo4j state no project id scopes (reference catalogues, "
        "schema constraints, database-wide backfills); concurrent suites take turns through it",
    )


@pytest.fixture(autouse=True)
def _neo4j_global_state(request):
    """Serialise `neo4j_global` tests across suites sharing this Neo4j (tests/neo4j_lock.py)."""
    if request.node.get_closest_marker("neo4j_global") is None:
        yield
        return
    from tests.neo4j_lock import neo4j_global_lock

    with neo4j_global_lock(os.environ["NEO4J_URI"]):
        yield


@pytest.fixture(scope="session", autouse=True)
def _migrated_postgres():
    """Migrate the exported Postgres once per session.

    The migration tests run in a scratch database, so nothing else guaranteed
    that the exported one was at head before a route test needed it. On a
    fresh database (CI, a new container) the access check then found no
    `project_members` table and answered 503 for every non-admin, which only
    showed up in the test order that reached the attack routes first. A `.invalid`
    placeholder means no Postgres: nothing to migrate.
    """
    import asyncio

    url = os.environ.get("POSTGRES_URL", "")
    if not url or ".invalid" in url:
        return
    from intel_platform.api.routes import admin_config  # noqa: F401  (registers the schema-ready hook)
    from intel_platform.db import engine as engine_module

    async def _migrate():
        await engine_module.init_db()
        await engine_module.get_engine().dispose()

    asyncio.run(_migrate())
    # The engine above belonged to that short-lived loop; later tests build
    # their own on their own loops.
    engine_module._engine = None
    engine_module._session_factory = None
