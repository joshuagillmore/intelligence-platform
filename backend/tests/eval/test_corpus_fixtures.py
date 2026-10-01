"""The eval corpus is safe to publish and its gold files are internally sound.

Runs in the default suite: no model, no network, no database.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from intel_platform.models.type_hierarchy import get_parent_category

BACKEND = Path(__file__).resolve().parents[2]
CORPUS = BACKEND / "tests" / "fixtures" / "extraction_corpus"
CYBER = BACKEND / "tests" / "fixtures" / "extraction_corpus_cyber"

# Independent of the builder's own check, so a change to one cannot quietly
# disable both.
_MARKING = re.compile(
    r"\b(?:COSMIC|NATO (?:SECRET|CONFIDENTIAL|RESTRICTED|UNCLASSIFIED)|NOFORN|ORCON|FVEY|REL-[A-Z]+)\b"
    r"|\((?:CTS|NS|NC|NR|NU)\)|^\s*(?:CTS|NS|NC|NR|NU)\s*(?://|$)|//\s*REL",
    re.MULTILINE,
)


def _builder():
    spec = importlib.util.spec_from_file_location("build_eval_corpus", BACKEND / "scripts" / "build_eval_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixtures(d: Path) -> list[tuple[str, str, dict]]:
    out = []
    for exp in sorted(d.glob("*_expected.json")):
        stem = exp.name[: -len("_expected.json")]
        out.append((stem, (d / f"{stem}.txt").read_text(encoding="utf-8"),
                    json.loads(exp.read_text(encoding="utf-8"))))
    return out


def test_corpus_has_about_forty_documents():
    assert 35 <= len(_fixtures(CORPUS)) <= 45


@pytest.mark.parametrize("stem,text,gold", _fixtures(CORPUS), ids=lambda v: v if isinstance(v, str) else "")
def test_corpus_text_carries_no_marking_and_keeps_the_banner(stem, text, gold):
    assert not _MARKING.search(text), f"{stem}: {_MARKING.search(text).group()!r}"
    assert "EXERCISE — FICTIONAL" in text
    assert "Entities identified in this reporting:" in text


@pytest.mark.parametrize("stem,text,gold", _fixtures(CORPUS) + _fixtures(CYBER),
                         ids=lambda v: v if isinstance(v, str) else "")
def test_gold_is_consistent_with_its_text(stem, text, gold):
    lowered = text.lower()
    names = set()
    for e in gold["entities"]:
        assert any(n.lower() in lowered for n in [e["name"], *e.get("aliases", [])]), (stem, e["name"])
        assert e["entity_type"] == "Date" or get_parent_category(e["entity_type"]) != "Other", (stem, e)
        names.add(e["name"])
    for r in gold.get("relationships", []):
        assert r["source"] in names and r["target"] in names, (stem, r)
    assert "REVIEW" not in {e["entity_type"] for e in gold["entities"]}
    assert not gold.get("review", "").startswith("seed"), f"{stem} was never reviewed"


def test_strip_markings_removes_banners_and_portion_markings():
    b = _builder()
    raw = (
        "EXERCISE — FICTIONAL\n\nNS//REL-NATO\n\n1. (NS) Source reported X.\n\n"
        "2. (CTS) Entities identified in this reporting: A.\n\nCTS//REL-FVEY//REL-NATO\n"
    )
    out = b.strip_markings(raw)
    assert out == "EXERCISE — FICTIONAL\n\n1. Source reported X.\n\n2. Entities identified in this reporting: A.\n"


def test_strip_markings_refuses_a_marking_it_does_not_know():
    b = _builder()
    with pytest.raises(b.MarkingResidue):
        b.strip_markings("1. Source reported X. NATO SECRET handling applies.\n")


def test_seed_entity_reads_hull_numbers_and_units():
    b = _builder()
    assert b.seed_entity("Ostravik (A-411)") == {
        "name": "Ostravik", "entity_type": "Ship", "aliases": ["Ostravik (A-411)", "A-411"],
    }
    assert b.seed_entity("3rd Naval Auxiliary Group")["entity_type"] == "Organization"
    assert b.split_entity_line("Brenna (P-118), Sarn (P-121), 3rd Naval Auxiliary Group.") == [
        "Brenna (P-118)", "Sarn (P-121)", "3rd Naval Auxiliary Group",
    ]


def test_scorer_pairs_exact_names_before_fuzzy_ones():
    import sys

    sys.path.insert(0, str(BACKEND))
    from tests.eval.run_corpus_eval import match_entities

    predicted = [{"name": "CVE-2023-27997"}, {"name": "2023"}, {"name": "Guam"}, {"name": "Naval Base Guam"}]
    expected = [{"name": "2023"}, {"name": "Guam"}, {"name": "CVE-2023-27997"}, {"name": "Naval Base Guam"}]
    assert sorted(match_entities(predicted, expected)) == [(0, 2), (1, 0), (2, 1), (3, 3)]
