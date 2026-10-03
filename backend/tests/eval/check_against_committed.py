#!/usr/bin/env python3
"""Extraction-quality gate: a replayed eval must not score below the committed one.

Runs ``run_corpus_eval.py --mode <mode> --replay-only`` into a temporary
directory and compares its F1 figures with the committed
``tests/eval/corpus_eval_<mode>.json``, overall and per set:

- ``entity`` (name match), ``entity_typed`` (name and type),
- ``relationship_typed`` (typed edges only), and ``relationship`` (every edge).

It fails when any fresh figure is lower than the committed one by more than
``TOLERANCE`` (0.005), when the replay had to skip a model request because no
reply was recorded for it (a prompt change committed without a re-recorded
run), and when a document degrades that did not degrade in the committed run.

There is no thresholds file. The committed results are the baseline, so a
change that improves extraction commits its new results and raises the bar.

No network, no database and no billed call: replay mode answers every model
request from ``llm_replies.json`` and never asks the model. The provider
settings are pinned to the ones the committed run recorded, with a placeholder
key, so neither the shell nor a local ``.env`` can change which replies match.

Usage (from backend/):
    uv run python tests/eval/check_against_committed.py --mode nlp
    uv run python tests/eval/check_against_committed.py --mode llm
    uv run python tests/eval/check_against_committed.py --mode hybrid
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
RUNNER = HERE / "run_corpus_eval.py"
MODES = ("nlp", "llm", "hybrid")

# A fresh figure may sit this far below the committed one before the gate fails.
TOLERANCE = 0.005
# The F1 figures compared, by report key. `relationship` is compared when the
# committed report has it.
METRICS = ("entity", "entity_typed", "relationship_typed", "relationship")

# The provider each recorded run used, by the class name the report records,
# and the key setting that provider needs before it can be selected.
_PROVIDERS = {
    "CohereProvider": ("cohere", "COHERE_API_KEY"),
    "AnthropicProvider": ("anthropic", "ANTHROPIC_API_KEY"),
    "OpenAIProvider": ("openai", "OPENAI_API_KEY"),
    "OllamaProvider": ("ollama", None),
}
# Everything that can steer provider selection; each is pinned or blanked.
_PROVIDER_VARS = (
    "DEFAULT_LLM_PROVIDER", "DEFAULT_LLM_MODEL", "EXTRACTION_LLM_PROVIDER", "EXTRACTION_LLM_MODEL",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "COHERE_API_KEY",
)
# Never sent anywhere: replay mode does not call the provider it wraps.
PLACEHOLDER_KEY = "replay-only-no-calls"


# ── Comparison (pure) ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Regression:
    scope: str            # "overall" or a set name
    metric: str           # a METRICS key
    committed: float
    fresh: float | None   # None when the fresh report lacks the figure

    @property
    def delta(self) -> float | None:
        return None if self.fresh is None else round(self.fresh - self.committed, 4)


def f1_scores(report: dict) -> dict[tuple[str, str], float]:
    """``{(scope, metric): f1}`` for the overall block and every set."""
    out: dict[tuple[str, str], float] = {}
    blocks = [("overall", report.get("overall") or {}), *(report.get("by_set") or {}).items()]
    for scope, block in blocks:
        for metric in METRICS:
            figure = block.get(metric)
            if isinstance(figure, dict) and isinstance(figure.get("f1"), (int, float)):
                out[(scope, metric)] = float(figure["f1"])
    return out


def compare(committed: dict, fresh: dict, tolerance: float = TOLERANCE) -> list[Regression]:
    """Every committed F1 the fresh report falls short of by more than ``tolerance``.

    A figure the committed report has and the fresh one lacks counts too: a
    metric or set that silently disappears must not pass the gate.
    """
    fresh_scores = f1_scores(fresh)
    regressions = []
    for (scope, metric), base in f1_scores(committed).items():
        now = fresh_scores.get((scope, metric))
        # Rounded so float noise cannot decide a figure sitting exactly on the line.
        if now is None or round(base - now, 6) > tolerance:
            regressions.append(Regression(scope, metric, base, now))
    return regressions


def run_problems(committed: dict, fresh: dict) -> list[str]:
    """What makes the fresh run unfit to compare, whatever its scores."""
    problems = []
    replies = (fresh.get("llm") or {}).get("replies") or {}
    if replies.get("missed", 0) > 0:
        problems.append(
            f"{replies['missed']} model request(s) had no recorded reply. The prompt or the request "
            "changed without a re-recorded run: record one live run and commit llm_replies.json "
            "with the results (tests/eval/README.md)."
        )
    if replies.get("live", 0) > 0:
        problems.append(f"{replies['live']} reply(ies) were asked live; the gate must only replay.")
    before = set(committed.get("degraded_documents") or [])
    newly = [d for d in fresh.get("degraded_documents") or [] if d not in before]
    if newly:
        problems.append(f"{len(newly)} document(s) degraded that did not before: " + "; ".join(newly[:10]))
    return problems


def format_regressions(mode: str, regressions: list[Regression]) -> str:
    lines = [
        f"Extraction eval regressed ({mode}): {len(regressions)} figure(s) more than {TOLERANCE} "
        "below the committed results.",
        "",
        "| Set | Metric | Committed F1 | Fresh F1 | Change |",
        "|---|---|---|---|---|",
    ]
    for r in regressions:
        fresh = "missing" if r.fresh is None else f"{r.fresh:.4f}"
        change = "" if r.delta is None else f"{r.delta:+.4f}"
        lines.append(f"| {r.scope} | {r.metric} | {r.committed:.4f} | {fresh} | {change} |")
    return "\n".join(lines)


def summary(mode: str, fresh: dict) -> str:
    o = fresh["overall"]
    return (
        f"{mode}: no regression against the committed results (tolerance {TOLERANCE}); entity F1 "
        f"{o['entity']['f1']:.4f}, typed F1 {o['entity_typed']['f1']:.4f}, "
        f"typed relationship F1 {o['relationship_typed']['f1']:.4f}"
    )


# ── Running the replay ──────────────────────────────────────────────────────

def replay_env(committed: dict, base: dict[str, str] | None = None) -> dict[str, str]:
    """The runner's environment: provider settings pinned to the committed run's.

    Every provider variable is set, blank when unused, because a variable left
    unset falls through to the repository ``.env`` (the runner's own loader and
    pydantic-settings both read it), and that is where a developer's real
    provider choice lives.
    """
    env = dict(os.environ if base is None else base)
    for key in _PROVIDER_VARS:
        env[key] = ""
    if committed.get("spacy_model"):
        env["SPACY_MODEL"] = committed["spacy_model"]
    llm = committed.get("llm") or {}
    if llm:
        provider, key_var = _PROVIDERS.get(llm.get("provider", ""), (None, None))
        if provider is None:
            raise SystemExit(f"the committed run used an unknown provider: {llm.get('provider')!r}")
        env["DEFAULT_LLM_PROVIDER"] = provider
        env["DEFAULT_LLM_MODEL"] = llm.get("model") or ""
        if key_var:
            env[key_var] = PLACEHOLDER_KEY
    return env


def run_replay(mode: str, committed: dict, out_dir: Path) -> dict:
    """Run the eval in replay mode over the committed run's sets; return its report."""
    sets = list(committed.get("by_set") or {})
    env_file = out_dir / "empty.env"   # so the runner does not load the repository .env
    env_file.write_text("", encoding="utf-8")
    cmd = [sys.executable, str(RUNNER), "--mode", mode, "--replay-only", "--out-dir", str(out_dir),
           "--env-file", str(env_file), "--llm-cache", str(HERE / "llm_replies.json")]
    if sets:
        cmd += ["--sets", *sets]
    proc = subprocess.run(cmd, cwd=BACKEND, env=replay_env(committed), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-3000:] + proc.stderr[-5000:])
        raise SystemExit(f"run_corpus_eval.py --mode {mode} --replay-only exited {proc.returncode}")
    return json.loads((out_dir / f"corpus_eval_{mode}.json").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fail when a replayed extraction eval scores below the committed one.")
    ap.add_argument("--mode", choices=MODES, required=True)
    ap.add_argument("--committed", type=Path, default=None,
                    help="baseline report (default: tests/eval/corpus_eval_<mode>.json)")
    args = ap.parse_args(argv)

    committed_path = args.committed or HERE / f"corpus_eval_{args.mode}.json"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix=f"eval-gate-{args.mode}-") as tmp:
        fresh = run_replay(args.mode, committed, Path(tmp))

    problems = run_problems(committed, fresh)
    regressions = compare(committed, fresh)
    for problem in problems:
        print(f"{args.mode}: {problem}")
    if regressions:
        print(format_regressions(args.mode, regressions))
    if problems or regressions:
        return 1
    print(summary(args.mode, fresh))
    return 0


if __name__ == "__main__":
    sys.exit(main())
