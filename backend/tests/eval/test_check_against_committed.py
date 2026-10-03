"""The extraction-eval gate's comparison. Default suite: no model, no database.

``check_against_committed.py`` fails CI when a replayed eval scores below the
committed results. These pin what counts as a regression: a lowered F1 fails,
a raised one passes, a dip inside the 0.005 tolerance passes, and a figure or
reply that goes missing fails rather than passing unnoticed.
"""

from __future__ import annotations

import copy

import pytest

from tests.eval import check_against_committed as gate


def _figure(f1: float) -> dict:
    return {"precision": f1, "recall": f1, "f1": f1, "tp": 1, "predicted": 1, "expected": 1}


def _block(entity=0.80, entity_typed=0.70, relationship_typed=0.50, relationship=0.10) -> dict:
    return {
        "documents": 40,
        "entity": _figure(entity),
        "entity_typed": _figure(entity_typed),
        "relationship_typed": _figure(relationship_typed),
        "relationship": _figure(relationship),
    }


def _report(**overrides) -> dict:
    report = {
        "mode": "hybrid",
        "spacy_model": "en_core_web_sm",
        "llm": {"provider": "CohereProvider", "model": "command-a-plus-05-2026",
                "replies": {"live": 0, "replayed": 83, "missed": 0}},
        "degraded_documents": [],
        "overall": _block(),
        "by_set": {"openrep": _block(), "kestrel": _block(), "cyber": _block()},
    }
    report.update(overrides)
    return report


def test_identical_results_pass():
    assert gate.compare(_report(), _report()) == []


@pytest.mark.parametrize("metric", gate.METRICS)
def test_a_lowered_overall_f1_fails(metric):
    fresh = _report()
    fresh["overall"][metric]["f1"] -= 0.02
    regressions = gate.compare(_report(), fresh)
    assert [(r.scope, r.metric) for r in regressions] == [("overall", metric)]
    assert regressions[0].delta == -0.02


def test_a_lowered_set_f1_fails_even_when_overall_holds():
    fresh = _report()
    fresh["by_set"]["cyber"]["relationship_typed"]["f1"] = 0.40
    regressions = gate.compare(_report(), fresh)
    assert [(r.scope, r.metric) for r in regressions] == [("cyber", "relationship_typed")]


def test_a_raised_f1_passes():
    fresh = _report(overall=_block(entity=0.95, entity_typed=0.90, relationship_typed=0.70, relationship=0.30))
    fresh["by_set"]["openrep"] = _block(entity=0.99)
    assert gate.compare(_report(), fresh) == []


def test_a_dip_within_the_tolerance_passes():
    fresh = _report()
    fresh["overall"]["entity"]["f1"] = 0.80 - 0.004
    # Exactly on the line passes too: the comparison is rounded, not float-noisy.
    fresh["by_set"]["kestrel"]["entity_typed"]["f1"] = 0.70 - gate.TOLERANCE
    assert gate.compare(_report(), fresh) == []


def test_a_dip_just_past_the_tolerance_fails():
    fresh = _report()
    fresh["overall"]["entity"]["f1"] = 0.80 - 0.006
    assert [r.metric for r in gate.compare(_report(), fresh)] == ["entity"]


def test_a_figure_missing_from_the_fresh_report_fails():
    fresh = _report()
    del fresh["by_set"]["cyber"]
    del fresh["overall"]["relationship"]
    missing = {(r.scope, r.metric) for r in gate.compare(_report(), fresh)}
    assert ("overall", "relationship") in missing
    assert {m for s, m in missing if s == "cyber"} == set(gate.METRICS)
    assert all(r.fresh is None and r.delta is None for r in gate.compare(_report(), fresh))


def test_a_metric_the_baseline_lacks_is_not_required():
    committed = _report()
    del committed["overall"]["relationship"]
    fresh = _report()
    fresh["overall"]["relationship"]["f1"] = 0.0
    assert gate.compare(committed, fresh) == []


def test_missed_replies_fail_the_run():
    fresh = _report(llm={"provider": "CohereProvider", "model": "m",
                         "replies": {"live": 0, "replayed": 80, "missed": 3}})
    problems = gate.run_problems(_report(), fresh)
    assert len(problems) == 1 and "3 model request(s) had no recorded reply" in problems[0]


def test_newly_degraded_documents_fail_the_run():
    committed = _report(degraded_documents=["openrep/a: old"])
    fresh = _report(degraded_documents=["openrep/a: old", "kestrel/b: LookupError"])
    problems = gate.run_problems(committed, fresh)
    assert len(problems) == 1 and "kestrel/b: LookupError" in problems[0]
    assert gate.run_problems(committed, copy.deepcopy(committed)) == []


def test_an_nlp_report_has_no_replay_problems():
    nlp = _report()
    del nlp["llm"]
    assert gate.run_problems(nlp, nlp) == []


def test_the_regression_table_names_set_metric_and_change():
    fresh = _report()
    fresh["by_set"]["openrep"]["entity_typed"]["f1"] = 0.65
    table = gate.format_regressions("nlp", gate.compare(_report(), fresh))
    assert "| openrep | entity_typed | 0.7000 | 0.6500 | -0.0500 |" in table


def test_the_replay_environment_is_pinned_to_the_committed_run():
    shell = {"PATH": "/bin", "DEFAULT_LLM_PROVIDER": "anthropic", "EXTRACTION_LLM_PROVIDER": "ollama",
             "COHERE_API_KEY": "a-real-key", "OPENAI_API_KEY": "another"}
    env = gate.replay_env(_report(), base=shell)
    assert env["PATH"] == "/bin"
    assert env["DEFAULT_LLM_PROVIDER"] == "cohere"
    assert env["DEFAULT_LLM_MODEL"] == "command-a-plus-05-2026"
    # Blank, not absent: an unset variable would fall through to the .env.
    assert env["EXTRACTION_LLM_PROVIDER"] == "" and env["OPENAI_API_KEY"] == ""
    # A placeholder, never the developer's key: replay mode calls nothing.
    assert env["COHERE_API_KEY"] == gate.PLACEHOLDER_KEY
    assert env["SPACY_MODEL"] == "en_core_web_sm"


def test_the_nlp_replay_environment_selects_no_provider():
    nlp = _report()
    del nlp["llm"]
    env = gate.replay_env(nlp, base={"COHERE_API_KEY": "a-real-key"})
    assert env["COHERE_API_KEY"] == "" and env["DEFAULT_LLM_PROVIDER"] == ""


def test_an_unknown_recorded_provider_is_refused():
    with pytest.raises(SystemExit):
        gate.replay_env(_report(llm={"provider": "MysteryProvider", "model": "x"}), base={})
