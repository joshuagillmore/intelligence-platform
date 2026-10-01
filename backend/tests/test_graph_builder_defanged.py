"""A defanged indicator must not crash the graph build.

`_host_of` handed "//evil-c2[.]com" to urlsplit, which (Python 3.11.4+) treats
any bracket in the authority as an IPv6 literal and raises ValueError. The
web-chrome filter calls `_host_of` for every Domain/URL entity before anything
else, so one defanged name — "evil-c2[.]com", "hxxp://evil[.]com/x", as a model
or an analyst writes them — raised out of build_graph_from_extractions and
failed the whole ingest. Reported by WP-X from a live eval run.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intel_platform.services.graph_builder import (
    _host_of, _is_malformed_host, _is_web_chrome, build_graph_from_extractions,
)
from tests.ids import tp

DEFANGED = ["evil-c2[.]com", "hxxp://evil[.]com/x", "https://cdn[.]example[.]org/a.js"]


@pytest.mark.parametrize("name", DEFANGED)
def test_host_of_never_raises(name):
    assert isinstance(_host_of(name), str)


def test_the_host_is_still_read_from_a_defanged_url():
    assert _host_of("hxxp://evil[.]com/x") == "evil[.]com"
    assert _host_of("evil-c2[.]com") == "evil-c2[.]com"


@pytest.mark.parametrize("name", DEFANGED)
@pytest.mark.parametrize("entity_type", ["Domain", "URL"])
def test_the_filters_never_raise(name, entity_type):
    _is_web_chrome(name, entity_type)
    _is_malformed_host(name, entity_type)


def test_a_build_with_a_defanged_domain_completes():
    created: list = []
    store = SimpleNamespace(
        create_entity=lambda e: created.append(e) or {"id": e.id},
        search_entity_by_name=lambda *a, **k: [],
        record_entity_source=lambda *a, **k: None,
        record_mentions=lambda *a, **k: 0,
        create_relationship=lambda rel: {},
    )
    result = build_graph_from_extractions(
        store, [{"name": "evil-c2[.]com", "entity_type": "Domain"}], [], project_id=tp("defanged"),
    )
    assert result["entities_created"] == 1
    assert [e.name for e in created] == ["evil-c2[.]com"]
