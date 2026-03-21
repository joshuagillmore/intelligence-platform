from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # API
    api_key: str = "dev-api-key-change-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Extraction
    extraction_mode: str = "nlp"  # nlp | llm | hybrid
    spacy_model: str = "en_core_web_sm"

    # Chunking
    chunk_size: int = 2000
    chunk_overlap: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


from functools import lru_cache


@lru_cache
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
