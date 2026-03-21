import os
from intel_platform.config import Settings


def test_settings_loads_defaults():
    s = Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test",
        api_key="test-key",
    )
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 8000
    assert s.extraction_mode == "nlp"
    assert s.chunk_size == 2000
    assert s.chunk_overlap == 50


def test_settings_requires_neo4j():
    try:
        Settings(api_key="test-key")
        assert False, "Should require neo4j_uri"
    except Exception:
        pass
