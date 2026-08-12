#!/usr/bin/env python3
"""Holdout evaluation runner — scores extraction against the extraction_holdout/
fixtures instead of the main extraction/ set.

These four documents were written and gold-labeled independently of the
extractor (never run through it during authoring) specifically so precision/
recall tuning on the main fixtures can be checked against unseen data and
doesn't just overfit the 8 curated training fixtures.

Reuses all scoring logic from tests.eval.extraction_eval — no metric logic is
duplicated here, only the fixture directory and report formatting differ from
run_full_eval.py (which must not be edited; this is a separate, additive
runner).

Usage:
    cd backend && NEO4J_URI=bolt://127.0.0.1:7687 PYTHONPATH=. uv run --no-sync python tests/eval/run_holdout_eval.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import os

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")

from intel_platform.services.extraction import extract_entities_nlp
from tests.eval.extraction_eval import (
    compute_entity_metrics,
    compute_relationship_metrics,
    compute_type_accuracy,
    strip_fixture_notice,
)

HOLDOUT_DIR = Path(__file__).parent.parent / "fixtures" / "extraction_holdout"


def load_holdout_fixture(name: str) -> tuple[str, dict]:
    """Load a holdout document and its expected output (mirrors load_fixture,
    but reads from extraction_holdout/ instead of extraction/)."""
    text_path = HOLDOUT_DIR / f"{name}.txt"
    expected_path = HOLDOUT_DIR / f"{name}_expected.json"

    text = strip_fixture_notice(text_path.read_text(encoding="utf-8"))
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    return text, expected


def discover_holdout_fixtures() -> list[str]:
    return sorted(
        p.stem.replace("_expected", "")
        for p in HOLDOUT_DIR.glob("*_expected.json")
        if (HOLDOUT_DIR / f"{p.stem.replace('_expected', '')}.txt").exists()
    )


def run_single(name: str) -> dict:
    text, expected = load_holdout_fixture(name)

    t0 = time.time()
    entities, rels = extract_entities_nlp(text, doc_id=f"holdout-{name}")
    extraction_time = time.time() - t0

    em = compute_entity_metrics(entities, expected["entities"])
    rm = compute_relationship_metrics(rels, expected.get("relationships", []))
    ta = compute_type_accuracy(entities, expected["entities"])

    return {
        "name": name,
        "extraction_time_s": round(extraction_time, 3),
        "text_length": len(text),
        "entities_predicted": len(entities),
        "entities_expected": len(expected["entities"]),
        "relationships_predicted": len(rels),
        "relationships_expected": len(expected.get("relationships", [])),
        "entity_metrics": em,
        "relationship_metrics": rm,
        "type_accuracy": ta,
        "predicted_entities": entities,
        "predicted_relationships": rels,
    }


def print_report(results: list[dict]) -> None:
    # ── Header ──
    print("\n" + "=" * 80)
    print("ENTITY EXTRACTION QUALITY EVALUATION REPORT - HOLDOUT CORPUS")
    print("=" * 80)
    print(f"Documents evaluated: {len(results)}")
    print("Extraction mode: NLP (spaCy)")
    print("Fixture set: tests/fixtures/extraction_holdout/ (unseen, independently labeled)")
    print()

    # ── Per-document summary table ──
    print(f"{'Document':<35} {'Ent P':>6} {'Ent R':>6} {'Ent F1':>6} {'Rel F1':>6} {'Type%':>6} {'Time':>6}")
    print("-" * 80)

    total_tp = total_fp = total_fn = 0
    total_rel_tp = total_rel_fp = total_rel_fn = 0
    type_correct = type_total = 0
    all_type_breakdown = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "pred": 0, "exp": 0})
    all_confusion = defaultdict(int)

    for r in results:
        em = r["entity_metrics"]
        rm = r["relationship_metrics"]
        ta = r["type_accuracy"]

        print(f"{r['name']:<35} {em['precision']:>6.3f} {em['recall']:>6.3f} {em['f1']:>6.3f} "
              f"{rm['f1']:>6.3f} {ta['accuracy']:>5.1%} {r['extraction_time_s']:>5.2f}s")

        total_tp += em["true_positives"]
        total_fp += em["false_positives"]
        total_fn += em["false_negatives"]
        total_rel_tp += rm["true_positives"]
        total_rel_fp += rm["false_positives"]
        total_rel_fn += rm["false_negatives"]
        type_correct += ta["correct"]
        type_total += ta["total"]

        for t, m in em["per_type"].items():
            all_type_breakdown[t]["tp"] += m["true_positives"]
            all_type_breakdown[t]["fp"] += m["predicted"] - m["true_positives"]
            all_type_breakdown[t]["fn"] += m["expected"] - m["true_positives"]
            all_type_breakdown[t]["pred"] += m["predicted"]
            all_type_breakdown[t]["exp"] += m["expected"]

        for k, v in ta.get("confusion", {}).items():
            all_confusion[k] += v

    # ── Aggregate metrics ──
    print("-" * 80)
    ep = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0
    er = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0
    ef1 = 2 * ep * er / (ep + er) if (ep + er) else 0
    rp = total_rel_tp / (total_rel_tp + total_rel_fp) if (total_rel_tp + total_rel_fp) else 0
    rr = total_rel_tp / (total_rel_tp + total_rel_fn) if (total_rel_tp + total_rel_fn) else 0
    rf1 = 2 * rp * rr / (rp + rr) if (rp + rr) else 0
    ta_pct = type_correct / type_total if type_total else 0

    print(f"{'AGGREGATE':<35} {ep:>6.3f} {er:>6.3f} {ef1:>6.3f} {rf1:>6.3f} {ta_pct:>5.1%}")
    print()

    # ── Per-entity-type breakdown ──
    print("PER-ENTITY-TYPE BREAKDOWN (Aggregate)")
    print(f"{'Type':<25} {'Prec':>6} {'Recall':>6} {'F1':>6} {'Pred':>5} {'Exp':>5} {'TP':>4}")
    print("-" * 60)

    for t in sorted(all_type_breakdown.keys()):
        m = all_type_breakdown[t]
        p = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) else 0
        r = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) else 0
        f = 2 * p * r / (p + r) if (p + r) else 0
        if m["pred"] > 0 or m["exp"] > 0:
            print(f"  {t:<23} {p:>6.2f} {r:>6.2f} {f:>6.2f} {m['pred']:>5} {m['exp']:>5} {m['tp']:>4}")

    print()

    # ── Type confusion matrix ──
    if all_confusion:
        print("TYPE CONFUSION (expected -> predicted)")
        print("-" * 50)
        for k in sorted(all_confusion.keys(), key=lambda x: all_confusion[x], reverse=True):
            print(f"  {k}: {all_confusion[k]}")
        print()

    # ── Missed entities across all documents ──
    print("MISSED ENTITIES (False Negatives)")
    print("-" * 50)
    for r in results:
        fns = r["entity_metrics"]["fn_details"]
        if fns:
            missed = [(e["name"], e.get("entity_type", "?")) for e in fns]
            print(f"  {r['name']}: {missed}")
    print()

    # ── Relationship analysis ──
    print("RELATIONSHIP EXTRACTION ANALYSIS")
    print("-" * 50)
    rel_type_counts = defaultdict(int)
    for r in results:
        for rel in r["predicted_relationships"]:
            rel_type_counts[rel["rel_type"]] += 1

    print("  Predicted relationship type distribution:")
    for rt in sorted(rel_type_counts.keys(), key=lambda x: rel_type_counts[x], reverse=True):
        print(f"    {rt:<25} {rel_type_counts[rt]:>4}")
    print(f"  Total predicted: {sum(rel_type_counts.values())}")
    print(f"  Total expected:  {sum(len(r['relationship_metrics'].get('fn_details', [])) for r in results) + total_rel_tp}")
    print()


def main():
    fixtures = discover_holdout_fixtures()
    if not fixtures:
        print("No holdout fixtures found!")
        return 1

    print(f"Discovered {len(fixtures)} holdout test documents: {fixtures}")

    results = []
    for name in fixtures:
        print(f"  Evaluating {name}...", end="", flush=True)
        r = run_single(name)
        print(f" done ({r['extraction_time_s']:.2f}s)")
        results.append(r)

    print_report(results)

    # Save detailed results (separate file from the main eval's output)
    output_path = Path(__file__).parent / "holdout_eval_results.json"
    serializable = []
    for r in results:
        s = dict(r)
        s.pop("predicted_entities", None)
        s.pop("predicted_relationships", None)
        s["entity_metrics"].pop("fp_details", None)
        s["entity_metrics"].pop("fn_details", None)
        serializable.append(s)

    with open(output_path, "w") as f:
        json.dump({"results": serializable, "fixtures": fixtures}, f, indent=2, default=str)
    print(f"Detailed results saved to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
