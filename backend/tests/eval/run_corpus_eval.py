#!/usr/bin/env python3
"""Corpus-backed extraction eval: score nlp | llm | hybrid against reviewed gold.

Scores the extractor against fixture sets in the format the older eval
harness reads (``<name>.txt`` + ``<name>_expected.json``), each reported on
its own and combined:

- ``openrep`` (primary): 40 chunks of the ``openrep-deep`` exercise collection —
  synthetic analyst products, public-domain CRS text and synthetic
  contradiction documents — with hand-labelled gold
  (``tests/fixtures/extraction_corpus_openrep``);
- ``kestrel``: 40 fictional exercise reporting chunks whose gold was seeded
  from their "Entities identified" line (``tests/fixtures/extraction_corpus``);
- ``cyber``: the three documents from the 2026-09-30 end-to-end run that showed
  the known typing and relationship defects (``extraction_corpus_cyber``).

Both corpora are built by ``scripts/build_eval_corpus.py``.

Writes ``tests/eval/corpus_eval_<mode>.json`` (overall, per set, per type,
relationship metrics, per-document detail) and ``corpus_eval_<mode>.md``.

This is a plain script on purpose. ``tests/conftest.py`` blanks every provider
setting and key, which is right for the unit suite and wrong here: the llm and
hybrid modes make real, billed model calls. So the script loads the repo-root
``.env`` itself (only for those modes), and the ``@pytest.mark.eval`` wrappers
in ``test_corpus_eval.py`` run it as a subprocess. Nothing here runs in the
default suite.

Usage (from backend/):
    uv run python tests/eval/run_corpus_eval.py --mode nlp
    uv run python tests/eval/run_corpus_eval.py --mode hybrid --build-neo4j bolt://localhost:7691
    uv run python tests/eval/run_corpus_eval.py --mode llm --refresh-cache   # ask live, record the replies

Model replies are replayed from ``llm_replies.json`` when the request is
unchanged (see ``ReplyCache``); ``--no-cache`` asks live and records nothing.
See ``tests/eval/README.md`` for the corpus, the gold conventions and results.

``--build-neo4j`` additionally runs each document's extraction through
``graph_builder.build_graph_from_extractions`` in a throwaway project and
records what the build kept and dropped — the number the live run reported as
"relationships_dropped 5" is a build number, not an extraction one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FIXTURES = BACKEND / "tests" / "fixtures"
SETS = {
    "openrep": FIXTURES / "extraction_corpus_openrep",
    "kestrel": FIXTURES / "extraction_corpus",
    "cyber": FIXTURES / "extraction_corpus_cyber",
    # The older hand-written sets, not run by default: a regression check that
    # a fix for this corpus does not cost what those already measure.
    "legacy": FIXTURES / "extraction",
    "holdout": FIXTURES / "extraction_holdout",
}
MODES = ("nlp", "llm", "hybrid")

# Provider settings the llm/hybrid modes read from the .env. A value that is
# missing *or empty* in the environment is taken from the file: the unit
# suite's conftest assigns these empty, and a subprocess inherits that.
_PROVIDER_VARS = (
    "DEFAULT_LLM_PROVIDER", "DEFAULT_LLM_MODEL",
    "EXTRACTION_LLM_PROVIDER", "EXTRACTION_LLM_MODEL",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "COHERE_API_KEY",
    "OLLAMA_BASE_URL", "SPACY_MODEL",
)


# ── Environment ─────────────────────────────────────────────────────────────

def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key] = value
    return out


def find_env_file() -> Path | None:
    """The repo-root .env; from a git worktree, the main checkout's."""
    candidates = [REPO / ".env"]
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if common:
            candidates.append(Path(common).parent / ".env")
    except (OSError, subprocess.CalledProcessError):
        pass
    return next((c for c in candidates if c.is_file()), None)


def load_provider_env(env_file: Path | None) -> Path | None:
    path = env_file or find_env_file()
    if path is None:
        return None
    values = _parse_env(path)
    for key in _PROVIDER_VARS:
        if values.get(key) and not os.environ.get(key):
            os.environ[key] = values[key]
    # The plan's default for eval runs; only when the file names none.
    if not os.environ.get("DEFAULT_LLM_PROVIDER"):
        os.environ["DEFAULT_LLM_PROVIDER"] = "cohere"
    return path


def _prepare_imports(neo4j_uri: str | None) -> None:
    # Settings requires a Neo4j URI even though extraction never connects;
    # only --build-neo4j does, and then this is the database it names.
    if neo4j_uri:
        os.environ["NEO4J_URI"] = neo4j_uri
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    for p in (str(BACKEND), str(BACKEND / "src")):
        if p not in sys.path:
            sys.path.insert(0, p)


# ── Matching and metrics ────────────────────────────────────────────────────

def _names(entity: dict) -> list[str]:
    return [entity["name"], *(entity.get("aliases") or [])]


def match_entities(predicted: list[dict], expected: list[dict]) -> list[tuple[int, int]]:
    """Pair predicted with gold entities: exact name/alias first, then fuzzy.

    The older harness matched greedily in one pass with a substring rule, so
    "CVE-2023-27997" could claim the gold "2023" before the gold CVE was tried,
    and "Guam" could claim "Naval Base Guam". Exact matches go first here, so
    the looser rules only see what is left.
    """
    from tests.eval.extraction_eval import _entity_matches, _normalize

    pairs: list[tuple[int, int]] = []
    used_p: set[int] = set()
    used_e: set[int] = set()
    for i, p in enumerate(predicted):
        pn = _normalize(p.get("name", ""))
        for j, e in enumerate(expected):
            if j not in used_e and pn in {_normalize(n) for n in _names(e)}:
                pairs.append((i, j))
                used_p.add(i)
                used_e.add(j)
                break
    for i, p in enumerate(predicted):
        if i in used_p:
            continue
        for j, e in enumerate(expected):
            if j not in used_e and _entity_matches(p.get("name", ""), e["name"], e.get("aliases")):
                pairs.append((i, j))
                used_p.add(i)
                used_e.add(j)
                break
    return pairs


def _prf(tp: int, n_pred: int, n_exp: int) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_exp if n_exp else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "tp": tp, "predicted": n_pred, "expected": n_exp}


def _category(entity_type: str) -> str:
    from intel_platform.models.type_hierarchy import get_parent_category
    return get_parent_category(entity_type or "")


GENERIC_REL = "ASSOCIATED_WITH"
DATE_REL = "OCCURRED_ON"


def relationship_class(rel: dict, entity_types: dict[str, str]) -> str:
    """``generic``, ``date_link`` or ``typed``: which relationship figure an edge counts in.

    The gold labels typed relations only. A generic association and a link
    that dates an event (OCCURRED_ON, or any edge with a Date endpoint) are
    legitimate output, and the second is what the timeline is built from, but
    against this gold each one counted as a false positive. ``typed`` scores
    the rest; ``all`` scores everything, as before.
    """
    if rel.get("rel_type") == GENERIC_REL:
        return "generic"
    if rel.get("rel_type") == DATE_REL or "Date" in (
            entity_types.get(rel.get("source_name", "")), entity_types.get(rel.get("target_name", ""))):
        return "date_link"
    return "typed"


def _match_relationships(rels: list[dict], gold_rels: list[dict], ends) -> set[int]:
    """Indices of the gold relationships some predicted edge matches (both ends, same type)."""
    matched: set[int] = set()
    for r in rels:
        src, tgt, typ = r.get("source_name", ""), r.get("target_name", ""), r.get("rel_type", "")
        for k, g in enumerate(gold_rels):
            if k not in matched and g["rel_type"] == typ and ends(g["source"], src) and ends(g["target"], tgt):
                matched.add(k)
                break
    return matched


def score_document(predicted: list[dict], rels: list[dict], gold: dict) -> dict:
    """Entity, typed-entity and relationship counts for one document."""
    from tests.eval.extraction_eval import _entity_matches

    expected = gold["entities"]
    pairs = match_entities(predicted, expected)
    typed_tp = sum(1 for i, j in pairs if predicted[i].get("entity_type") == expected[j]["entity_type"])
    cat_tp = sum(
        1 for i, j in pairs
        if _category(predicted[i].get("entity_type", "")) == _category(expected[j]["entity_type"])
    )
    confusion = Counter(
        f"{expected[j]['entity_type']} -> {predicted[i].get('entity_type', '?')}"
        for i, j in pairs if predicted[i].get("entity_type") != expected[j]["entity_type"]
    )
    per_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "pred": 0, "exp": 0})
    for p in predicted:
        per_type[p.get("entity_type", "?")]["pred"] += 1
    for e in expected:
        per_type[e["entity_type"]]["exp"] += 1
    for i, j in pairs:
        if predicted[i].get("entity_type") == expected[j]["entity_type"]:
            per_type[expected[j]["entity_type"]]["tp"] += 1

    # Relationships: a gold endpoint matches by name or alias; type must agree.
    by_name = {e["name"]: e for e in expected}
    gold_rels = gold.get("relationships", [])

    def ends(ref: str, name: str) -> bool:
        ent = by_name.get(ref)
        return _entity_matches(name, ref, ent.get("aliases") if ent else None)

    matched_gold = _match_relationships(rels, gold_rels, ends)
    rel_tp = len(matched_gold)
    # The same rule on both sides: gold has no generic or date edge today, and
    # if it ever gains one, `typed` must not count it as a typed miss.
    entity_types = {p.get("name", ""): p.get("entity_type", "") for p in predicted}
    classes = Counter(relationship_class(r, entity_types) for r in rels)
    typed_rels = [r for r in rels if relationship_class(r, entity_types) == "typed"]
    typed_gold = [g for g in gold_rels if g["rel_type"] not in (GENERIC_REL, DATE_REL)]
    rel_typed_tp = len(_match_relationships(typed_rels, typed_gold, ends))
    pair_only = 0
    for g in gold_rels:
        if any(
            (ends(g["source"], r.get("source_name", "")) and ends(g["target"], r.get("target_name", "")))
            or (ends(g["source"], r.get("target_name", "")) and ends(g["target"], r.get("source_name", "")))
            for r in rels
        ):
            pair_only += 1

    rel_types = Counter(r.get("rel_type", "?") for r in rels)
    gold_by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "exp": 0})
    for k, g in enumerate(gold_rels):
        gold_by_type[g["rel_type"]]["exp"] += 1
        if k in matched_gold:
            gold_by_type[g["rel_type"]]["tp"] += 1

    matched_p = {i for i, _ in pairs}
    matched_e = {j for _, j in pairs}
    return {
        "entities": {"tp": len(pairs), "pred": len(predicted), "exp": len(expected),
                     "typed_tp": typed_tp, "category_tp": cat_tp},
        "per_type": {k: dict(v) for k, v in per_type.items()},
        "confusion": dict(confusion),
        "relationships": {"tp": rel_tp, "pred": len(rels), "exp": len(gold_rels), "pair_found": pair_only},
        "relationships_typed": {"tp": rel_typed_tp, "pred": len(typed_rels), "exp": len(typed_gold)},
        "relationship_classes": {k: classes.get(k, 0) for k in ("typed", "generic", "date_link")},
        "rel_types_predicted": dict(rel_types),
        "rel_gold_by_type": {k: dict(v) for k, v in gold_by_type.items()},
        "false_positives": sorted(
            f"{predicted[i]['name']} [{predicted[i].get('entity_type', '?')}]"
            for i in range(len(predicted)) if i not in matched_p
        ),
        "false_negatives": sorted(
            f"{expected[j]['name']} [{expected[j]['entity_type']}]"
            for j in range(len(expected)) if j not in matched_e
        ),
        "mistyped": sorted(
            f"{predicted[i]['name']}: {expected[j]['entity_type']} -> {predicted[i].get('entity_type', '?')}"
            for i, j in pairs if predicted[i].get("entity_type") != expected[j]["entity_type"]
        ),
        "relationships_missed": sorted(
            f"{g['source']} -{g['rel_type']}-> {g['target']}"
            for k, g in enumerate(gold_rels) if k not in matched_gold
        ),
        "relationships_predicted": sorted(
            f"{r.get('source_name')} -{r.get('rel_type')}-> {r.get('target_name')}" for r in rels
        ),
    }


def evidence_spans(text: str, rels: list[dict]) -> dict:
    """Each edge's evidence span against the chunk: ``located`` when the chunk's
    text at ``evidence_offset`` is the evidence, ``unlocated`` with no evidence
    or offset, ``mismatched`` when the offset points elsewhere (a bug)."""
    counts = {"located": 0, "unlocated": 0, "mismatched": 0}
    for r in rels:
        off, ev = r.get("evidence_offset", -1), r.get("evidence") or ""
        if not isinstance(off, int) or off < 0 or not ev:
            counts["unlocated"] += 1
        elif text[off:off + len(ev)] == ev:
            counts["located"] += 1
        else:
            counts["mismatched"] += 1
    return counts


def aggregate(docs: list[dict]) -> dict:
    ent = Counter()
    rel = Counter()
    rel_typed = Counter()
    rel_classes = Counter()
    dropped = Counter()
    spans = Counter()
    per_type: dict[str, Counter] = defaultdict(Counter)
    confusion: Counter = Counter()
    rel_types: Counter = Counter()
    rel_gold: dict[str, Counter] = defaultdict(Counter)
    for d in docs:
        s = d["score"]
        ent.update(s["entities"])
        rel.update(s["relationships"])
        rel_typed.update(s["relationships_typed"])
        rel_classes.update(s["relationship_classes"])
        dropped.update(d.get("relationships_dropped_by_reason") or {})
        spans.update(d.get("evidence_spans") or {})
        for t, v in s["per_type"].items():
            per_type[t].update(v)
        confusion.update(s["confusion"])
        rel_types.update(s["rel_types_predicted"])
        for t, v in s["rel_gold_by_type"].items():
            rel_gold[t].update(v)
    n_rels = sum(rel_types.values())
    return {
        "documents": len(docs),
        "entity": _prf(ent["tp"], ent["pred"], ent["exp"]),
        # A match counts only when the type is right too: what typing fixes move.
        "entity_typed": _prf(ent["typed_tp"], ent["pred"], ent["exp"]),
        "type_accuracy": round(ent["typed_tp"] / ent["tp"], 4) if ent["tp"] else 0.0,
        "category_accuracy": round(ent["category_tp"] / ent["tp"], 4) if ent["tp"] else 0.0,
        "per_type": {
            t: _prf(v["tp"], v["pred"], v["exp"]) for t, v in sorted(per_type.items())
        },
        "type_confusion": dict(confusion.most_common()),
        # Every predicted edge against the gold ("all"), and the typed ones only:
        # generic associations and date links are left out (see relationship_class).
        "relationship": _prf(rel["tp"], rel["pred"], rel["exp"]),
        "relationship_typed": _prf(rel_typed["tp"], rel_typed["pred"], rel_typed["exp"]),
        "relationship_classes_predicted": {k: rel_classes.get(k, 0) for k in ("typed", "generic", "date_link")},
        # Model edges the extraction itself dropped, by reason (unlisted_endpoint,
        # evidence_not_verbatim, evidence_missing_endpoint, ...).
        "relationships_dropped_by_reason": dict(sorted(dropped.items())),
        # Predicted edges whose evidence is the chunk's text at their offset.
        "evidence_spans": {k: spans.get(k, 0) for k in ("located", "unlocated", "mismatched")},
        # Gold pairs some predicted edge connects, in either direction, of any type.
        "relationship_pairs_found": rel["pair_found"],
        "relationship_types_predicted": dict(rel_types.most_common()),
        "associated_with_share": round(rel_types.get("ASSOCIATED_WITH", 0) / n_rels, 4) if n_rels else 0.0,
        "relationship_recall_by_type": {
            t: {"tp": v["tp"], "expected": v["exp"]} for t, v in sorted(rel_gold.items())
        },
    }


# ── Running ─────────────────────────────────────────────────────────────────

def discover(set_name: str) -> list[str]:
    d = SETS[set_name]
    return sorted(
        p.name[: -len("_expected.json")]
        for p in d.glob("*_expected.json")
        if (d / (p.name[: -len("_expected.json")] + ".txt")).exists()
    )


def load(set_name: str, name: str) -> tuple[str, dict]:
    from tests.eval.extraction_eval import strip_fixture_notice

    d = SETS[set_name]
    text = strip_fixture_notice((d / f"{name}.txt").read_text(encoding="utf-8"))
    gold = json.loads((d / f"{name}_expected.json").read_text(encoding="utf-8"))
    return text, gold


async def _extract(mode: str, text: str, doc_id: str, retries: int):
    from intel_platform.services.extraction import (
        extract_entities_hybrid, extract_entities_llm, extract_entities_nlp,
    )

    if mode == "nlp":
        # Synchronous on purpose: one spaCy pipeline, never shared across threads.
        return extract_entities_nlp(text, doc_id)
    fn = extract_entities_llm if mode == "llm" else extract_entities_hybrid
    result = await fn(text, doc_id)
    attempt = 0
    while result.degraded and attempt < retries:
        attempt += 1
        # A rate limit is per minute (a Cohere trial key allows 20 calls), so
        # a retry a few seconds later meets the same limit; wait it out.
        rate_limited = "TooManyRequests" in result.reason or "429" in result.reason
        await asyncio.sleep((30 if rate_limited else 2) * attempt)
        result = await fn(text, doc_id)
    return result


def _build(driver, mode: str, set_name: str, name: str, entities: list[dict], rels: list[dict]) -> dict:
    """Run one document through the real graph build in a throwaway project."""
    import copy

    from intel_platform.graph.store import GraphStore
    from intel_platform.services.graph_builder import build_graph_from_extractions

    project = f"eval-{mode}-{set_name}-{name}".lower()
    with driver.session() as s:
        s.run("MATCH (n) WHERE n.project_id = $p DETACH DELETE n", p=project)
    try:
        return build_graph_from_extractions(
            GraphStore(driver), copy.deepcopy(entities), copy.deepcopy(rels), project,
            source_doc_id=f"eval-{name}",
        )
    finally:
        with driver.session() as s:
            s.run("MATCH (n) WHERE n.project_id = $p DETACH DELETE n", p=project)


class ReplyCache:
    """Model replies keyed by the exact request, so a re-run can replay them.

    Fixes to what happens *after* the model answers (type canon, relationship
    normalisation, provenance filtering) are measured on the same replies as
    the baseline; otherwise sampling noise between two live runs swamps the
    change. A changed prompt is a different key, so it is always asked live.
    """

    def __init__(self, path: Path | None, model: str, refresh: bool = False, replay_only: bool = False):
        self.path = path
        self.model = model
        # Ask live even when a reply is recorded, and record the new one.
        self.refresh = refresh
        # Never ask live: a request with no recorded reply fails (and the
        # document degrades, which the report lists) instead of being billed.
        self.replay_only = replay_only
        self.data: dict[str, dict] = {}
        if path and path.is_file():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        self.hits = 0
        self.live = 0
        self.missed = 0

    def key(self, system: str, messages: list[dict]) -> str:
        import hashlib

        blob = json.dumps({"model": self.model, "system": system, "messages": messages}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def save(self) -> None:
        # Nothing asked live means nothing new to record; rewriting the file
        # anyway touched it on every replayed run.
        if self.path and self.live:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(dict(sorted(self.data.items())), indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8", newline="\n")


class CachingProvider:
    """Wraps the selected provider; answers from the cache when it can."""

    def __init__(self, inner, cache: ReplyCache):
        self._inner = inner
        self._cache = cache
        self._model = getattr(inner, "_model", "")

    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3,
                       max_tokens: int = 4096):
        from intel_platform.llm.base import LLMResponse

        k = self._cache.key(system, messages)
        hit = None if self._cache.refresh else self._cache.data.get(k)
        if hit is not None:
            self._cache.hits += 1
            return LLMResponse(content=hit["content"], model=hit.get("model", self._model),
                               input_tokens=0, output_tokens=0)
        if self._cache.replay_only:
            self._cache.missed += 1
            raise LookupError("no recorded reply for this request (--replay-only)")
        resp = await self._inner.generate(messages=messages, system=system, temperature=temperature,
                                          max_tokens=max_tokens)
        self._cache.live += 1
        if resp.content:
            self._cache.data[k] = {"content": resp.content, "model": resp.model}
        return resp


async def run(mode: str, sets: list[str], concurrency: int, retries: int, limit: int | None,
              build_uri: str | None, cache_path: Path | None = None, refresh: bool = False,
              replay_only: bool = False) -> dict:
    from intel_platform.config import settings

    provider_info: dict = {}
    cache: ReplyCache | None = None
    if mode != "nlp":
        # Keys come from the environment, never the database: a stored key is
        # not part of an eval, and the lookup would need a live Postgres.
        import intel_platform.api.routes.admin_config as admin_config
        import intel_platform.llm.providers as providers

        async def _no_db_key(provider: str) -> None:
            return None

        admin_config.get_active_api_key = _no_db_key
        provider = await providers._get_extraction_provider()
        if not provider:
            raise SystemExit("no LLM provider configured for an llm/hybrid run")
        model = getattr(provider, "_model", None) or getattr(provider, "model", None) or ""
        provider_info = {"provider": type(provider).__name__, "model": model}
        # Selection happened above, in providers.py; from here extraction gets
        # the same provider back, behind the reply cache.
        cache = ReplyCache(cache_path, f"{type(provider).__name__}/{model}", refresh=refresh,
                           replay_only=replay_only)
        wrapped = CachingProvider(provider, cache)

        async def _selected() -> CachingProvider:
            return wrapped

        providers._get_extraction_provider = _selected

    driver = None
    if build_uri:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            build_uri, auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "changeme")),
        )

    sem = asyncio.Semaphore(concurrency)
    jobs = [(s, n) for s in sets for n in discover(s)]
    if limit:
        jobs = jobs[:limit]

    async def one(set_name: str, name: str) -> dict:
        text, gold = load(set_name, name)
        async with sem:
            t0 = time.perf_counter()
            result = await _extract(mode, text, f"eval-{name}", retries)
            elapsed = time.perf_counter() - t0
        entities, rels = result
        doc = {
            "set": set_name, "name": name,
            "method": getattr(result, "method", mode),
            "degraded": bool(getattr(result, "degraded", False)),
            "reason": getattr(result, "reason", ""),
            "seconds": round(elapsed, 2),
            "relationships_dropped_by_reason": dict(getattr(result, "relationships_dropped_by_reason", None) or {}),
            "evidence_spans": evidence_spans(text, rels),
            "score": score_document(entities, rels, gold),
        }
        if driver is not None:
            try:
                b = await asyncio.to_thread(_build, driver, mode, set_name, name, entities, rels)
            except Exception as exc:
                # A build that raises is a finding about the build, not a reason
                # to lose the run: recorded per document, by exception type.
                doc["build"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                print(f"  {set_name}/{name}: graph build raised {type(exc).__name__}: {exc}", flush=True)
            else:
                doc["build"] = {k: b.get(k) for k in (
                    "entities_created", "entities_merged", "entities_filtered", "dates_absorbed",
                    "dates_orphaned", "relationships_created", "relationships_retired",
                    "relationships_dropped", "relationships_dropped_by_type", "relationships_dropped_by_reason",
                )}
        print(f"  {set_name}/{name}: {doc['method']}{' DEGRADED' if doc['degraded'] else ''} "
              f"{doc['seconds']}s", flush=True)
        return doc

    try:
        docs = await asyncio.gather(*(one(s, n) for s, n in jobs))
    finally:
        if driver is not None:
            driver.close()
        if cache is not None:
            # Saved even when the run fails: the replies were paid for.
            cache.save()

    docs = sorted(docs, key=lambda d: (d["set"], d["name"]))
    if cache is not None:
        provider_info["replies"] = {"live": cache.live, "replayed": cache.hits,
                                    **({"missed": cache.missed} if cache.replay_only else {})}
    report = {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "git_commit": _git_head(),
        "spacy_model": settings.spacy_model,
        **({"llm": provider_info} if provider_info else {}),
        "degraded_documents": [f"{d['set']}/{d['name']}: {d['reason']}" for d in docs if d["degraded"]],
        "overall": aggregate(docs),
        "by_set": {s: aggregate([d for d in docs if d["set"] == s]) for s in sets},
        "documents": docs,
    }
    if driver is not None:
        report["build"] = _build_totals(docs)
    return report


def _build_totals(docs: list[dict]) -> dict:
    tot: Counter = Counter()
    dropped: Counter = Counter()
    reasons: Counter = Counter()
    errors = []
    for d in docs:
        b = d.get("build") or {}
        if "error" in b:
            errors.append(f"{d['set']}/{d['name']}: {b['error']}")
        for k, v in b.items():
            if isinstance(v, int):
                tot[k] += v
        dropped.update(b.get("relationships_dropped_by_type") or {})
        reasons.update(b.get("relationships_dropped_by_reason") or {})
    return {**dict(sorted(tot.items())), "relationships_dropped_by_type": dict(dropped.most_common()),
            "relationships_dropped_by_reason": dict(sorted(reasons.items())), "errors": errors}


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


# ── Reporting ───────────────────────────────────────────────────────────────

def _row(label: str, m: dict) -> str:
    return f"| {label} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['tp']} | {m['predicted']} | {m['expected']} |"


def markdown(report: dict) -> str:
    o = report["overall"]
    lines = [
        f"# Corpus extraction eval — `{report['mode']}`",
        "",
        f"Generated {report['generated_at']} at `{report['git_commit']}`; spaCy `{report['spacy_model']}`"
        + (f"; LLM `{report['llm']['provider']}` / `{report['llm']['model']}` "
           f"({report['llm'].get('replies', {}).get('live', 0)} live replies, "
           f"{report['llm'].get('replies', {}).get('replayed', 0)} replayed)" if report.get("llm") else "")
        + ".",
        "",
    ]
    if report["degraded_documents"]:
        lines += [f"**{len(report['degraded_documents'])} document(s) degraded to NLP** — their numbers are "
                  "NLP numbers:", ""] + [f"- {d}" for d in report["degraded_documents"]] + [""]
    else:
        lines += ["No document degraded: every score below is the requested mode's own.", ""]
    lines += [
        "Relationships are scored twice. **typed** leaves out generic associations (`ASSOCIATED_WITH`) and "
        "date links (`OCCURRED_ON`, or any edge with a Date endpoint), which the gold does not label; **all** "
        "scores every edge.",
        "",
        "| Set | Docs | Entity P / R / F1 | Typed F1 | Type acc | Rel typed P / R / F1 | Typed TP / Pred / Gold "
        "| Rel all P / R / F1 | All TP / Pred / Gold |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, a in [*report["by_set"].items(), ("**combined**", o)]:
        en, rl, rt = a["entity"], a["relationship"], a["relationship_typed"]
        lines.append(
            f"| {label} | {a['documents']} | {en['precision']:.3f} / {en['recall']:.3f} / {en['f1']:.3f} "
            f"| {a['entity_typed']['f1']:.3f} | {a['type_accuracy']:.3f} "
            f"| {rt['precision']:.3f} / {rt['recall']:.3f} / {rt['f1']:.3f} | {rt['tp']} / {rt['predicted']} / {rt['expected']} "
            f"| {rl['precision']:.3f} / {rl['recall']:.3f} / {rl['f1']:.3f} | {rl['tp']} / {rl['predicted']} / {rl['expected']} |"
        )
    classes = o["relationship_classes_predicted"]
    dropped = o.get("relationships_dropped_by_reason") or {}
    spans = o.get("evidence_spans") or {"located": 0, "unlocated": 0, "mismatched": 0}
    lines += [
        "",
        "| Combined metric | P | R | F1 | TP | Pred | Gold |",
        "|---|---|---|---|---|---|---|",
        _row("Entities (name)", o["entity"]),
        _row("Entities (name + type)", o["entity_typed"]),
        _row("Relationships (typed)", o["relationship_typed"]),
        _row("Relationships (all)", o["relationship"]),
    ]
    lines += [
        "",
        f"Type accuracy on matched entities: **{o['type_accuracy']:.3f}** "
        f"(parent category: {o['category_accuracy']:.3f}). "
        f"Gold relationship pairs connected by any edge: {o['relationship_pairs_found']} of "
        f"{o['relationship']['expected']}. Predicted edges: {classes['typed']} typed, {classes['generic']} "
        f"generic, {classes['date_link']} date links (ASSOCIATED_WITH share {o['associated_with_share']:.1%}). "
        "Dropped by the extraction: "
        + (", ".join(f"{k} {v}" for k, v in dropped.items()) or "none") + ". "
        f"Evidence spans: {spans['located']} located at their offset, {spans['unlocated']} without one, "
        f"{spans['mismatched']} mismatched.",
        "",
        "## Per type (name + type must match)",
        "",
        "| Type | P | R | F1 | TP | Pred | Gold |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [_row(t, m) for t, m in o["per_type"].items()]
    lines += ["", "## Type confusion (gold -> predicted)", ""]
    lines += [f"- {k}: {v}" for k, v in o["type_confusion"].items()] or ["- none"]
    lines += ["", "## Relationships", "", "Predicted types: " + (", ".join(
        f"{k} {v}" for k, v in o["relationship_types_predicted"].items()) or "none") + ".", "",
        "| Gold type | Found | Gold |", "|---|---|---|"]
    lines += [f"| {t} | {v['tp']} | {v['expected']} |" for t, v in o["relationship_recall_by_type"].items()]
    if report.get("build"):
        b = report["build"]
        lines += ["", "## Graph build (real `build_graph_from_extractions`, throwaway projects)", "",
                  f"Relationships created {b.get('relationships_created', 0)}, retired "
                  f"{b.get('relationships_retired', 0)}, dropped {b.get('relationships_dropped', 0)} "
                  f"{b.get('relationships_dropped_by_type') or ''} {b.get('relationships_dropped_by_reason') or ''}; "
                  f"entities created "
                  f"{b.get('entities_created', 0)}, filtered {b.get('entities_filtered', 0)}, "
                  f"dates orphaned {b.get('dates_orphaned', 0)}."]
        if b.get("errors"):
            lines += ["", f"**The build raised on {len(b['errors'])} document(s):**", ""]
            lines += [f"- {e}" for e in b["errors"]]
    cyber = [d for d in report["documents"] if d["set"] == "cyber"]
    if cyber:
        lines += ["", "## Cyber documents in full", ""]
        for d in cyber:
            s = d["score"]
            lines += [f"### {d['name']}", "",
                      f"- mistyped: {', '.join(s['mistyped']) or 'none'}",
                      f"- missed: {', '.join(s['false_negatives']) or 'none'}",
                      f"- extra: {', '.join(s['false_positives']) or 'none'}",
                      f"- edges: {'; '.join(s['relationships_predicted']) or 'none'}",
                      f"- gold edges missed: {'; '.join(s['relationships_missed']) or 'none'}"]
            if d.get("build", {}).get("error"):
                lines.append(f"- build raised: {d['build']['error']}")
            elif d.get("build"):
                lines.append(f"- build: created {d['build']['relationships_created']}, dropped "
                             f"{d['build']['relationships_dropped']} {d['build']['relationships_dropped_by_type']}")
            lines.append("")
    for set_name in report["by_set"]:
        if set_name == "cyber":
            continue
        docs = [d for d in report["documents"] if d["set"] == set_name]
        fp = Counter(x for d in docs for x in d["score"]["false_positives"])
        fn = Counter(x for d in docs for x in d["score"]["false_negatives"])
        mt = Counter(x.split(": ", 1)[1] for d in docs for x in d["score"]["mistyped"])
        lines += [f"## {set_name}: most frequent misses, extras and mistypes", "",
                  "Missed: " + (", ".join(f"{k} x{v}" for k, v in fn.most_common(15)) or "none") + ".", "",
                  "Extra: " + (", ".join(f"{k} x{v}" for k, v in fp.most_common(15)) or "none") + ".", "",
                  "Mistyped (gold -> predicted): "
                  + (", ".join(f"{k} x{v}" for k, v in mt.most_common(10)) or "none") + ".", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score extraction against the eval corpus.")
    ap.add_argument("--mode", choices=MODES, required=True)
    ap.add_argument("--sets", nargs="+", choices=sorted(SETS), default=["openrep", "kestrel", "cyber"])
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--retries", type=int, default=2, help="re-run a document whose LLM half degraded")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--build-neo4j", default=None, metavar="BOLT_URI",
                    help="also run the graph build against this Neo4j (throwaway projects)")
    ap.add_argument("--llm-cache", type=Path, default=Path(__file__).resolve().parent / "llm_replies.json",
                    help="model replies to replay, and where new ones are recorded")
    ap.add_argument("--no-cache", action="store_true", help="ask the model for every document; record nothing")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="ask the model for every document and record its replies over any recorded ones")
    ap.add_argument("--replay-only", action="store_true",
                    help="never ask the model: a request with no recorded reply degrades the document")
    args = ap.parse_args(argv)
    if args.replay_only and (args.no_cache or args.refresh_cache):
        ap.error("--replay-only cannot be combined with --no-cache or --refresh-cache")

    if args.mode != "nlp":
        env_path = load_provider_env(args.env_file)
        print(f"provider settings from {env_path or 'the process environment only'}", flush=True)
    _prepare_imports(args.build_neo4j)
    report = asyncio.run(run(
        args.mode, args.sets, args.concurrency, 0 if args.replay_only else args.retries, args.limit,
        args.build_neo4j, cache_path=None if args.no_cache else args.llm_cache, refresh=args.refresh_cache,
        replay_only=args.replay_only,
    ))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_dir / f"corpus_eval_{args.mode}.json"
    out_md = args.out_dir / f"corpus_eval_{args.mode}.md"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    out_md.write_text(markdown(report), encoding="utf-8", newline="\n")
    o = report["overall"]
    print(f"{args.mode}: entity F1 {o['entity']['f1']:.3f}, typed F1 {o['entity_typed']['f1']:.3f}, "
          f"type acc {o['type_accuracy']:.3f}, relationship F1 typed {o['relationship_typed']['f1']:.3f} "
          f"/ all {o['relationship']['f1']:.3f}, "
          f"degraded {len(report['degraded_documents'])}")
    print(f"wrote {out_json} and {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
