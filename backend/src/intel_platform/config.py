from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # PostgreSQL
    postgres_url: str = "postgresql+asyncpg://intel:changeme@localhost:5432/intel_platform"

    # API
    api_key: str = "dev-api-key-change-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Per-client request/minute cap. High by default for the single-user
    # workbench (the SPA fires many calls per page, and behind the local
    # frontend proxy they all share one client IP); tighten for public deploys.
    rate_limit_per_minute: int = 3000
    # Security hardening: when true, refuse to start with the built-in default
    # JWT secret / API key / admin password. Set REQUIRE_SECURE_AUTH=true on any
    # public or deployed instance.
    require_secure_auth: bool = False
    # Seed password for the auto-created admin user (blank -> 'admin' in dev; must
    # be set when require_secure_auth is on). Read via Settings so .env works too.
    default_admin_password: str = ""
    # The MCP server exposes read+write graph tools and is NOT behind the REST
    # auth layer, so it is disabled by default. Enable deliberately (behind a
    # trusted network / gateway) via MCP_ENABLED=true.
    mcp_enabled: bool = False

    # Extraction
    extraction_mode: str = "nlp"  # nlp | llm | hybrid
    spacy_model: str = "en_core_web_lg"
    coreference_enabled: bool = False
    entity_resolution_threshold: float = 0.92
    extraction_confidence_min: float = 0.0
    # Storage-time floor for blanket co-occurrence relationships
    # (ASSOCIATED_WITH) specifically — these are a last-resort "these two
    # entities appeared near each other" guess, not a typed/pattern-derived
    # relation, so they need a higher bar to be worth persisting to the
    # graph. Verb/pattern-derived and LLM-typed relationships are unaffected.
    cooccurrence_confidence_min: float = 0.55

    # Chunking
    chunk_size: int = 2000
    chunk_overlap: int = 50

    # Collection / agentic crawl
    collection_crawl_concurrency: int = 4  # max concurrent URL fetches per source
    # Dedicated provider for bulk collection work (source resolution + per-doc
    # summarization), which is high-volume and would exhaust a rate-limited cloud
    # key. Empty = use the default provider (preserves prior behavior, e.g. on
    # deployments without a local Ollama). Set to "ollama" to offload locally.
    collection_llm_provider: str = ""
    collection_llm_model: str = ""

    # LLM providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    cohere_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_llm_provider: str = "anthropic"
    default_llm_model: str = ""

    # Embeddings
    embedding_provider: str = "openai"  # openai | cohere | ollama
    embedding_model: str = ""  # provider-specific default if empty
    embedding_dimensions: int = 1536
    vector_search_limit: int = 20
    hybrid_graph_weight: float = 0.4  # weight for graph results in hybrid scoring

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


from functools import lru_cache  # noqa: E402


@lru_cache
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
