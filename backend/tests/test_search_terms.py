"""Global search matches every term, not the whole phrase.

`search_entities` matched `toLower(n.name) CONTAINS toLower($query)` — the
entire query as one literal substring. Any search of more than one word
therefore returned nothing: on a 5,486-entity project about Baltic cable
sabotage, "Baltic" returned results, "cable" returned results, and
"Baltic cable" returned an empty page, because no entity is named that
exactly. Typing a phrase is how anyone uses a search box.
"""
from __future__ import annotations

import pytest

from intel_platform.graph.store import _MAX_SEARCH_TERMS, _search_terms


class TestSearchTerms:
    def test_a_phrase_becomes_separate_terms(self):
        assert _search_terms("Baltic cable") == ["baltic", "cable"]

    def test_matching_is_case_insensitive(self):
        assert _search_terms("Yi Peng 3") == ["yi", "peng", "3"]

    def test_a_single_word_is_unchanged(self):
        assert _search_terms("Baltic") == ["baltic"]

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n", None])
    def test_blank_input_filters_nothing(self, blank):
        """A filter on " " would quietly restrict results to names containing a
        space — a subtle wrong answer where no filter is the right one."""
        assert _search_terms(blank) == []

    def test_repeated_whitespace_does_not_create_empty_terms(self):
        """An empty term becomes CONTAINS "", which matches everything and
        makes the query slower for no effect."""
        assert _search_terms("  Baltic   cable  ") == ["baltic", "cable"]

    def test_a_pasted_paragraph_is_bounded(self):
        """Each term is another CONTAINS clause in the Cypher statement."""
        assert len(_search_terms(" ".join(f"w{i}" for i in range(200)))) == _MAX_SEARCH_TERMS


class TestQueryConstruction:
    """The clause the terms build, checked without a database."""

    def _cypher_for(self, query: str) -> tuple[str, dict]:
        cypher = "MATCH (n) WHERE n.project_id = $project_id"
        params: dict = {"project_id": "p"}
        for i, term in enumerate(_search_terms(query)):
            cypher += f" AND toLower(n.name) CONTAINS $q{i}"
            params[f"q{i}"] = term
        return cypher, params

    def test_every_term_gets_its_own_clause(self):
        cypher, params = self._cypher_for("Baltic cable")
        assert cypher.count("CONTAINS") == 2
        assert params["q0"] == "baltic" and params["q1"] == "cable"

    def test_terms_are_parameters_not_interpolated_text(self):
        """Only the parameter *name* is built by hand; the value stays bound."""
        cypher, params = self._cypher_for("'; MATCH (x) DETACH DELETE x //")
        assert "DETACH DELETE" not in cypher
        assert any("delete" in str(v) for v in params.values())

    def test_no_query_leaves_the_statement_unfiltered(self):
        cypher, params = self._cypher_for("")
        assert "CONTAINS" not in cypher
        assert list(params) == ["project_id"]


class TestAgainstTheGraph:
    """The behaviour that was broken, against a real Neo4j."""

    @pytest.fixture
    def seeded(self, graph_store):
        from intel_platform.models.entities import Organization

        project = "test-search-terms"
        for name in ("Baltic Sea Cable Incidents", "Baltic Air Policing", "Undersea Cable Repair"):
            graph_store.create_entity(Organization(name=name, project_id=project))
        return project

    def test_a_phrase_finds_the_entity_that_contains_both_words(self, graph_store, seeded):
        names = [e["name"] for e in graph_store.search_entities(project_id=seeded, query="Baltic cable")]
        assert names == ["Baltic Sea Cable Incidents"]

    def test_word_order_does_not_matter(self, graph_store, seeded):
        names = [e["name"] for e in graph_store.search_entities(project_id=seeded, query="cable baltic")]
        assert names == ["Baltic Sea Cable Incidents"]

    def test_single_words_still_match_broadly(self, graph_store, seeded):
        names = sorted(e["name"] for e in graph_store.search_entities(project_id=seeded, query="baltic"))
        assert names == ["Baltic Air Policing", "Baltic Sea Cable Incidents"]

    def test_partial_words_still_match(self, graph_store, seeded):
        """Substring matching is what makes the search forgiving; keep it."""
        names = [e["name"] for e in graph_store.search_entities(project_id=seeded, query="Balt Cabl")]
        assert names == ["Baltic Sea Cable Incidents"]

    def test_an_absent_term_still_returns_nothing(self, graph_store, seeded):
        assert graph_store.search_entities(project_id=seeded, query="Baltic submarine") == []


class TestEntityCount:
    """The total that tells a caller its list is truncated.

    Every list view took the server's default `limit=50` and said nothing about
    it: the network sidebar grouped 50 of 5,486 entities under type headings
    that read as totals, beside a graph holding 156 Organizations.
    """

    @pytest.fixture
    def seeded(self, graph_store):
        from intel_platform.models.entities import Organization, Person

        project = "test-entity-count"
        for i in range(7):
            graph_store.create_entity(Organization(name=f"Baltic Org {i}", project_id=project))
        for i in range(3):
            graph_store.create_entity(Person(name=f"Person {i}", project_id=project))
        return project

    def test_the_total_exceeds_the_page(self, graph_store, seeded):
        page = graph_store.search_entities(project_id=seeded, limit=4)
        assert len(page) == 4
        assert graph_store.count_entities(project_id=seeded) == 10

    def test_the_count_honours_the_type_filter(self, graph_store, seeded):
        assert graph_store.count_entities(project_id=seeded, entity_type="Organization") == 7
        assert graph_store.count_entities(project_id=seeded, entity_type="Person") == 3

    def test_the_count_honours_the_search_terms(self, graph_store, seeded):
        """It must describe the same set as the page it accompanies — a total
        for a different filter would mislead worse than no total at all."""
        assert graph_store.count_entities(project_id=seeded, query="baltic org") == 7
        assert graph_store.count_entities(project_id=seeded, query="person") == 3

    def test_counting_is_scoped_to_the_project(self, graph_store, seeded):
        from intel_platform.models.entities import Organization

        graph_store.create_entity(Organization(name="Elsewhere", project_id="test-entity-count-other"))
        assert graph_store.count_entities(project_id=seeded) == 10

    def test_an_empty_project_counts_zero(self, graph_store):
        assert graph_store.count_entities(project_id="test-entity-count-empty") == 0

    def test_count_and_search_agree_when_nothing_is_truncated(self, graph_store, seeded):
        found = graph_store.search_entities(project_id=seeded, entity_type="Person", limit=50)
        assert len(found) == graph_store.count_entities(project_id=seeded, entity_type="Person")
