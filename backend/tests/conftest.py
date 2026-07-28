import os
import pytest
from neo4j import GraphDatabase

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
# Extraction defaults to hybrid (NLP + LLM) in production; force NLP for the
# test suite so unit tests stay deterministic and never depend on a live LLM.
os.environ["EXTRACTION_MODE"] = "nlp"


@pytest.fixture
def neo4j_driver():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    yield driver
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.project_id STARTS WITH 'test-' DETACH DELETE n")
    driver.close()


@pytest.fixture
def graph_store(neo4j_driver):
    from intel_platform.graph.store import GraphStore
    store = GraphStore(neo4j_driver)
    return store
