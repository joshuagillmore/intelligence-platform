"""The PIR judge: does the collected intelligence answer a requirement?

- ``eeis``      capturing Essential Elements of Information from a refinement
- ``evidence``  the graph sample, dated entities, per-element passages, the
                context budgets and the screening of scraped text
- ``verdicts``  reading verdicts out of the reply, settling them into a status
- ``judge``     the steps the assess route runs: source budget, graph read,
                context, the model exchange, the recommendation

The HTTP route is ``api/routes/pirs/assess.py``.
"""
from __future__ import annotations

from intel_platform.services.pir_judge.eeis import extract_eeis
from intel_platform.services.pir_judge.evidence import PassageEvidence
from intel_platform.services.pir_judge.judge import (
    GraphSample,
    JudgeReply,
    SourceBudget,
    build_context,
    criteria,
    gather_graph,
    recommendation,
    run_judge,
    source_budget,
    stopped_on_budget,
)
from intel_platform.services.pir_judge.verdicts import Settlement, parse_verdicts, settle

__all__ = [
    "GraphSample",
    "JudgeReply",
    "PassageEvidence",
    "Settlement",
    "SourceBudget",
    "build_context",
    "criteria",
    "extract_eeis",
    "gather_graph",
    "parse_verdicts",
    "recommendation",
    "run_judge",
    "settle",
    "source_budget",
    "stopped_on_budget",
]
