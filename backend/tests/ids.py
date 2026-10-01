"""Per-run identifiers for everything the suite writes to a shared database.

``TEST_RUN`` is drawn once per pytest process (``test-`` + 8 hex chars), and
every project id, and every fixed node id, that a test writes goes through
:func:`tp`, so the data is ``test-<run>-<name>``. The Neo4j teardown in
``conftest.py`` deletes only this run's prefix, which is what lets two suites
share one Neo4j without deleting each other's fixtures mid-test.

Import it as ``from tests.ids import tp`` (one module object, so one value).
"""
from __future__ import annotations

from uuid import uuid4

TEST_RUN = f"test-{uuid4().hex[:8]}"


def tp(name: str) -> str:
    """``tp("proj-1")`` -> ``test-ab12cd34-proj-1``: a test id scoped to this run."""
    return f"{TEST_RUN}-{name}"
