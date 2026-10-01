"""Wrappers that run the corpus eval end to end. Excluded from the default suite.

    uv run pytest -m eval tests/eval -v

The llm and hybrid modes make real model calls (replayed from
``llm_replies.json`` where the request is unchanged), so they run the script
as a subprocess: ``tests/conftest.py`` has blanked every provider setting in
this process, and the script reads them from the repo-root ``.env`` itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_corpus_eval.py"
BACKEND = HERE.parents[1]


@pytest.mark.eval
@pytest.mark.parametrize("mode", ["nlp", "llm", "hybrid"])
def test_corpus_eval_runs_end_to_end(mode, tmp_path):
    cache = tmp_path / "llm_replies.json"
    if (HERE / "llm_replies.json").is_file():
        # A copy, so a run with a changed prompt records into tmp, not the repo.
        shutil.copy(HERE / "llm_replies.json", cache)
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", mode, "--out-dir", str(tmp_path), "--llm-cache", str(cache)],
        cwd=BACKEND, env=dict(os.environ), capture_output=True, text=True, timeout=1800,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-4000:]

    report = json.loads((tmp_path / f"corpus_eval_{mode}.json").read_text(encoding="utf-8"))
    overall = report["overall"]
    assert overall["documents"] >= 40
    # Floors well under the committed results: this catches a broken run (no
    # entities, every document degraded), not a point of F1.
    assert overall["entity"]["f1"] > 0.6
    assert overall["entity_typed"]["f1"] > 0.4
    if mode != "nlp":
        assert not report["degraded_documents"], report["degraded_documents"]
