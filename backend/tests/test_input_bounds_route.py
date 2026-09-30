"""Out-of-range input is a 422, not a Cypher error or a silent substitution (Low -> A).

A negative limit or offset reached Cypher's LIMIT/SKIP as a syntax error (500);
/graph/influence took an untyped dict; ego-network hops below 1 went through;
and PUT /admin/proxy answered 200 while quietly saving 'direct' for a mode it
did not recognise, which on a Tor or VPN deployment turns egress protection off.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}
PID = "test-low-bounds"


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": -1}, {"limit": 10001}, {"offset": -1},
])
def test_entity_list_bounds(params):
    resp = client.get("/api/entities", params={"project_id": PID, **params}, headers=headers)
    assert resp.status_code == 422


def test_entity_list_upper_bound_is_accepted(graph_store):
    resp = client.get("/api/entities", params={"project_id": PID, "limit": 10000, "offset": 0}, headers=headers)
    assert resp.status_code == 200


@pytest.mark.parametrize("path,params", [
    ("/api/projects/{pid}/activity", {"limit": 0}),
    ("/api/projects/{pid}/activity", {"limit": -5}),
    ("/api/graph/structural-holes", {"project_id": PID, "top_n": 0}),
    ("/api/graph/structural-holes", {"project_id": PID, "top_n": -1}),
    ("/api/graph/ego-network/e1", {"project_id": PID, "hops": 0}),
    ("/api/graph/ego-network/e1", {"project_id": PID, "hops": 5}),
])
def test_other_list_and_depth_bounds(path, params):
    resp = client.get(path.format(pid=PID), params=params, headers=headers)
    assert resp.status_code == 422


class TestInfluenceBody:
    @pytest.fixture
    def recorded(self, monkeypatch):
        from intel_platform.api.routes import graph as graph_route

        calls = []

        def fake(store, project_id, seed_ids, steps=3, threshold=0.3):
            calls.append({"project_id": project_id, "seed_ids": seed_ids, "steps": steps, "threshold": threshold})
            return {"influenced": []}

        monkeypatch.setattr(graph_route, "compute_influence_propagation", fake)
        return calls

    @pytest.mark.parametrize("body", [
        {"seed_ids": ["e1"]},  # no project
        {"project_id": PID, "seed_ids": "e1"},  # not a list
        {"project_id": PID, "seed_ids": ["e1"], "steps": 0},
        {"project_id": PID, "seed_ids": ["e1"], "steps": 11},
        {"project_id": PID, "seed_ids": ["e1"], "threshold": 1.5},
        {"project_id": PID, "seed_ids": ["e1"], "threshold": "high"},
    ])
    def test_malformed_bodies_are_rejected(self, recorded, body):
        assert client.post("/api/graph/influence", json=body, headers=headers).status_code == 422
        assert recorded == []

    def test_a_valid_body_is_passed_through(self, recorded):
        body = {"project_id": PID, "seed_ids": ["e1", "e2"], "steps": 4, "threshold": 0.5}
        assert client.post("/api/graph/influence", json=body, headers=headers).status_code == 200
        assert recorded == [body]


class TestProxyMode:
    @pytest.fixture
    def db(self, monkeypatch):
        from intel_platform.api.routes import admin_config

        writes = []

        class _Result:
            def scalar_one_or_none(self):
                return None

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement):
                return _Result()

            def add(self, row):
                writes.append((row.key, row.value))

            async def commit(self):
                pass

        monkeypatch.setattr(admin_config, "get_session_factory", lambda: (lambda: _Session()))
        return writes

    @pytest.mark.parametrize("mode", ["tr0r", "", "proxy", "TOR "])
    def test_an_unknown_mode_is_rejected_not_saved_as_direct(self, db, mode):
        resp = client.put("/api/admin/proxy", json={"mode": mode}, headers=headers)
        assert resp.status_code == 422
        assert db == []

    @pytest.mark.parametrize("mode", ["direct", "vpn", "tor"])
    def test_known_modes_are_saved(self, db, mode):
        resp = client.put("/api/admin/proxy", json={"mode": mode}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["mode"] == mode
        assert db[-1][1] == mode
