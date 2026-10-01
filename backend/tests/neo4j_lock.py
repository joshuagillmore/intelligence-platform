"""A cross-process lock for tests that touch Neo4j state no project id scopes.

The per-run prefix (``tests/ids.py``) isolates everything a test writes under a
project. A few tests cannot be scoped that way: they load the global ATT&CK and
CWE reference nodes and their meta singletons, drop and recreate schema
constraints, or assert on a database-wide backfill count. Two suites running
those at once against one Neo4j would delete each other's reference nodes or
count each other's data, so the modules that hold them carry
``pytest.mark.neo4j_global`` and ``conftest.py`` holds this lock around each of
their tests: the suites take turns through those modules and overlap
everywhere else.

It is an OS file lock in the temp directory, keyed by the Neo4j host and port,
so it covers suites on one machine (two worktrees, two terminals) and is
released by the OS if a process dies holding it.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

_LOCAL = {"localhost", "127.0.0.1", "::1", ""}


def _key(neo4j_uri: str) -> str:
    parts = urlsplit(neo4j_uri)
    host = (parts.hostname or "").lower()
    host = "127.0.0.1" if host in _LOCAL else host
    return f"{host}:{parts.port or 7687}"


def lock_path(neo4j_uri: str) -> str:
    digest = hashlib.sha1(_key(neo4j_uri).encode()).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), f"intel-platform-tests-neo4j-{digest}.lock")


if os.name == "nt":
    import msvcrt

    def _try_lock(fh) -> bool:
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fh) -> bool:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def neo4j_global_lock(neo4j_uri: str, *, timeout: float = 600.0):
    """Hold the lock for ``neo4j_uri``; raise if another suite holds it past ``timeout``."""
    deadline = time.monotonic() + timeout
    with open(lock_path(neo4j_uri), "a+b") as fh:
        while not _try_lock(fh):
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"another test suite has held the Neo4j global-state lock ({fh.name}) for {timeout:.0f} s"
                )
            time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(fh)
