from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/intel_platform/config.py -> the repository root. The .env lives
# there (it also feeds docker compose), and a bare ".env" resolved against the
# working directory, so `cd backend && uv run uvicorn ...` never read it.
_REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # PostgreSQL
    postgres_url: str = "postgresql+asyncpg://intel:changeme@localhost:5432/intel_platform"

    # API
    api_key: str = "dev-api-key-change-in-production"
    # HS256 signing key for login tokens. The default is public (it is in this
    # file), so it is for local development only: REQUIRE_SECURE_AUTH refuses to
    # boot on it, on a blank value, or on anything shorter than 32 bytes.
    jwt_secret: str = "intel-platform-dev-secret-change-in-production"
    # Fernet key for API keys stored in Postgres. Blank = stored in plaintext
    # (dev only); REQUIRE_SECURE_AUTH refuses to boot without a valid key.
    encryption_key: str = ""
    # Browser origins allowed to call the API with credentials, comma-separated.
    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    # Browser session (contract 8): /api/auth/login sets this httpOnly,
    # SameSite=Lax cookie holding the JWT, valid for session_cookie_max_age
    # seconds. session_cookie_secure adds the Secure flag: set it to true on any
    # deployment served over HTTPS (Railway), or the cookie also travels over
    # plain HTTP. Off by default because local development is plain HTTP.
    session_cookie_name: str = "sentinel_session"
    session_cookie_secure: bool = False
    session_cookie_max_age: int = 86400
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Per-client request/minute cap. High by default for the single-user
    # workbench (the SPA fires many calls per page, and behind the local
    # frontend proxy they all share one client IP); tighten for public deploys.
    rate_limit_per_minute: int = 3000
    # Trust X-Forwarded-For for the client IP used by rate limiting / login
    # throttling. OFF by default: only enable behind a trusted reverse proxy
    # (e.g. Railway), otherwise clients can spoof the header to evade limits.
    # When on, the entry trusted_proxy_hops from the RIGHT is used: the one the
    # nearest trusted proxy appended. Set it to the number of proxies in front
    # of the app (1 for Railway's edge alone).
    trust_proxy_headers: bool = False
    trusted_proxy_hops: int = 1
    # Security hardening: when true, refuse to start with the built-in default
    # JWT secret / API key / admin password. Set REQUIRE_SECURE_AUTH=true on any
    # public or deployed instance.
    require_secure_auth: bool = False
    # Seed password for the auto-created admin user (blank -> 'admin' in dev; must
    # be set when require_secure_auth is on). Read via Settings so .env works too.
    default_admin_password: str = ""
    # The MCP server (endpoint /mcp) exposes graph-writing and LLM-spending
    # tools, so it is disabled by default. When enabled it requires the REST
    # API's credentials; it is refused outright under require_secure_auth.
    mcp_enabled: bool = False

    # Extraction
    # hybrid (NLP + LLM) is the recommended default: the LLM contributes typed,
    # evidence-backed relationships and higher-precision entities, NLP/regex
    # contributes deterministic IOCs. Falls back to NLP when no LLM provider is
    # reachable. Set extraction_llm_provider=ollama to route extraction to a
    # local, rate-limit-free model (see _get_extraction_provider).
    extraction_mode: str = "hybrid"  # nlp | llm | hybrid
    extraction_llm_provider: str = ""  # "" = default provider; "ollama" = local
    extraction_llm_model: str = ""
    coreference_enabled: bool = False
    entity_resolution_threshold: float = 0.92
    spacy_model: str = "en_core_web_sm"
    extraction_confidence_min: float = 0.0
    # Storage-time floor for blanket co-occurrence relationships
    # (ASSOCIATED_WITH) specifically — these are a last-resort "these two
    # entities appeared near each other" guess, not a typed/pattern-derived
    # relation, so they need a higher bar to be worth persisting to the
    # graph. Verb/pattern-derived and LLM-typed relationships are unaffected.
    cooccurrence_confidence_min: float = 0.55

    # Chunking
    # Characters of a single crawled document kept and extracted from. A live
    # crawl returned a 139,391-word page: chunked whole, that is hundreds of
    # sequential LLM calls, and the collection stalled with one entity to show
    # for it. The same bound applies to what is stored, so every extracted
    # entity's evidence remains inside the document that is kept.
    max_document_chars: int = 50000
    chunk_size: int = 2000
    chunk_overlap: int = 50

    # Collection / agentic crawl
    collection_crawl_concurrency: int = 4  # max concurrent URL fetches per source

    # Collection egress proxy (optional; OFF by default). ONLY web-collection
    # egress (crawl4ai + ddgs + the httpx connectors) is routed through the
    # selected proxy. The active mode is persisted in Postgres (AppSetting
    # "collection_proxy_mode": direct|vpn|tor) and defaults to direct. LLM /
    # cloud API calls are NEVER proxied — they always go out direct.
    #   vpn  -> gluetun's local HTTP proxy (self-hosted sidecar; local only)
    #   tor  -> Tor SOCKS5 with remote DNS (socks5h)
    vpn_http_proxy: str = "http://gluetun:8888"
    tor_socks_proxy: str = "socks5h://tor:9050"
    # gluetun control server (queried DIRECTLY, never through the tunnel) for
    # VPN status / kill-switch. gluetun_control_apikey is an optional X-API-Key.
    gluetun_control_url: str = "http://gluetun:8000"
    gluetun_control_apikey: str = ""
    # Dedicated provider for bulk collection work (source resolution + per-doc
    # summarization), which is high-volume and would exhaust a rate-limited cloud
    # key. Empty = use the default provider (preserves prior behavior, e.g. on
    # deployments without a local Ollama). Set to "ollama" to offload locally.
    # Topic-label refinement is one LLM call per cluster node, so it drains a
    # rate-limited cloud key fastest. Set to "ollama" to run it locally.
    topics_llm_provider: str = ""
    topics_llm_model: str = ""
    collection_llm_provider: str = ""
    collection_llm_model: str = ""
    # Which provider bulk collection work prefers when collection_llm_provider
    # is empty: "cloud-first" (a configured cloud key, else Ollama) or
    # "local-first". Read by llm/providers.py.
    collection_llm_preference: str = "cloud-first"
    # Largest response body, in bytes, a collection or enrichment fetch will
    # buffer before giving up on it.
    max_fetch_bytes: int = 10_000_000

    # Search engines to try in order, comma-separated, first non-empty answer
    # wins. `ddgs` fronts several engines that fail independently — the
    # duckduckgo backend answers "no results" under light load for queries brave
    # and bing serve immediately — and a single-engine search starves a
    # collection run without ever reporting an error. Empty = the default order.
    search_backends: str = "auto,brave,bing,duckduckgo"

    # Cyber enrichment (WHOIS/RDAP, DNS, GeoIP, cert transparency, CISA KEV, NVD).
    # All providers are keyless; the NVD key is OPTIONAL and only raises NVD's
    # rate limit. Auto-enrich of newly-seen cyber nodes is OFF by default and is
    # toggled at runtime via AppSetting "enrichment_auto_enabled" (admin screen).
    # Enrichment egress goes through the collection proxy, never the LLM path.
    nvd_api_key: str = ""

    # Geo enrichment (Nominatim geocoding, Overpass POIs) — all keyless. Public
    # Nominatim caps at 1 req/s and REQUIRES a descriptive User-Agent (ToS);
    # egress goes through the collection proxy. Base URLs are config-driven so a
    # self-hosted Nominatim/Overpass is a .env swap (no bulk on the public ones).
    geo_user_agent: str = "intel-platform/1.0 (geo enrichment)"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    overpass_base_url: str = "https://overpass-api.de/api/interpreter"
    geonames_username: str = ""  # optional; enables the GeoNames admin ladder

    # MITRE ATT&CK® integration. The Enterprise STIX 2.1 bundle is pinned to a
    # version and fetched on demand (~50 MB, keyless, redistributable with
    # attribution — see data/attack/ATTRIBUTION.md), cached to a gitignored path.
    # Base URL is config-driven so a mirror is a .env swap.
    attack_stix_version: str = "19.1"
    attack_stix_base_url: str = (
        "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack"
    )
    # ATT&CK Phase 2 — RAG text→technique mapping. POST /attack/embed embeds the
    # technique catalog into pgvector; POST /attack/map retrieves the top-K nearest
    # candidate techniques per unresolved TTP and an LLM confirms which apply.
    # Only confirmed matches at/above the confidence floor are written as
    # (:TTP)-[:MAPS_TO {method:"llm"}]->(:AttackTechnique).
    attack_mapping_top_k: int = 5
    attack_mapping_confidence_min: float = 0.5
    attack_mapping_max_ttps: int = 200  # cap per /attack/map run (cost/latency guard)
    # ATT&CK Phase 3a — CVE→ATT&CK chaining via CWE→CAPEC→ATT&CK. Both files are
    # keyless + redistributable (MITRE Terms of Use, see data/attack/ATTRIBUTION.md),
    # fetched on demand and cached to a gitignored path under data/attack/. URLs are
    # config-driven so a mirror is a .env swap.
    cwe_xml_url: str = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"
    capec_xml_url: str = "https://capec.mitre.org/data/xml/capec_latest.xml"
    # ATT&CK Phase 3b — D3FEND defensive countermeasures. GET
    # /attack/technique/{tid}/d3fend lazily fetches the per-technique offensive→
    # defensive mapping from D3FEND (keyless), parses the SPARQL-style bindings to
    # [{id, label}], and caches it in Postgres (AttackD3fendCache) for
    # attack_d3fend_ttl_days. Degrades to [] on any outage. Base URL is
    # config-driven so a mirror is a .env swap.
    d3fend_api_base: str = "https://d3fend.mitre.org/api/offensive-technique/attack"
    attack_d3fend_ttl_days: int = 30

    # LLM providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    cohere_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    # Context window requested from Ollama. Its own default (2048 tokens)
    # silently truncates extraction and report prompts.
    ollama_num_ctx: int = 16384
    default_llm_provider: str = "anthropic"
    default_llm_model: str = ""

    # Embeddings
    embedding_provider: str = "openai"  # openai | cohere | ollama
    embedding_model: str = ""  # provider-specific default if empty
    embedding_dimensions: int = 1536
    vector_search_limit: int = 20
    hybrid_graph_weight: float = 0.4  # weight for graph results in hybrid scoring

    # extra="ignore": the same .env carries keys for docker compose and the VPN
    # sidecar (SURFSHARK_*, ...) that are not settings; forbidding them made a
    # copy of .env.example fail to load at all.
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore",
    )


from functools import lru_cache  # noqa: E402


@lru_cache
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    """Module-level ``settings`` that always resolves to the cached instance.

    Attribute *writes* are forwarded too. Without that, ``monkeypatch.setattr(
    settings, "x", ...)`` stored ``x`` on the proxy itself, and the undo wrote
    the old value back onto the proxy as well, leaving a permanent shadow that
    every later reader (and every later patch of the instance) lost to.
    """

    def __getattr__(self, name):
        return getattr(get_settings(), name)

    def __setattr__(self, name, value):
        setattr(get_settings(), name, value)

    def __delattr__(self, name):
        delattr(get_settings(), name)


settings = _SettingsProxy()
