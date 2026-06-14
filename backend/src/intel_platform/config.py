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

    # Extraction
    extraction_mode: str = "nlp"  # nlp | llm | hybrid
    spacy_model: str = "en_core_web_lg"
    coreference_enabled: bool = False
    entity_resolution_threshold: float = 0.92
    extraction_confidence_min: float = 0.0

    # Chunking
    chunk_size: int = 2000
    chunk_overlap: int = 50

    # Collection / agentic crawl
    collection_crawl_concurrency: int = 4  # max concurrent URL fetches per source

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


from functools import lru_cache


@lru_cache
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
