"""Low -> G: the TF-IDF k-means seed survives a restart.

The seed was ``hash(project_id) % 2**31``. Python salts ``str`` hashes per
process (PYTHONHASHSEED), so the same project's topic tree was reshuffled —
different clusters, different node ids — every time the API restarted, and
any analyst edit keyed to a node id pointed somewhere else afterwards.
"""
from __future__ import annotations

import os
import subprocess
import sys

_PROBE = """
import numpy as np
from intel_platform.services import document_clustering as dc

seeds = []
_Real = np.random.RandomState

class _Spy(_Real):
    def __init__(self, seed=None):
        seeds.append(seed)
        super().__init__(seed)

np.random.RandomState = _Spy
docs = [(f"d{i}", f"alpha beta gamma item{i} delta epsilon") for i in range(8)]
dc.cluster_documents(docs, "project-restart-check")
print(seeds[0])
"""


def _seed_under(hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    out = subprocess.run(
        [sys.executable, "-c", _PROBE], env=env, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.strip().splitlines()[-1]


def test_the_seed_is_the_same_in_every_process():
    assert _seed_under("1") == _seed_under("2") == _seed_under("3")


def test_different_projects_still_get_different_seeds():
    from intel_platform.services.document_clustering import _project_seed

    assert _project_seed("project-a") != _project_seed("project-b")
    assert 0 <= _project_seed("project-a") < 2 ** 31
