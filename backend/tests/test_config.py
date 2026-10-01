from pathlib import Path

import pytest

from intel_platform import config as config_module
from intel_platform.config import Settings

REPO_ROOT = Path(config_module.__file__).resolve().parents[3]


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


# ---------------------------------------------------------------------------
# A-17 / contract 20: every setting goes through Settings, and a real .env loads
# ---------------------------------------------------------------------------

def test_the_env_file_is_the_repo_root_env_wherever_the_process_starts():
    """It was the bare name '.env', resolved against the working directory, so
    `cd backend && uv run uvicorn ...` never saw the repo's .env. (conftest
    switches the env file off for the suite, so the module constant is checked.)"""
    env_file = config_module.ENV_FILE
    assert env_file.is_absolute()
    assert env_file == REPO_ROOT / ".env"
    assert (REPO_ROOT / ".env.example").exists(), "the resolved directory is not the repo root"


def test_the_suite_does_not_read_a_developers_env():
    assert Settings.model_config["env_file"] is None


def test_keys_settings_does_not_define_are_ignored(tmp_path):
    """The repo .env also feeds docker compose (SURFSHARK_*, gluetun); with
    extra='forbid' copying .env.example to .env raised extra_forbidden."""
    env = tmp_path / ".env"
    env.write_text("NEO4J_URI=bolt://example:7687\nSURFSHARK_VPN_TYPE=wireguard\nJWT_SECRET=from-the-file\n")
    s = Settings(_env_file=str(env))
    assert s.jwt_secret == "from-the-file"


def test_env_example_loads_as_a_settings_file():
    """Copying .env.example to .env must produce a working configuration."""
    s = Settings(_env_file=str(REPO_ROOT / ".env.example"))
    assert s.neo4j_uri


def test_env_example_blank_embedding_model_is_blank(monkeypatch):
    """I-2: `EMBEDDING_MODEL=   # blank = ...` parsed as the comment text, so the
    quickstart asked the provider for a model named '# blank = provider default'."""
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    s = Settings(_env_file=str(REPO_ROOT / ".env.example"))
    assert s.embedding_model == ""
    assert s.embedding_provider == "openai"


def test_no_env_example_value_carries_a_comment():
    """Inline comments are parsed differently by python-dotenv and compose; a
    value in .env.example must never depend on either stripping one."""
    from dotenv import dotenv_values

    leaked = {k: v for k, v in dotenv_values(REPO_ROOT / ".env.example").items() if v and "#" in v}
    assert leaked == {}
    raw = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    inline = [line for line in raw if not line.startswith("#") and "=" in line and " #" in line]
    assert inline == []


@pytest.mark.parametrize("field,default", [
    ("jwt_secret", "intel-platform-dev-secret-change-in-production"),
    ("encryption_key", ""),
    ("cors_origins", "http://localhost:3000,http://localhost:8000"),
    ("trusted_proxy_hops", 1),
    ("ollama_num_ctx", 16384),
    ("max_fetch_bytes", 10_000_000),
    ("collection_llm_preference", "cloud-first"),
    # Contract 11 (post-review hardening).
    ("collection_worker_mode", "inline"),
    ("collection_stall_seconds", 120),
    ("egress_proxy_enabled", True),
    ("session_cookie_name", "sentinel_session"),
    ("session_cookie_secure", False),
    ("session_cookie_max_age", 86400),
])
def test_settings_other_packages_read_exist_with_their_defaults(field, default, monkeypatch):
    monkeypatch.delenv(field.upper(), raising=False)
    s = Settings(neo4j_uri="bolt://x:7687", _env_file=None)
    assert getattr(s, field) == default


@pytest.mark.parametrize("field", [
    "JWT_SECRET", "ENCRYPTION_KEY", "CORS_ORIGINS", "TRUSTED_PROXY_HOPS",
    "OLLAMA_NUM_CTX", "MAX_FETCH_BYTES", "COLLECTION_LLM_PREFERENCE",
    "COLLECTION_WORKER_MODE", "COLLECTION_STALL_SECONDS", "EGRESS_PROXY_ENABLED",
    "SESSION_COOKIE_NAME", "SESSION_COOKIE_SECURE", "SESSION_COOKIE_MAX_AGE",
])
def test_every_setting_is_discoverable_in_env_example(field):
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"\n{field}=" in text


def test_cors_origins_come_from_settings():
    from intel_platform.api import app as app_module

    assert app_module._parse_origins(" http://a.example , ,http://b.example ") == [
        "http://a.example", "http://b.example",
    ]
    cors = next(m for m in app_module.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    from intel_platform.config import settings
    assert cors.kwargs["allow_origins"] == app_module._parse_origins(settings.cors_origins)


def test_nothing_reads_os_environ_ad_hoc():
    """Config only via Settings: a second reader is a second source of truth."""
    src = REPO_ROOT / "backend" / "src" / "intel_platform"
    offenders = [
        str(p.relative_to(src)) for p in (src / "api").rglob("*.py")
        if "os.environ" in p.read_text(encoding="utf-8")
    ]
    offenders += [
        name for name in ("config.py", "crypto.py")
        if "os.environ" in (src / name).read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_patching_the_settings_proxy_never_shadows_the_instance(monkeypatch):
    """monkeypatch.setattr(settings, ...) used to store the value on the proxy
    and, on undo, write the *old* value back onto the proxy too. That shadow
    then hid every later patch of the real instance (an ingest test saw 50000
    after another file had patched-and-restored 100)."""
    from intel_platform.config import get_settings, settings

    original = get_settings().max_document_chars
    with monkeypatch.context() as m:
        m.setattr(settings, "max_document_chars", 100)
        assert settings.max_document_chars == 100
        assert get_settings().max_document_chars == 100
    assert settings.__dict__ == {}
    assert settings.max_document_chars == original

    with monkeypatch.context() as m:
        m.setattr(get_settings(), "max_document_chars", 300)
        assert settings.max_document_chars == 300
    assert settings.max_document_chars == original
