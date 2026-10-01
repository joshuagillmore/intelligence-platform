"""Write the API's OpenAPI schema to backend/openapi.json (contract 9).

The frontend generates its API types from this file (`npm run gen:api`), so it
is committed and must change only when the API does: keys are sorted and the
output is byte-for-byte reproducible. Regenerate after any route or model
change, from backend/:

    uv run python scripts/export_openapi.py            # write openapi.json
    uv run python scripts/export_openapi.py --check    # exit 1 if it is stale

Nothing is connected to: building the schema only imports the app. A
developer's .env is not read, so the file never depends on whose machine made it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def schema_text(app) -> str:
    """``app``'s schema as the exact text openapi.json holds."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render() -> str:
    # Settings requires a Neo4j URI to exist; nothing connects to it here.
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    from intel_platform import config

    config.Settings.model_config["env_file"] = None
    config.get_settings.cache_clear()

    from intel_platform.api.app import app

    return schema_text(app)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if openapi.json is not current")
    parser.add_argument("--output", type=Path, default=OUTPUT, help=f"default: {OUTPUT}")
    args = parser.parse_args(argv)

    text = render()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != text:
            print(f"{args.output} is stale: run `uv run python scripts/export_openapi.py`", file=sys.stderr)
            return 1
        print(f"{args.output} is current")
        return 0
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.output} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
