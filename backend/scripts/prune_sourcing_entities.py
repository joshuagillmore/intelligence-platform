"""Remove entities that were sourcing, not indicators.

Extraction used to mint a Domain and a URL node for every host in a document,
so graphs built before that changed carry URL nodes for share links, cookie
banners and "read more" footers, plus hosts mangled by percent-encoding
(``2fen.wikipedia.org`` from an encoded ``/``). Re-extraction would not remove
them: nothing deletes an entity that is no longer produced.

Dry run by default. Prints what it would delete and stops:

    uv run python scripts/prune_sourcing_entities.py                 # all projects
    uv run python scripts/prune_sourcing_entities.py --project <id>
    uv run python scripts/prune_sourcing_entities.py --apply

Only two classes are touched, both chosen so a real indicator cannot be caught:

* URL nodes with no relationships. A URL that something in the graph actually
  points at is left alone regardless of how it got there.
* Domain/URL nodes whose name still carries percent-encoding debris. These are
  not hostnames at all.

A defanged indicator that was correctly extracted has relationships and a
well-formed name, so neither rule can reach it.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from neo4j import GraphDatabase

# Only the separators a URL actually encodes: %2F (/) and %3A (:), plus their
# double-encoded forms (%252F -> "252f").
#
# The extraction-time helper uses a far looser pattern, [0-9a-f]{2}, and is safe
# because it only fires when the character before the match was a literal "%".
# Here there is no surrounding text to check, and reusing that pattern flagged
# darkside-blog.com, careers.aljazeera.net and account.bbc.com — "da", "ca" and
# "ac" are all valid hex pairs. One of those is a real indicator. A cleanup that
# can delete an IOC is worse than the debris it removes.
MANGLED = re.compile(r"^(?:25)*(?:2f|3a)(?=[a-z0-9])", re.IGNORECASE)

ISOLATED_URLS = """
MATCH (n:URL)
WHERE ($project IS NULL OR n.project_id = $project) AND NOT (n)--()
RETURN count(n) AS c
"""

DELETE_ISOLATED_URLS = """
MATCH (n:URL)
WHERE ($project IS NULL OR n.project_id = $project) AND NOT (n)--()
WITH n LIMIT $batch
DETACH DELETE n
RETURN count(*) AS c
"""

# Candidates for the mangled-name rule, filtered in Python so the regex stays
# in one place rather than being restated as a Cypher pattern.
MANGLED_CANDIDATES = """
MATCH (n)
WHERE ($project IS NULL OR n.project_id = $project)
  AND (n:Domain OR n:URL) AND n.name IS NOT NULL
RETURN n.name AS name, elementId(n) AS eid, size([(n)--() | 1]) AS deg
"""

DELETE_BY_IDS = """
UNWIND $ids AS eid
MATCH (n) WHERE elementId(n) = eid
DETACH DELETE n
RETURN count(*) AS c
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None, help="limit to one project_id")
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--batch", type=int, default=5000, help="delete batch size")
    args = ap.parse_args()

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "changeme")
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    scope = args.project or "ALL PROJECTS"

    try:
        with driver.session() as s:
            isolated = s.run(ISOLATED_URLS, project=args.project).single()["c"]

            rows = s.run(MANGLED_CANDIDATES, project=args.project).data()
            known = {r["name"] for r in rows}

            # Three conditions, all required, because "2fa.example.com" is a
            # legitimate hostname that the prefix alone cannot be told apart
            # from debris:
            #   1. the prefix is an encoded URL separator,
            #   2. the node is isolated — anything the graph actually uses stays,
            #   3. the name with the prefix removed exists as its own node,
            #      which is the positive evidence that this one is a duplicate
            #      of a real host rather than a host in its own right.
            mangled, unclear = [], []
            for r in rows:
                name = r["name"] or ""
                m = MANGLED.match(name)
                if not m:
                    continue
                stripped = name[m.end():]
                if r["deg"] == 0 and stripped in known:
                    mangled.append({**r, "stripped": stripped})
                else:
                    unclear.append({**r, "stripped": stripped})

            print(f"scope: {scope}")
            print(f"  isolated URL nodes .............. {isolated}")
            print(f"  percent-mangled Domain/URL names  {len(mangled)}")
            for r in mangled[:10]:
                print(f"      {r['name']}  ->  {r['stripped']}")
            if len(mangled) > 10:
                print(f"      ... and {len(mangled) - 10} more")

            if unclear:
                print(f"\n  left alone, needs a human ({len(unclear)}): encoded-looking "
                      f"prefix but in use, or no matching real host")
                for r in unclear[:10]:
                    print(f"      {r['name']}  (degree {r['deg']})")
                if len(unclear) > 10:
                    print(f"      ... and {len(unclear) - 10} more")

            if not args.apply:
                print("\ndry run — nothing deleted. Re-run with --apply to remove.")
                return 0

            removed = 0
            while True:
                got = s.run(DELETE_ISOLATED_URLS, project=args.project,
                            batch=args.batch).single()["c"]
                removed += got
                if got == 0:
                    break
            print(f"\ndeleted {removed} isolated URL nodes")

            if mangled:
                n = s.run(DELETE_BY_IDS, ids=[r["eid"] for r in mangled]).single()["c"]
                print(f"deleted {n} percent-mangled nodes")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
