"""Engine fallback in collection search.

A single-engine search is the quietest failure in the collection path: the
engine answers "no results", the run acquires nothing, and the plan reports
success. Measured across a 15-run campaign on this stack, 41 source failures
against 27 successes — most of them sources that never resolved at all.
"""
from __future__ import annotations

import pytest

from intel_platform.collection import search as search_mod


class _FakeDDGS:
    """Stands in for ddgs. `script` maps backend name -> rows or an exception."""

    script: dict = {}
    calls: list = []

    def __init__(self, proxy=None, timeout=None):
        self.proxy = proxy

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, query, max_results=10, backend="auto"):
        type(self).calls.append((backend, query, max_results, self.proxy))
        outcome = type(self).script.get(backend, [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def ddgs(monkeypatch):
    _FakeDDGS.script = {}
    _FakeDDGS.calls = []
    monkeypatch.setattr(search_mod, "DDGS", _FakeDDGS)
    monkeypatch.setattr(search_mod.settings, "search_backends", "auto,brave,bing,duckduckgo")
    monkeypatch.setattr(search_mod.time, "sleep", lambda _s: None)
    return _FakeDDGS


def _row(url="https://example.com/a", title="T", body="B"):
    return {"href": url, "title": title, "body": body}


def test_first_engine_that_answers_wins(ddgs):
    ddgs.script = {"auto": [_row()]}
    results = search_mod.web_search("q")
    assert [r["url"] for r in results] == ["https://example.com/a"]
    assert [c[0] for c in ddgs.calls] == ["auto"], "later engines must not be consulted"


def test_empty_primary_falls_through_to_a_working_engine(ddgs):
    """The reported case: duckduckgo returns nothing where brave answers."""
    ddgs.script = {"auto": [], "brave": [_row("https://brave.example/x")]}
    results = search_mod.web_search("q")
    assert [r["url"] for r in results] == ["https://brave.example/x"]
    assert [c[0] for c in ddgs.calls] == ["auto", "brave"]


def test_failing_engine_falls_through_rather_than_failing_the_search(ddgs):
    ddgs.script = {"auto": RuntimeError("engine down"), "brave": [_row()]}
    assert len(search_mod.web_search("q")) == 1


def test_rate_limited_engine_is_retried_then_abandoned(ddgs):
    ddgs.script = {"auto": search_mod.RatelimitException("slow down"), "brave": [_row()]}
    results = search_mod.web_search("q")
    assert len(results) == 1
    auto_attempts = [c for c in ddgs.calls if c[0] == "auto"]
    assert len(auto_attempts) == 2, "a throttled engine gets one retry, not an infinite loop"


def test_all_engines_empty_returns_empty_not_an_error(ddgs):
    ddgs.script = {}
    assert search_mod.web_search("q") == []
    assert [c[0] for c in ddgs.calls] == ["auto", "brave", "bing", "duckduckgo"]


def test_every_engine_is_tried_before_giving_up(ddgs):
    ddgs.script = {b: RuntimeError("down") for b in ("auto", "brave", "bing", "duckduckgo")}
    assert search_mod.web_search("q") == []
    assert {c[0] for c in ddgs.calls} == {"auto", "brave", "bing", "duckduckgo"}


def test_rows_without_a_url_are_dropped(ddgs):
    ddgs.script = {"auto": [{"title": "no link", "body": "x"}, _row()]}
    assert len(search_mod.web_search("q")) == 1


def test_url_key_variants_are_both_read(ddgs):
    """ddgs backends disagree on the key: some emit href, others url."""
    ddgs.script = {"auto": [{"url": "https://alt.example/y", "title": "t", "body": "b"}]}
    assert search_mod.web_search("q")[0]["url"] == "https://alt.example/y"


def test_proxy_is_passed_to_every_backend(ddgs):
    """Collection egress goes through the VPN/Tor proxy; a fallback engine must
    not quietly bypass it."""
    ddgs.script = {"auto": [], "brave": [_row()]}
    search_mod.web_search("q", proxy="socks5://127.0.0.1:9050")
    assert {c[3] for c in ddgs.calls} == {"socks5://127.0.0.1:9050"}


def test_configured_backend_order_is_honoured(ddgs, monkeypatch):
    monkeypatch.setattr(search_mod.settings, "search_backends", "bing, brave")
    ddgs.script = {"bing": [], "brave": [_row()]}
    search_mod.web_search("q")
    assert [c[0] for c in ddgs.calls] == ["bing", "brave"]


def test_blank_configuration_falls_back_to_the_default_order(ddgs, monkeypatch):
    monkeypatch.setattr(search_mod.settings, "search_backends", "")
    ddgs.script = {"auto": [_row()]}
    search_mod.web_search("q")
    assert ddgs.calls[0][0] == "auto"


def test_max_results_is_clamped(ddgs):
    ddgs.script = {"auto": [_row()]}
    search_mod.web_search("q", max_results=500)
    assert ddgs.calls[0][2] == 20
    ddgs.calls.clear()
    search_mod.web_search("q", max_results=0)
    assert ddgs.calls[0][2] == 1
