#!/usr/bin/env python3
"""Build the corpus-backed extraction eval set from a local Qdrant.

Scrolls the fictional exercise collections (``kestrel``, ``openrep``), keeps
the chunks that carry an "Entities identified in this reporting:" line, picks
about forty of them for variety, strips every classification and releasability
marking, and writes each as a fixture in the format ``tests/eval`` already
reads:

    tests/fixtures/extraction_corpus/<chunk>.txt
    tests/fixtures/extraction_corpus/<chunk>_expected.json

The entity line is only the *seed* of the gold set. A seed file is written
only where none exists, so re-running the builder never overwrites a gold file
someone has reviewed against the text (``--reseed`` does, deliberately).

This repository is public. The stored text keeps the ``EXERCISE — FICTIONAL``
banner and loses every marking; the build fails rather than write a file that
still carries one.

Usage (from backend/):
    uv run python scripts/build_eval_corpus.py                 # build / refresh text
    uv run python scripts/build_eval_corpus.py --dry-run       # show the selection
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ENTITY_LINE = "Entities identified in this reporting:"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "extraction_corpus"

NOTICE = (
    "FICTIONAL EXERCISE REPORTING — NOT A REAL INTELLIGENCE PRODUCT.\n"
    "Taken from a synthetic exercise collection ({collection}, chunk {chunk_id}) to\n"
    "evaluate entity extraction. Every unit, vessel, place and person is invented.\n"
    "All classification and releasability markings have been removed.\n"
    "--- BEGIN FIXTURE ---\n"
)

# ── Markings ────────────────────────────────────────────────────────────────

# Short-form classification levels used as portion and banner markings.
_LEVELS = r"(?:CTS|NS|NC|NR|NU|CTS-A|NS-A|TS|S|C|R|U)"
_LONG_LEVELS = (
    r"(?:COSMIC TOP SECRET|NATO SECRET|NATO CONFIDENTIAL|NATO RESTRICTED|NATO UNCLASSIFIED"
    r"|TOP SECRET|SECRET|CONFIDENTIAL|RESTRICTED|UNCLASSIFIED)"
)
_CAVEAT = r"(?:REL[- ](?:TO[- ])?[A-Z][A-Z0-9, -]*|NOFORN|ORCON|FVEY|RELIDO|PROPIN)"

# A banner line: "NS//REL-NATO", "CTS//REL-FVEY//REL-NATO", "NATO SECRET".
_BANNER_LINE = re.compile(
    rf"^[ \t]*(?:{_LEVELS}|{_LONG_LEVELS})(?:[ \t]*//[ \t]*{_CAVEAT})*[ \t]*$",
    re.MULTILINE,
)
# A portion marking after the paragraph number: "1. (NS) Source reported".
_PORTION = re.compile(rf"\((?:{_LEVELS}|{_LONG_LEVELS})(?://{_CAVEAT})*\)[ \t]*")

# What must not survive. Deliberately broader than the strippers: a marking
# form they do not know fails the build instead of reaching the repository.
_RESIDUE = re.compile(
    rf"\b(?:COSMIC|NATO (?:SECRET|CONFIDENTIAL|RESTRICTED|UNCLASSIFIED)|NOFORN|ORCON|FVEY|REL-[A-Z]+)\b"
    rf"|\((?:{_LEVELS})(?://[^)]*)?\)"
    rf"|^[ \t]*{_LEVELS}[ \t]*(?://|$)"
    rf"|//[ \t]*REL",
    re.MULTILINE,
)


class MarkingResidue(ValueError):
    """Text still carries a classification or releasability marking."""


def strip_markings(text: str) -> str:
    """Remove classification and releasability markings; keep everything else.

    The ``EXERCISE — FICTIONAL`` banner is not a marking and is kept: it is
    what tells a reader this is invented.
    """
    out = _BANNER_LINE.sub("", text)
    out = _PORTION.sub("", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
    residue = _RESIDUE.search(out)
    if residue:
        raise MarkingResidue(f"marking survived stripping: {residue.group()!r}")
    return out


# ── Seed gold ───────────────────────────────────────────────────────────────

_HULL = re.compile(r"^(?P<name>.+?)\s*\((?P<hull>[A-Z]{1,3}-\d{2,4})\)$")
_ORG_WORDS = (
    "Group", "Regiment", "Battalion", "Detachment", "Authority", "Service",
    "Brigade", "Division", "Squadron", "Command", "Cell", "Agency", "Ministry",
)


def split_entity_line(line: str) -> list[str]:
    """Split "A (A-411), B, C." on commas outside parentheses."""
    parts, depth, cur = [], 0, []
    for ch in line.strip().rstrip("."):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def seed_entity(raw: str) -> dict:
    """A first guess at one gold entity from its entry on the seed line."""
    m = _HULL.match(raw)
    if m:
        # A hull number makes it a vessel: Ship is the hierarchy's type for one.
        return {"name": m.group("name"), "entity_type": "Ship", "aliases": [raw, m.group("hull")]}
    if any(w in raw.split() for w in _ORG_WORDS):
        return {"name": raw, "entity_type": "Organization"}
    return {"name": raw, "entity_type": "REVIEW"}


def seed_expected(text: str, collection: str, chunk_id: str, doc_id: str) -> dict:
    m = re.search(re.escape(ENTITY_LINE) + r"\s*(.+)", text)
    entities = [seed_entity(e) for e in split_entity_line(m.group(1))] if m else []
    return {
        "source": {"collection": collection, "chunk_id": chunk_id, "doc_id": doc_id},
        "review": "seed — not yet reviewed against the text",
        "entities": entities,
        "relationships": [],
    }


# ── Qdrant ──────────────────────────────────────────────────────────────────

def scroll(client: httpx.Client, base: str, collection: str) -> list[dict]:
    points: list[dict] = []
    offset = None
    while True:
        body: dict = {"limit": 100, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        r = client.post(f"{base}/collections/{collection}/points/scroll", json=body)
        r.raise_for_status()
        result = r.json()["result"]
        points.extend(result["points"])
        offset = result.get("next_page_offset")
        if offset is None:
            return points


def candidate_chunks(points: list[dict], collection: str) -> list[dict]:
    out = []
    for p in points:
        payload = p.get("payload") or {}
        text = payload.get("text") or ""
        if ENTITY_LINE not in text:
            continue
        m = re.search(re.escape(ENTITY_LINE) + r"\s*(.+)", text)
        out.append({
            "collection": collection,
            "chunk_id": str(payload.get("chunk_id") or p["id"]),
            "doc_id": str(payload.get("doc_id") or ""),
            "int_type": payload.get("int_type") or "",
            "seed_line": m.group(1).strip() if m else "",
            "text": text,
        })
    return sorted(out, key=lambda c: (c["collection"], c["chunk_id"]))


def select(cands: list[dict], count: int) -> list[dict]:
    """Every distinct seed line once, then fill by the least-represented discipline.

    Deterministic: candidates arrive sorted, and ties break on that order.
    """
    by_line: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_line[c["seed_line"]].append(c)

    chosen: list[dict] = []
    per_type: Counter = Counter()
    seen_docs: set[str] = set()

    def take(c: dict) -> None:
        chosen.append(c)
        per_type[c["int_type"]] += 1
        seen_docs.add(c["doc_id"])

    # Pass 1: one chunk per distinct seed line, preferring a discipline not yet taken.
    for line in sorted(by_line):
        group = by_line[line]
        pick = min(group, key=lambda c: (per_type[c["int_type"]], cands.index(c)))
        take(pick)
        if len(chosen) >= count:
            return chosen

    # Pass 2: fill to `count` from unseen documents, least-represented discipline first.
    remaining = [c for c in cands if c not in chosen and c["doc_id"] not in seen_docs]
    while len(chosen) < count and remaining:
        pick = min(remaining, key=lambda c: (per_type[c["int_type"]], cands.index(c)))
        take(pick)
        remaining = [c for c in remaining if c is not pick and c["doc_id"] not in seen_docs]
    return chosen


def fixture_stem(chunk_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", chunk_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--qdrant", default="http://127.0.0.1:6333")
    ap.add_argument("--collections", nargs="+", default=["kestrel", "openrep"])
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--reseed", action="store_true", help="overwrite existing _expected.json with a fresh seed")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    cands: list[dict] = []
    with httpx.Client(timeout=60) as client:
        for name in args.collections:
            pts = scroll(client, args.qdrant.rstrip("/"), name)
            found = candidate_chunks(pts, name)
            print(f"{name}: {len(pts)} points, {len(found)} with an entity line")
            cands.extend(found)

    chosen = select(cands, args.count)
    print(f"selected {len(chosen)} chunks; disciplines {dict(Counter(c['int_type'] for c in chosen))}; "
          f"{len({c['seed_line'] for c in chosen})} distinct seed lines")
    if args.dry_run:
        for c in chosen:
            print(f"  {c['chunk_id']:<14} {c['int_type']:<8} {c['seed_line']}")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    written = seeded = 0
    for c in chosen:
        stem = fixture_stem(c["chunk_id"])
        body = strip_markings(c["text"])
        notice = NOTICE.format(collection=c["collection"], chunk_id=c["chunk_id"])
        (args.out / f"{stem}.txt").write_text(notice + "\n" + body, encoding="utf-8", newline="\n")
        written += 1
        expected = args.out / f"{stem}_expected.json"
        if args.reseed or not expected.exists():
            seed = seed_expected(body, c["collection"], c["chunk_id"], c["doc_id"])
            expected.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            seeded += 1
    print(f"wrote {written} texts, {seeded} seed gold files to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
