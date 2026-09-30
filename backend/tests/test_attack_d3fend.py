"""Tests for D3FEND countermeasure lookup (``services.attack.d3fend``).

The ProxiedClient fetch and the Postgres session are both mocked — no real
D3FEND network call and no live DB. We assert the SPARQL-binding parse extracts
distinct countermeasures, that every failure mode degrades to
``{"countermeasures": []}`` without raising, and that a fresh cache hit short-
circuits before any fetch.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from intel_platform.services.attack import d3fend

TID = "T1566"


def _binding(cid: str, label: str, name: str = "") -> dict:
    row = {"def_tech_id": {"value": cid}, "def_tech_label": {"value": label}}
    if name:
        row["def_tech"] = {"value": f"http://d3fend.mitre.org/ontologies/d3fend.owl#{name}"}
    return row


def _payload(bindings: list[dict]) -> dict:
    return {"off_to_def": {"head": {"vars": ["def_tech_id", "def_tech_label", "def_tech"]},
                           "results": {"bindings": bindings}}}


def _mock_session(cached_row=None) -> MagicMock:
    """AsyncSession stub: execute() -> a result whose scalar_one_or_none is cached_row."""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=cached_row)
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _mock_client(*, payload=None, status_code=200, raise_exc=None) -> MagicMock:
    client = MagicMock()
    if raise_exc is not None:
        client.get = AsyncMock(side_effect=raise_exc)
        return client
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


# --- Pure parse ------------------------------------------------------------

def test_parse_extracts_distinct_countermeasures():
    payload = _payload([
        _binding("D3-FH", "File Hashing", "FileHashing"),
        _binding("D3-NTF", "Network Traffic Filtering", "NetworkTrafficFiltering"),
        _binding("D3-FH", "File Hashing", "FileHashing"),  # duplicate id -> collapsed
        _binding("D3-NN", "No Name URI"),                  # def_tech absent -> name=""
    ])
    out = d3fend.parse_countermeasures(payload)
    assert out == [
        {"id": "D3-FH", "label": "File Hashing", "name": "FileHashing"},
        {"id": "D3-NTF", "label": "Network Traffic Filtering", "name": "NetworkTrafficFiltering"},
        {"id": "D3-NN", "label": "No Name URI", "name": ""},
    ]


def test_parse_skips_bindings_missing_id_or_label():
    payload = _payload([
        _binding("D3-G", "Good", "Good"),
        {"def_tech_id": {"value": "D3-NL"}},                 # missing label
        {"def_tech_label": {"value": "No Id"}},              # missing id
        {"def_tech_id": {"value": ""}, "def_tech_label": {"value": "Blank"}},  # blank id
    ])
    assert d3fend.parse_countermeasures(payload) == [{"id": "D3-G", "label": "Good", "name": "Good"}]


def test_parse_without_the_bindings_structure_is_none():
    # A reply without off_to_def.results.bindings is not "no countermeasures";
    # it is a reply we cannot read (a schema change, an error object).
    assert d3fend.parse_countermeasures({}) is None
    assert d3fend.parse_countermeasures({"off_to_def": {}}) is None
    assert d3fend.parse_countermeasures({"off_to_def": {"results": {}}}) is None
    assert d3fend.parse_countermeasures({"off_to_def": {"results": {"bindings": "nope"}}}) is None
    assert d3fend.parse_countermeasures("not a dict") is None


def test_parse_empty_bindings_is_a_real_no_countermeasures():
    assert d3fend.parse_countermeasures(_payload([])) == []


# --- Fetch + cache flow ----------------------------------------------------

async def test_fetch_parses_and_caches_on_success():
    session = _mock_session(cached_row=None)  # cache miss
    client = _mock_client(payload=_payload([_binding("D3-FH", "File Hashing", "FileHashing")]))

    result = await d3fend.get_countermeasures(session, TID, client=client)

    assert result == {"countermeasures": [{"id": "D3-FH", "label": "File Hashing", "name": "FileHashing"}]}
    client.get.assert_awaited_once()
    session.add.assert_called_once()  # upserted the fresh result
    session.commit.assert_awaited_once()


async def test_cache_hit_short_circuits_without_fetch():
    fresh = SimpleNamespace(
        technique_id=TID,
        countermeasures=[{"id": "d3f:Cached", "label": "Cached CM"}],
        fetched_at=datetime.now(timezone.utc) - timedelta(days=1),  # within 30d TTL
    )
    session = _mock_session(cached_row=fresh)
    client = _mock_client(payload=_payload([_binding("d3f:Other", "Other")]))

    result = await d3fend.get_countermeasures(session, TID, client=client)

    assert result == {"countermeasures": [{"id": "d3f:Cached", "label": "Cached CM"}]}
    client.get.assert_not_called()  # no second fetch on a fresh hit


async def test_stale_cache_triggers_refetch():
    stale = SimpleNamespace(
        technique_id=TID,
        countermeasures=[{"id": "d3f:Old", "label": "Old"}],
        fetched_at=datetime.now(timezone.utc) - timedelta(days=90),  # older than TTL
    )
    session = _mock_session(cached_row=stale)
    client = _mock_client(payload=_payload([_binding("D3-N", "New CM", "NewCM")]))

    result = await d3fend.get_countermeasures(session, TID, client=client)

    assert result == {"countermeasures": [{"id": "D3-N", "label": "New CM", "name": "NewCM"}]}
    client.get.assert_awaited_once()


async def test_404_degrades_to_empty_no_raise():
    session = _mock_session(cached_row=None)
    client = _mock_client(payload=None, status_code=404)

    result = await d3fend.get_countermeasures(session, TID, client=client)
    assert result == {"countermeasures": []}


async def test_network_error_degrades_to_empty_uncached():
    session = _mock_session(cached_row=None)
    client = _mock_client(raise_exc=RuntimeError("d3fend unreachable"))

    result = await d3fend.get_countermeasures(session, TID, client=client)
    assert result == {"countermeasures": [], "degraded": True}
    session.add.assert_not_called()   # a transient failure must not poison the cache
    session.commit.assert_not_called()


async def test_a_reply_without_bindings_is_not_cached_as_no_countermeasures():
    # A D3FEND schema change used to be cached for 30 days as "no countermeasures".
    session = _mock_session(cached_row=None)
    client = _mock_client(payload={"off_to_def": {"head": {"vars": []}, "results": {}}})

    result = await d3fend.get_countermeasures(session, TID, client=client)
    assert result == {"countermeasures": [], "degraded": True}
    session.add.assert_not_called()
    session.commit.assert_not_called()


async def test_empty_bindings_are_cached_as_no_countermeasures():
    session = _mock_session(cached_row=None)
    client = _mock_client(payload=_payload([]))

    result = await d3fend.get_countermeasures(session, TID, client=client)
    assert result == {"countermeasures": []}
    session.add.assert_called_once()


async def test_a_malformed_technique_id_is_never_put_in_the_url():
    session = _mock_session(cached_row=None)
    client = _mock_client(payload=_payload([]))
    for tid in ("../../api/offensive-technique", "T1566/../../x", "T15661", "T1566.01", "1566"):
        result = await d3fend.get_countermeasures(session, tid, client=client)
        assert result == {"countermeasures": []}
    client.get.assert_not_called()


async def test_malformed_body_degrades_to_empty_uncached():
    session = _mock_session(cached_row=None)
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(side_effect=ValueError("not json"))
    client.get = AsyncMock(return_value=resp)

    result = await d3fend.get_countermeasures(session, TID, client=client)
    assert result == {"countermeasures": [], "degraded": True}
    session.add.assert_not_called()


async def test_blank_technique_id_returns_empty():
    session = _mock_session(cached_row=None)
    client = _mock_client(payload=_payload([]))
    result = await d3fend.get_countermeasures(session, "   ", client=client)
    assert result == {"countermeasures": []}
    client.get.assert_not_called()
