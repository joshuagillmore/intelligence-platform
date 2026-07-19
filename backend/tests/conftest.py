import os
import pytest
from neo4j import GraphDatabase

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "changeme")
os.environ.setdefault("API_KEY", "test-key")
# Extraction defaults to hybrid (NLP + LLM) in production; force NLP for the
# test suite so unit tests stay deterministic and never depend on a live LLM.
os.environ.setdefault("EXTRACTION_MODE", "nlp")


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
