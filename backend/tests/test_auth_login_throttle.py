"""Who is logging in, and how often they may fail.

`client_ip` trusted the LEFTMOST X-Forwarded-For entry — the one the client
writes — so behind Railway anyone could send a fresh value per request and brute
force without limit, while each spoofed value grew `_failed_logins` forever. With
the header ignored, every Railway client shared the proxy's address and five bad
logins locked everybody out.

The client address is now the entry TRUSTED_PROXY_HOPS from the right (the one
the nearest trusted proxy appended), failures are throttled per username as well
as per address, and the failure table has a hard size.
"""
from __future__ import annotations

import types

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from intel_platform.api import auth as auth_module
from intel_platform.api.middleware import client_ip

PEER = "10.0.0.9"


def _request(*xff_lines: str) -> Request:
    headers = [(b"x-forwarded-for", line.encode()) for line in xff_lines]
    return Request({"type": "http", "headers": headers, "client": (PEER, 5555)})


def _trust(monkeypatch, hops: int = 1, trust: bool = True):
    monkeypatch.setattr(
        "intel_platform.config.settings",
        types.SimpleNamespace(trust_proxy_headers=trust, trusted_proxy_hops=hops),
    )


class TestClientIp:
    def test_header_is_ignored_unless_trusted(self, monkeypatch):
        _trust(monkeypatch, trust=False)
        assert client_ip(_request("6.6.6.6")) == PEER

    def test_one_hop_one_entry(self, monkeypatch):
        _trust(monkeypatch, hops=1)
        assert client_ip(_request("203.0.113.7")) == "203.0.113.7"

    def test_one_hop_takes_the_entry_the_proxy_appended_not_the_client_one(self, monkeypatch):
        """The leftmost entry is whatever the client sent; it must not win."""
        _trust(monkeypatch, hops=1)
        assert client_ip(_request("6.6.6.6, 203.0.113.7")) == "203.0.113.7"

    def test_one_hop_three_entries(self, monkeypatch):
        _trust(monkeypatch, hops=1)
        assert client_ip(_request("6.6.6.6, 7.7.7.7, 203.0.113.7")) == "203.0.113.7"

    def test_two_hops_three_entries(self, monkeypatch):
        _trust(monkeypatch, hops=2)
        assert client_ip(_request("6.6.6.6, 203.0.113.7, 198.51.100.2")) == "203.0.113.7"

    def test_three_hops_three_entries(self, monkeypatch):
        _trust(monkeypatch, hops=3)
        assert client_ip(_request("203.0.113.7, 198.51.100.3, 198.51.100.2")) == "203.0.113.7"

    def test_fewer_entries_than_hops_falls_back_to_the_peer(self, monkeypatch):
        """A header shorter than the proxy chain was not written by that chain."""
        _trust(monkeypatch, hops=3)
        assert client_ip(_request("6.6.6.6, 203.0.113.7")) == PEER

    def test_repeated_header_lines_are_read_as_one_list(self, monkeypatch):
        """A proxy may append a second header line rather than extend the first."""
        _trust(monkeypatch, hops=1)
        assert client_ip(_request("6.6.6.6", "203.0.113.7")) == "203.0.113.7"

    def test_blank_selected_entry_falls_back_to_the_peer(self, monkeypatch):
        _trust(monkeypatch, hops=1)
        assert client_ip(_request("6.6.6.6, ")) == PEER

    def test_zero_hops_trusts_nothing(self, monkeypatch):
        _trust(monkeypatch, hops=0)
        assert client_ip(_request("6.6.6.6, 203.0.113.7")) == PEER


@pytest.fixture(autouse=True)
def _clean_failures():
    auth_module._failed_logins.clear()
    yield
    auth_module._failed_logins.clear()


def _fail(ip: str, username: str, times: int):
    for _ in range(times):
        auth_module.record_failed_login(ip, username)


class TestThrottle:
    def test_a_username_is_locked_after_five_failures_from_any_addresses(self):
        for i in range(auth_module.MAX_LOGIN_ATTEMPTS):
            auth_module.record_failed_login(f"198.51.100.{i}", "alice")
        with pytest.raises(HTTPException) as exc:
            auth_module.check_login_rate_limit("203.0.113.99", "alice")
        assert exc.value.status_code == 429

    def test_four_failures_are_not_a_lockout(self):
        _fail("198.51.100.1", "alice", auth_module.MAX_LOGIN_ATTEMPTS - 1)
        auth_module.check_login_rate_limit("198.51.100.1", "alice")

    def test_one_users_failures_do_not_lock_out_another_behind_the_same_address(self):
        """Every Railway client can share one address; one bad actor must not lock all."""
        _fail("10.0.0.1", "mallory", auth_module.MAX_LOGIN_ATTEMPTS)
        auth_module.check_login_rate_limit("10.0.0.1", "alice")

    def test_an_address_spraying_many_usernames_is_still_limited(self):
        for i in range(auth_module.MAX_LOGIN_ATTEMPTS_PER_IP):
            auth_module.record_failed_login("198.51.100.66", f"user{i}")
        with pytest.raises(HTTPException):
            auth_module.check_login_rate_limit("198.51.100.66", "someone-new")

    def test_success_clears_the_username_but_not_the_address(self):
        """Clearing the address on success would let one valid account reset a spray."""
        _fail("198.51.100.66", "alice", 3)
        for i in range(auth_module.MAX_LOGIN_ATTEMPTS_PER_IP - 3):
            auth_module.record_failed_login("198.51.100.66", f"user{i}")
        auth_module.clear_failed_logins("198.51.100.66", "alice")
        with pytest.raises(HTTPException):
            auth_module.check_login_rate_limit("198.51.100.66", "alice")

    def test_the_failure_table_is_bounded(self, monkeypatch):
        monkeypatch.setattr(auth_module, "_MAX_TRACKED_KEYS", 50)
        for i in range(500):
            auth_module.record_failed_login(f"spoofed-{i}", f"user-{i}")
        assert len(auth_module._failed_logins) <= 50

    def test_expired_failures_do_not_count(self, monkeypatch):
        _fail("198.51.100.1", "alice", auth_module.MAX_LOGIN_ATTEMPTS)
        real_time = auth_module.time.time
        monkeypatch.setattr(
            auth_module.time, "time", lambda: real_time() + auth_module.LOGIN_LOCKOUT_SECONDS + 1,
        )
        auth_module.check_login_rate_limit("198.51.100.1", "alice")
