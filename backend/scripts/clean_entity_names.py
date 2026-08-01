"""Apply the current entity-name rules to entities already in the graph.

The name cleaning in `services.graph_builder` runs at write time, so every fix
to it only helps entities extracted *after* the fix. Live graphs therefore hold
names the pipeline would no longer produce — markdown headings stored as
`Financial` nodes, and link spans like `Europe]` or
`BBC News Mundo (Spanish)](https://www.bbc.com/mundo`.

That is not only cosmetic. A node named `sophie himka]` can never resolve
against the `Sophie Himka` the fixed pipeline now writes, so the duplicate is
permanent and grows with every mention.

Three passes, in order:

  1. **normalize** — rewrite `name` through `_clean_entity_name`.
  2. **drop** — delete nodes whose cleaned name is junk (`_is_junk_name`): pure
     markup with no alphanumeric character, or a captured navigation block.
  3. **merge** — collapse nodes that now share (project_id, label, name),
     keeping the oldest and moving every relationship onto it.

Dry run by default: it reports what it would do and changes nothing. Deleting
and merging graph nodes cannot be undone, so applying is an explicit choice.

    cd backend && uv run python scripts/clean_entity_names.py             # report
    cd backend && uv run python scripts/clean_entity_names.py --apply     # do it
    cd backend && uv run python scripts/clean_entity_names.py --project X # scope it
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

from neo4j import GraphDatabase

from intel_platform.graph.schema import ENTITY_NAME_LABELS
from intel_platform.services.graph_builder import _clean_entity_name, _is_junk_name


def _printable_output() -> None:
    """Entity names are not ASCII, and the console it prints to may be.

    Without this the script dies partway through its report on a Windows
    terminal (cp1252) the moment it reaches a name with an en dash in it —
    having already scanned the whole graph.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _connection() -> tuple[str, str, str]:
    """Where to connect, preferring Settings but not requiring it.

    Settings is the SSOT for the service, but it needs the full config surface
    and raises without it — and `.env` lives at the repo root while this runs
    from `backend/`. A maintenance script should not be unusable because an
    unrelated setting is missing, so fall back to the same NEO4J_* variables
    docker-compose sets.
    """
    try:
        from intel_platform.config import settings

        return settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
    except Exception:
        return (
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "changeme"),
        )

# Only labels the name index covers. Project/User/Snapshot/Date are excluded
# there because they are not analyst-facing entities and must never be merged
# against; the same reasoning applies to rewriting their names.
LABELS = list(ENTITY_NAME_LABELS)

# Labels whose names are not identities, so equal names are not the same thing.
# Caught by the dry run on a live graph: dozens of separate uploads all carry
# the placeholder name `text_input`, and merging by name would have collapsed
# unrelated documents into one. Their names are still normalized and their junk
# still dropped — only the merge is unsafe.
NEVER_MERGE = {"Document"}


def _scan(session, project_id: str | None):
    """Every candidate node with its current and cleaned name."""
    query = """
    MATCH (n)
    WHERE n.name IS NOT NULL AND n.project_id IS NOT NULL
      AND any(l IN labels(n) WHERE l IN $labels)
      AND ($project IS NULL OR n.project_id = $project)
    RETURN n.id AS id, n.name AS name, n.project_id AS project,
           labels(n)[0] AS label, n.created_at AS created
    """
    return list(session.run(query, labels=LABELS, project=project_id))


def plan(rows):
    """Split the scan into the three passes. Pure, so it is testable."""
    renames, drops = [], []
    # Keyed on what the node will be called once pass 1 has run, which is what
    # decides whether it collides with another node.
    by_key: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    for r in rows:
        cleaned = _clean_entity_name(r["name"])
        if _is_junk_name(cleaned):
            drops.append(dict(r))
            continue
        if cleaned != r["name"]:
            renames.append({**dict(r), "cleaned": cleaned})
        if r["label"] not in NEVER_MERGE:
            by_key[(r["project"], r["label"], cleaned.lower())].append({**dict(r), "cleaned": cleaned})

    merges = [g for g in by_key.values() if len(g) > 1]
    return renames, drops, merges


def _survivor(group: list[dict]) -> dict:
    """Keep the oldest node: it is the one other data most likely points at."""
    return min(group, key=lambda n: (n.get("created") or "", n["id"]))


def apply_renames(session, renames) -> int:
    for r in renames:
        session.run("MATCH (n {id: $id}) SET n.name = $name", id=r["id"], name=r["cleaned"])
    return len(renames)


def apply_drops(session, drops) -> int:
    for r in drops:
        session.run("MATCH (n {id: $id}) DETACH DELETE n", id=r["id"])
    return len(drops)


def apply_merges(session, merges) -> int:
    """Move relationships onto the survivor, then delete the duplicates.

    apoc.refactor.mergeNodes would be shorter, but it is not guaranteed present
    on every deployment and a failed half-merge is worse than a slower one.
    """
    moved = 0
    for group in merges:
        keep = _survivor(group)
        for dup in group:
            if dup["id"] == keep["id"]:
                continue
            session.run(
                """
                MATCH (dup {id: $dup}), (keep {id: $keep})
                WITH dup, keep
                CALL {
                    WITH dup, keep
                    MATCH (dup)-[r]->(o) WHERE o <> keep
                    CALL apoc.create.relationship(keep, type(r), properties(r), o) YIELD rel
                    RETURN count(rel) AS out
                }
                CALL {
                    WITH dup, keep
                    MATCH (i)-[r]->(dup) WHERE i <> keep
                    CALL apoc.create.relationship(i, type(r), properties(r), keep) YIELD rel
                    RETURN count(rel) AS inc
                }
                DETACH DELETE dup
                RETURN out + inc AS moved
                """,
                dup=dup["id"], keep=keep["id"],
            )
            moved += 1
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually rewrite, delete and merge (default: report only)")
    ap.add_argument("--project", default=None, help="limit to one project_id")
    ap.add_argument("--examples", type=int, default=8, help="how many examples to print per pass")
    args = ap.parse_args()
    _printable_output()

    uri, user, password = _connection()
    print(f"connecting to {uri}")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            rows = _scan(session, args.project)
            renames, drops, merges = plan(rows)

            print(f"scanned {len(rows)} entities" + (f" in project {args.project}" if args.project else ""))
            print(f"  rename : {len(renames)}")
            print(f"  drop   : {len(drops)}")
            print(f"  merge  : {len(merges)} groups, {sum(len(g) - 1 for g in merges)} nodes absorbed")

            for label, items in (("rename", renames), ("drop", drops)):
                for r in items[:args.examples]:
                    shown = f"{r['name']!r}" + (f" -> {r['cleaned']!r}" if label == "rename" else "")
                    print(f"    {label:<7} {r['label']:<14} {shown}")
            for g in merges[:args.examples]:
                keep = _survivor(g)
                print(f"    merge   {g[0]['label']:<14} {keep['cleaned']!r} <- {len(g) - 1} duplicate(s)")

            if not args.apply:
                print("\nDry run — nothing changed. Re-run with --apply to carry it out.")
                return 0

            print("\napplying...")
            print(f"  renamed  {apply_renames(session, renames)}")
            print(f"  dropped  {apply_drops(session, drops)}")
            print(f"  absorbed {apply_merges(session, merges)}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
