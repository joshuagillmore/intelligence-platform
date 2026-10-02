"""How the corpus eval scores relationships. Default suite: no model, no database.

The gold labels typed relations only. Generic associations and the links that
date an event are legitimate output (the timeline is built from the second),
but scoring them against that gold counted every one as a false positive, so
relationship precision said nothing about the typed relations. The runner
reports two figures: ``typed`` and ``all``.
"""

from __future__ import annotations

from tests.eval import run_corpus_eval as rce

# openrep OPENREP-SUPINTREP-0006#0: "Since Russia's full-scale invasion of
# Ukraine in 2022, U.S., European, and NATO officials have highlighted the
# continued threat Russia poses to European security." Gold: Russia TARGETS
# Ukraine (and five more edges elsewhere in the chunk).
DOC = "OPENREP-SUPINTREP-0006_0"


def _prediction():
    entities = [
        {"name": "Russia", "entity_type": "Location"},
        {"name": "Ukraine", "entity_type": "Location"},
        {"name": "NATO", "entity_type": "Organization"},
        {"name": "Russia's full-scale invasion of Ukraine", "entity_type": "Event"},
        {"name": "2022", "entity_type": "Date"},
    ]
    rels = [
        {"source_name": "Russia", "target_name": "Ukraine", "rel_type": "TARGETS"},
        {"source_name": "Russia's full-scale invasion of Ukraine", "target_name": "2022", "rel_type": "OCCURRED_ON"},
        {"source_name": "NATO", "target_name": "Russia", "rel_type": "ASSOCIATED_WITH"},
        # A typed edge to a date is still a date link, not a typed relation.
        {"source_name": "NATO", "target_name": "2022", "rel_type": "LOCATED_AT"},
    ]
    return entities, rels


def test_relationships_are_scored_typed_and_all():
    _, gold = rce.load("openrep", DOC)
    entities, rels = _prediction()
    score = rce.score_document(entities, rels, gold)

    every = score["relationships"]
    assert (every["tp"], every["pred"], every["exp"]) == (1, 4, 6)

    typed = score["relationships_typed"]
    # Only Russia TARGETS Ukraine is a typed relation; the gold is unchanged.
    assert (typed["tp"], typed["pred"], typed["exp"]) == (1, 1, 6)
    assert score["relationship_classes"] == {"typed": 1, "generic": 1, "date_link": 2}
    # The entity figures are untouched by the relationship split: Russia,
    # Ukraine, NATO and 2022 match gold with their types; the event is extra.
    assert score["entities"] == {"tp": 4, "pred": 5, "exp": len(gold["entities"]), "typed_tp": 4, "category_tp": 4}


def test_the_aggregate_and_report_carry_both_figures():
    _, gold = rce.load("openrep", DOC)
    entities, rels = _prediction()
    doc = {"set": "openrep", "name": DOC, "score": rce.score_document(entities, rels, gold)}
    agg = rce.aggregate([doc])
    assert agg["relationship"]["precision"] == 0.25
    assert agg["relationship_typed"]["precision"] == 1.0
    assert agg["relationship_typed"]["recall"] == agg["relationship"]["recall"] == round(1 / 6, 4)
    assert agg["relationship_classes_predicted"] == {"typed": 1, "generic": 1, "date_link": 2}

    report = {"mode": "nlp", "generated_at": "", "git_commit": "", "spacy_model": "", "degraded_documents": [],
              "overall": agg, "by_set": {"openrep": agg}, "documents": [doc]}
    md = rce.markdown(report)
    assert "Rel typed P / R / F1" in md and "Rel all P / R / F1" in md
    assert "Relationships (typed)" in md and "Relationships (all)" in md
