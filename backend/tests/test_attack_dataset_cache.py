"""Caching of the downloaded MITRE datasets (Low -> E).

The ATT&CK bundle and the CWE/CAPEC files used to be written to the cache
*before* they were parsed, so a truncated body or an HTML error page became the
cached copy every later ingest trusted; and the CWE/CAPEC "latest" files, once
cached, were never fetched again. Now a download is parsed first and written by
temp file + rename, and "latest" copies expire.

No network: ``ProxiedClient`` is replaced by a fake in every test.
"""
import io
import json
import os
import time
import zipfile
from types import SimpleNamespace

import pytest

from intel_platform.services.attack import ingest, vuln_chain

VERSION = "19.1"

_BUNDLE = {
    "type": "bundle",
    "objects": [
        {
            "type": "x-mitre-tactic", "id": "x-mitre-tactic--a", "name": "Initial Access",
            "x_mitre_shortname": "initial-access",
            "external_references": [{"source_name": "mitre-attack", "external_id": "TA0001"}],
        },
        {
            "type": "attack-pattern", "id": "attack-pattern--t1566", "name": "Phishing",
            "x_mitre_is_subtechnique": False,
            "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}],
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1566"}],
        },
    ],
}

_CAPEC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Attack_Pattern_Catalog xmlns="http://capec.mitre.org/capec-3" Name="CAPEC" Version="3.9">
   <Attack_Patterns>
      <Attack_Pattern ID="98" Name="Phishing">
         <Related_Weaknesses><Related_Weakness CWE_ID="451"/></Related_Weaknesses>
         <Taxonomy_Mappings>
            <Taxonomy_Mapping Taxonomy_Name="ATTACK"><Entry_ID>1566</Entry_ID></Taxonomy_Mapping>
         </Taxonomy_Mappings>
      </Attack_Pattern>
   </Attack_Patterns>
</Attack_Pattern_Catalog>
"""

_CWE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Weakness_Catalog xmlns="http://cwe.mitre.org/cwe-7" Name="CWE" Version="4.15">
   <Weaknesses><Weakness ID="451" Name="User Interface Misrepresentation"/></Weaknesses>
</Weakness_Catalog>
"""


def _zip(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cwec_v4.15.xml", xml)
    return buf.getvalue()


class _FakeClient:
    """Stands in for ProxiedClient: serves canned bodies by URL, records calls."""

    def __init__(self, bodies: dict[str, bytes] | None = None, *, fail: bool = False):
        self.bodies = bodies or {}
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, timeout=30, **kwargs):
        self.calls.append((url, kwargs))
        if self.fail:
            raise ConnectionError("mitre.org unreachable")
        body = next((b for key, b in self.bodies.items() if key in url), b"")

        def raise_for_status():
            return None

        return SimpleNamespace(
            status_code=200, content=body, text=body.decode("utf-8", "replace"),
            raise_for_status=raise_for_status,
        )


def _no_temp_files(directory) -> bool:
    return not [p for p in os.listdir(directory) if p.endswith(".tmp")]


# --- ATT&CK bundle ------------------------------------------------------------

@pytest.fixture
def attack_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "_DATA_DIR", tmp_path)
    return tmp_path


def _serve_attack(monkeypatch, body: bytes) -> _FakeClient:
    client = _FakeClient({"enterprise-attack": body})
    monkeypatch.setattr(ingest, "ProxiedClient", lambda *a, **k: client)
    return client


@pytest.mark.parametrize("body", [
    pytest.param(b"<html><body>502 Bad Gateway</body></html>", id="html-error-page"),
    pytest.param(json.dumps(_BUNDLE).encode()[:200], id="truncated"),
    pytest.param(json.dumps({"type": "bundle", "objects": []}).encode(), id="no-techniques"),
])
async def test_an_attack_bundle_that_does_not_parse_is_not_cached(attack_dir, monkeypatch, body):
    _serve_attack(monkeypatch, body)
    with pytest.raises(ValueError):
        await ingest._load_parsed(VERSION)
    assert not ingest._cache_path(VERSION).exists()
    assert _no_temp_files(attack_dir)


async def test_a_valid_attack_bundle_is_parsed_then_cached(attack_dir, monkeypatch):
    client = _serve_attack(monkeypatch, json.dumps(_BUNDLE).encode())
    parsed = await ingest._load_parsed(VERSION)

    assert [t["attack_id"] for t in parsed.techniques] == ["T1566"]
    assert json.loads(ingest._cache_path(VERSION).read_text(encoding="utf-8")) == _BUNDLE
    assert _no_temp_files(attack_dir)
    # ~53 MB: above ProxiedClient's default body cap.
    assert client.calls[0][1].get("max_bytes") == 200_000_000


async def test_a_corrupt_cached_bundle_is_fetched_again(attack_dir, monkeypatch):
    ingest._cache_path(VERSION).write_text("{not json", encoding="utf-8")
    client = _serve_attack(monkeypatch, json.dumps(_BUNDLE).encode())

    parsed = await ingest._load_parsed(VERSION)
    assert parsed.techniques
    assert len(client.calls) == 1
    assert json.loads(ingest._cache_path(VERSION).read_text(encoding="utf-8")) == _BUNDLE


async def test_a_good_cached_bundle_is_used_without_fetching(attack_dir, monkeypatch):
    ingest._cache_path(VERSION).write_text(json.dumps(_BUNDLE), encoding="utf-8")
    client = _serve_attack(monkeypatch, b"")
    parsed = await ingest._load_parsed(VERSION)
    assert parsed.techniques and client.calls == []


# --- CWE / CAPEC "latest" files -----------------------------------------------

@pytest.fixture
def vuln_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(vuln_chain, "_CAPEC_CACHE", tmp_path / "capec_latest.xml")
    monkeypatch.setattr(vuln_chain, "_CWE_CACHE", tmp_path / "cwec_latest.xml.zip")
    return tmp_path


def _serve_vuln(monkeypatch, capec: bytes, cwe: bytes, *, fail: bool = False) -> _FakeClient:
    client = _FakeClient({"capec": capec, "cwec": cwe}, fail=fail)
    monkeypatch.setattr(vuln_chain, "ProxiedClient", lambda *a, **k: client)
    return client


def _age(path, days: float) -> None:
    then = time.time() - days * 86400
    os.utime(path, (then, then))


async def test_capec_that_does_not_parse_is_not_cached(vuln_dir, monkeypatch):
    _serve_vuln(monkeypatch, b"<html>maintenance</html", _zip(_CWE_XML))
    with pytest.raises((ValueError, SyntaxError)):
        await vuln_chain.load_capec_map()
    assert not vuln_chain._CAPEC_CACHE.exists()
    assert _no_temp_files(vuln_dir)


async def test_cwe_download_that_is_not_a_zip_is_not_cached(vuln_dir, monkeypatch):
    _serve_vuln(monkeypatch, _CAPEC_XML.encode(), b"<html>not a zip</html>")
    with pytest.raises(zipfile.BadZipFile):
        await vuln_chain.load_cwe_names()
    assert not vuln_chain._CWE_CACHE.exists()


async def test_valid_downloads_are_parsed_then_cached_with_a_large_body_allowed(vuln_dir, monkeypatch):
    client = _serve_vuln(monkeypatch, _CAPEC_XML.encode(), _zip(_CWE_XML))

    assert await vuln_chain.load_capec_map() == {"CWE-451": {"T1566"}}
    assert await vuln_chain.load_cwe_names() == {"CWE-451": "User Interface Misrepresentation"}
    assert vuln_chain._CAPEC_CACHE.read_bytes() == _CAPEC_XML.encode()
    assert vuln_chain._CWE_CACHE.read_bytes() == _zip(_CWE_XML)
    assert [kwargs.get("max_bytes") for _, kwargs in client.calls] == [200_000_000, 200_000_000]
    assert _no_temp_files(vuln_dir)


async def test_a_fresh_latest_cache_is_used_without_fetching(vuln_dir, monkeypatch):
    vuln_chain._CAPEC_CACHE.write_bytes(_CAPEC_XML.encode())
    client = _serve_vuln(monkeypatch, b"", b"")
    assert await vuln_chain.load_capec_map() == {"CWE-451": {"T1566"}}
    assert client.calls == []


async def test_a_stale_latest_cache_is_refreshed(vuln_dir, monkeypatch):
    # "latest" is a moving target: a copy cached once used to be trusted forever.
    old = _CAPEC_XML.replace("1566", "1204")
    vuln_chain._CAPEC_CACHE.write_bytes(old.encode())
    _age(vuln_chain._CAPEC_CACHE, 45)
    client = _serve_vuln(monkeypatch, _CAPEC_XML.encode(), b"")

    assert await vuln_chain.load_capec_map() == {"CWE-451": {"T1566"}}
    assert len(client.calls) == 1
    assert vuln_chain._CAPEC_CACHE.read_bytes() == _CAPEC_XML.encode()


async def test_a_stale_cache_is_the_fallback_when_the_refresh_fails(vuln_dir, monkeypatch):
    vuln_chain._CAPEC_CACHE.write_bytes(_CAPEC_XML.encode())
    _age(vuln_chain._CAPEC_CACHE, 45)
    _serve_vuln(monkeypatch, b"", b"", fail=True)

    assert await vuln_chain.load_capec_map() == {"CWE-451": {"T1566"}}


async def test_no_cache_and_no_network_is_an_error(vuln_dir, monkeypatch):
    _serve_vuln(monkeypatch, b"", b"", fail=True)
    with pytest.raises(ConnectionError):
        await vuln_chain.load_capec_map()
