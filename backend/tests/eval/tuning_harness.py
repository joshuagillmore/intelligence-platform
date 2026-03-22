#!/usr/bin/env python3
"""Tuning harness for QA agent to evaluate and optimize entity extraction.

Usage:
    python -m tests.eval.tuning_harness [OPTIONS]

Examples:
    # Run with default settings
    python -m tests.eval.tuning_harness

    # Run with specific spaCy model
    python -m tests.eval.tuning_harness --spacy-model en_core_web_lg

    # Compare two result files
    python -m tests.eval.tuning_harness --compare results_a.json results_b.json

    # Save results to file
    python -m tests.eval.tuning_harness --output results.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(_project_root))


def run_evaluation(
    spacy_model: str = "",
    confidence_threshold: float = 0.0,
    jw_threshold: float = 0.92,
    extraction_mode: str = "nlp",
) -> dict:
    """Run extraction evaluation against all test documents.

    Returns a results dict with per-document and aggregate metrics.
    """
    # Override settings if provided
    if spacy_model:
        os.environ["SPACY_MODEL"] = spacy_model
    if confidence_threshold > 0:
        os.environ["EXTRACTION_CONFIDENCE_MIN"] = str(confidence_threshold)
    os.environ["ENTITY_RESOLUTION_THRESHOLD"] = str(jw_threshold)

    # Force reimport to pick up env changes
    import importlib
    import intel_platform.config
    importlib.reload(intel_platform.config)

    # Reset spaCy model cache if model changed
    if spacy_model:
        import intel_platform.services.extraction as ext_mod
        ext_mod._nlp = None
        ext_mod._domain_pattern_cache = None

    from intel_platform.services.extraction import extract_entities_nlp
    from tests.eval.extraction_eval import (
        compute_entity_metrics,
        compute_relationship_metrics,
        compute_type_accuracy,
        generate_report,
        load_fixture,
    )

    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "extraction"
    fixture_names = sorted(
        p.stem.replace("_expected", "")
        for p in fixtures_dir.glob("*_expected.json")
        if (fixtures_dir / f"{p.stem.replace('_expected', '')}.txt").exists()
    )

    results = []
    doc_names = []

    for name in fixture_names:
        text, expected = load_fixture(name)

        entities, relationships = extract_entities_nlp(text, doc_id=f"eval-{name}")

        # Apply confidence filter if threshold set
        if confidence_threshold > 0:
            entities = [e for e in entities if e.get("confidence", 0) >= confidence_threshold]

        entity_metrics = compute_entity_metrics(entities, expected["entities"])
        rel_metrics = compute_relationship_metrics(relationships, expected.get("relationships", []))
        type_acc = compute_type_accuracy(entities, expected["entities"])

        results.append({
            "entity_metrics": entity_metrics,
            "relationship_metrics": rel_metrics,
            "type_accuracy": type_acc,
            "entities_predicted": len(entities),
            "entities_expected": len(expected["entities"]),
            "relationships_predicted": len(relationships),
            "relationships_expected": len(expected.get("relationships", [])),
        })
        doc_names.append(name)

    report = generate_report(results, doc_names)

    # Add parameters used
    report["parameters"] = {
        "spacy_model": spacy_model or os.environ.get("SPACY_MODEL", "default"),
        "confidence_threshold": confidence_threshold,
        "jw_threshold": jw_threshold,
        "extraction_mode": extraction_mode,
    }

    # Add per-document detail
    for i, name in enumerate(doc_names):
        report["per_document"][i]["entity_metrics"] = results[i]["entity_metrics"]
        report["per_document"][i]["relationship_metrics"] = results[i]["relationship_metrics"]
        report["per_document"][i]["type_accuracy"] = results[i]["type_accuracy"]

    return report


def compare_results(file_a: str, file_b: str) -> None:
    """Compare two evaluation result files side by side."""
    with open(file_a) as f:
        a = json.load(f)
    with open(file_b) as f:
        b = json.load(f)

    print("=" * 70)
    print(f"{'Metric':<30} {'Run A':>15} {'Run B':>15} {'Delta':>10}")
    print("=" * 70)

    agg_a = a["aggregate"]
    agg_b = b["aggregate"]

    for key in ["entity_precision", "entity_recall", "entity_f1",
                 "relationship_precision", "relationship_recall", "relationship_f1"]:
        va = agg_a.get(key, 0)
        vb = agg_b.get(key, 0)
        delta = vb - va
        marker = "+" if delta > 0 else ""
        print(f"{key:<30} {va:>14.4f} {vb:>14.4f} {marker}{delta:>9.4f}")

    print("\n--- Parameters ---")
    pa = a.get("parameters", {})
    pb = b.get("parameters", {})
    for key in set(list(pa.keys()) + list(pb.keys())):
        print(f"  {key}: {pa.get(key, '?')} -> {pb.get(key, '?')}")


def main():
    parser = argparse.ArgumentParser(description="Entity extraction tuning harness")
    parser.add_argument("--spacy-model", default="", help="spaCy model to use")
    parser.add_argument("--confidence-threshold", type=float, default=0.0,
                        help="Minimum confidence to include an entity")
    parser.add_argument("--jw-threshold", type=float, default=0.92,
                        help="Jaro-Winkler threshold for entity resolution")
    parser.add_argument("--extraction-mode", default="nlp", choices=["nlp", "llm", "hybrid"],
                        help="Extraction mode")
    parser.add_argument("--output", default="", help="Save results to JSON file")
    parser.add_argument("--compare", nargs=2, metavar=("FILE_A", "FILE_B"),
                        help="Compare two result files")
    parser.add_argument("--verbose", action="store_true", help="Print detailed per-document results")

    args = parser.parse_args()

    if args.compare:
        compare_results(args.compare[0], args.compare[1])
        return

    print(f"Running evaluation (model={args.spacy_model or 'default'}, "
          f"confidence={args.confidence_threshold}, jw={args.jw_threshold}, "
          f"mode={args.extraction_mode})...")

    report = run_evaluation(
        spacy_model=args.spacy_model,
        confidence_threshold=args.confidence_threshold,
        jw_threshold=args.jw_threshold,
        extraction_mode=args.extraction_mode,
    )

    # Print summary
    agg = report["aggregate"]
    print("\n" + "=" * 50)
    print("AGGREGATE RESULTS")
    print("=" * 50)
    print(f"Entity      P={agg['entity_precision']:.4f}  R={agg['entity_recall']:.4f}  F1={agg['entity_f1']:.4f}")
    print(f"Relationship P={agg['relationship_precision']:.4f}  R={agg['relationship_recall']:.4f}  F1={agg['relationship_f1']:.4f}")

    if args.verbose:
        print("\n--- Per-Document ---")
        for doc in report["per_document"]:
            print(f"\n  {doc['document']}:")
            print(f"    Entity F1={doc['entity_f1']:.4f}  Rel F1={doc['relationship_f1']:.4f}  Type Acc={doc['type_accuracy']:.4f}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
