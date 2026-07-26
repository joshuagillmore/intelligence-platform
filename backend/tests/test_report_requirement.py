"""Reports are grounded in the requirement that drove the collection.

Without it, `POST /reports/generate` is "tell me about these entities". A live
run collecting on Iranian intrusions into water-utility OT produced an
assessment of the EPA website's language options and topic menu — including
"Bed Bugs" — in full ICD 203 probability language, because navigation furniture
was among the entities passed in.
"""
from __future__ import annotations

from intel_platform.api.routes.reports import GenerateReportRequest


class TestRequirementField:
    def test_defaults_to_empty(self):
        req = GenerateReportRequest(project_id="p")
        assert req.requirement == ""
        assert req.pir_id is None

    def test_accepts_requirement_text(self):
        req = GenerateReportRequest(project_id="p", requirement="Which groups compromised OT?")
        assert req.requirement == "Which groups compromised OT?"

    def test_accepts_pir_id(self):
        req = GenerateReportRequest(project_id="p", pir_id="abc-123")
        assert req.pir_id == "abc-123"


class TestRetrievalQuerySelection:
    """The requirement leads retrieval when present; entity names are fallback."""

    @staticmethod
    def _query(requirement: str, entity_names: list[str], report_type: str) -> str:
        return requirement or ", ".join(entity_names) or report_type

    def test_requirement_wins(self):
        assert self._query("Iranian OT intrusions", ["EPA", "Arabic"], "general") == \
            "Iranian OT intrusions"

    def test_falls_back_to_entities(self):
        assert self._query("", ["Sandworm", "APT44"], "general") == "Sandworm, APT44"

    def test_falls_back_to_report_type(self):
        assert self._query("", [], "threat_assessment") == "threat_assessment"
