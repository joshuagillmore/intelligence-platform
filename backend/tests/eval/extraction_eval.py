"""Evaluation framework for entity extraction quality.

Computes precision, recall, and F1 for entities and relationships
against ground-truth annotations.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import jellyfish


# ── Entity matching ──────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return name.lower().strip()


def _entity_matches(
    predicted_name: str,
    expected_name: str,
    expected_aliases: list[str] | None = None,
    threshold: float = 0.90,
) -> bool:
    """Return True if predicted matches expected (exact, alias, or fuzzy)."""
    p = _normalize(predicted_name)
    e = _normalize(expected_name)

    # Exact match
    if p == e:
        return True

    # Alias match
    for alias in (expected_aliases or []):
        if p == _normalize(alias):
            return True

    # Jaro-Winkler fuzzy match
    if jellyfish.jaro_winkler_similarity(p, e) >= threshold:
        return True

    # Substring match (handles "Putin" matching "Vladimir Putin")
    shorter = min(p, e, key=len)
    longer = max(p, e, key=len)
    if len(shorter) >= 4 and shorter in longer:
        return True

    return False


# ── Metric computation ───────────────────────────────────────────────────────

def compute_entity_metrics(
    predicted: list[dict],
    expected: list[dict],
    threshold: float = 0.90,
) -> dict:
    """Compute precision, recall, F1 for entity extraction.

    Returns overall metrics and per-entity-type breakdown.
    """
    matched_expected = set()
    matched_predicted = set()

    # Match predicted to expected
    for i, p in enumerate(predicted):
        for j, e in enumerate(expected):
            if j in matched_expected:
                continue
            if _entity_matches(p["name"], e["name"], e.get("aliases"), threshold):
                matched_predicted.add(i)
                matched_expected.add(j)
                break

    tp = len(matched_expected)
    fp = len(predicted) - len(matched_predicted)
    fn = len(expected) - len(matched_expected)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Per-entity-type metrics
    type_metrics = _compute_per_type_metrics(predicted, expected, matched_predicted, matched_expected, threshold)

    # False positives and negatives for review
    false_positives = [predicted[i] for i in range(len(predicted)) if i not in matched_predicted]
    false_negatives = [expected[j] for j in range(len(expected)) if j not in matched_expected]

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "per_type": type_metrics,
        "fp_details": false_positives,
        "fn_details": false_negatives,
    }


def _compute_per_type_metrics(
    predicted: list[dict], expected: list[dict],
    matched_predicted: set[int], matched_expected: set[int],
    threshold: float,
) -> dict:
    """Compute metrics broken down by entity type."""
    types = set()
    for e in expected:
        types.add(e.get("entity_type", "Unknown"))
    for p in predicted:
        types.add(p.get("entity_type", "Unknown"))

    results = {}
    for t in sorted(types):
        pred_of_type = [p for p in predicted if p.get("entity_type", "Unknown") == t]
        exp_of_type = [e for e in expected if e.get("entity_type", "Unknown") == t]

        tp = 0
        for p in pred_of_type:
            for e in exp_of_type:
                if _entity_matches(p["name"], e["name"], e.get("aliases"), threshold):
                    tp += 1
                    break

        fp = len(pred_of_type) - tp
        fn = len(exp_of_type) - tp

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        results[t] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "predicted": len(pred_of_type),
            "expected": len(exp_of_type),
            "true_positives": tp,
        }

    return results


def compute_relationship_metrics(
    predicted: list[dict],
    expected: list[dict],
    threshold: float = 0.90,
) -> dict:
    """Compute precision, recall, F1 for relationship extraction."""
    matched_expected = set()
    matched_predicted = set()

    for i, p in enumerate(predicted):
        p_src = p.get("source_name", p.get("source", ""))
        p_tgt = p.get("target_name", p.get("target", ""))
        p_type = p.get("rel_type", p.get("relationship_type", ""))

        for j, e in enumerate(expected):
            if j in matched_expected:
                continue
            e_src = e.get("source", e.get("source_name", ""))
            e_tgt = e.get("target", e.get("target_name", ""))
            e_type = e.get("rel_type", e.get("relationship_type", ""))

            if (
                _entity_matches(p_src, e_src, threshold=threshold)
                and _entity_matches(p_tgt, e_tgt, threshold=threshold)
                and p_type == e_type
            ):
                matched_predicted.add(i)
                matched_expected.add(j)
                break

    tp = len(matched_expected)
    fp = len(predicted) - len(matched_predicted)
    fn = len(expected) - len(matched_expected)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def compute_type_accuracy(
    predicted: list[dict],
    expected: list[dict],
    threshold: float = 0.90,
) -> dict:
    """Compute what fraction of matched entities have the correct type."""
    correct = 0
    total = 0
    confusion: dict[tuple[str, str], int] = defaultdict(int)

    for p in predicted:
        for e in expected:
            if _entity_matches(p["name"], e["name"], e.get("aliases"), threshold):
                total += 1
                p_type = p.get("entity_type", "Unknown")
                e_type = e.get("entity_type", "Unknown")
                if p_type == e_type:
                    correct += 1
                else:
                    confusion[(e_type, p_type)] += 1
                break

    accuracy = correct / total if total > 0 else 0.0
    return {
        "accuracy": round(accuracy, 4),
        "correct": correct,
        "total": total,
        "confusion": {f"{expected_t} -> {predicted_t}": count for (expected_t, predicted_t), count in confusion.items()},
    }


# ── Report generation ────────────────────────────────────────────────────────

FIXTURE_MARKER = "--- BEGIN FIXTURE ---"


def strip_fixture_notice(text: str) -> str:
    """Drop the leading "this is synthetic" notice, if present.

    The fixtures imitate real intelligence products closely enough to carry
    fake control markings, so each one says in its own first lines that it is
    fabricated — that has to be legible to anyone who opens the file, not
    buried in a sidecar. The extractor must not see it, though: it is prose
    naming no real entity, and feeding it in would cost precision against a
    gold set that rightly does not mention it.

    A file without the marker is returned unchanged, so an unmarked or
    externally-supplied fixture still loads.
    """
    _, sep, body = text.partition(FIXTURE_MARKER)
    return body.lstrip("\n") if sep else text


def load_fixture(name: str) -> tuple[str, dict]:
    """Load a test document and its expected output."""
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "extraction"
    text_path = fixtures_dir / f"{name}.txt"
    expected_path = fixtures_dir / f"{name}_expected.json"

    text = strip_fixture_notice(text_path.read_text(encoding="utf-8"))
    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    return text, expected


def generate_report(
    results: list[dict],
    document_names: list[str],
) -> dict:
    """Generate an aggregate evaluation report across multiple documents."""
    total_entity_tp = 0
    total_entity_fp = 0
    total_entity_fn = 0
    total_rel_tp = 0
    total_rel_fp = 0
    total_rel_fn = 0

    per_doc = []
    for name, result in zip(document_names, results):
        em = result["entity_metrics"]
        rm = result["relationship_metrics"]
        total_entity_tp += em["true_positives"]
        total_entity_fp += em["false_positives"]
        total_entity_fn += em["false_negatives"]
        total_rel_tp += rm["true_positives"]
        total_rel_fp += rm["false_positives"]
        total_rel_fn += rm["false_negatives"]

        per_doc.append({
            "document": name,
            "entity_f1": em["f1"],
            "entity_precision": em["precision"],
            "entity_recall": em["recall"],
            "relationship_f1": rm["f1"],
            "type_accuracy": result.get("type_accuracy", {}).get("accuracy", 0),
        })

    # Aggregate metrics
    ep = total_entity_tp / (total_entity_tp + total_entity_fp) if (total_entity_tp + total_entity_fp) > 0 else 0
    er = total_entity_tp / (total_entity_tp + total_entity_fn) if (total_entity_tp + total_entity_fn) > 0 else 0
    ef1 = 2 * ep * er / (ep + er) if (ep + er) > 0 else 0

    rp = total_rel_tp / (total_rel_tp + total_rel_fp) if (total_rel_tp + total_rel_fp) > 0 else 0
    rr = total_rel_tp / (total_rel_tp + total_rel_fn) if (total_rel_tp + total_rel_fn) > 0 else 0
    rf1 = 2 * rp * rr / (rp + rr) if (rp + rr) > 0 else 0

    return {
        "aggregate": {
            "entity_precision": round(ep, 4),
            "entity_recall": round(er, 4),
            "entity_f1": round(ef1, 4),
            "relationship_precision": round(rp, 4),
            "relationship_recall": round(rr, 4),
            "relationship_f1": round(rf1, 4),
        },
        "per_document": per_doc,
    }
