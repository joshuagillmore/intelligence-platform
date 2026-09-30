"""The pgvector columns are created at EMBEDDING_DIMENSIONS on first boot and
never altered. A later change of embedding provider (Cohere's 1024 against a
1536 column) made every insert fail with only a log line to show for it, and
the ingest response's ``embeddings_stored: 0`` was the sole visible symptom."""
from intel_platform.db.engine import vector_width_problem


def test_matching_widths_are_fine():
    assert vector_width_problem(1536, {"chunk_embeddings": 1536, "attack_technique_embeddings": 1536}) is None


def test_absent_tables_are_not_a_mismatch():
    assert vector_width_problem(1024, {"chunk_embeddings": None}) is None


def test_a_mismatch_names_the_column_and_the_two_ways_out():
    problem = vector_width_problem(1024, {"chunk_embeddings": 1536, "attack_technique_embeddings": 1024})
    assert problem is not None
    assert "EMBEDDING_DIMENSIONS=1024" in problem
    assert "chunk_embeddings.embedding is vector(1536)" in problem
    assert "attack_technique_embeddings" not in problem
    assert "set EMBEDDING_DIMENSIONS to the column width" in problem
    assert "vector(1024)" in problem


def test_health_reports_the_problem(monkeypatch):
    from intel_platform.db import engine as db_engine
    from intel_platform.api.routes import health as health_route

    monkeypatch.setattr(db_engine, "VECTOR_WIDTH_PROBLEM", "EMBEDDING_DIMENSIONS=1024 but x")
    monkeypatch.setattr(health_route, "get_neo4j_driver", lambda: type("D", (), {"verify_connectivity": lambda self: None})())
    monkeypatch.setattr(health_route, "_ollama_configured", lambda: False)
    monkeypatch.setattr(health_route, "_ollama_is_fallback", lambda: False)
    body = health_route.health_check()
    assert body.status == "ok"
    assert body.embeddings.startswith("EMBEDDING_DIMENSIONS=1024")
