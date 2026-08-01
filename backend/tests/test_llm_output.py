"""Labelled values survive however the model emphasises them.

Every case below is a form seen in live output or a near neighbour of one. The
failures this guards against were all silent: the value fell back to a default
and the default looked like a real answer.
"""
from __future__ import annotations

from intel_platform.services.llm_output import (
    json_object,
    labelled_json,
    labelled_probability,
    labelled_value,
)


class TestLabelledProbability:
    def test_every_emphasis_arrangement(self):
        for text in (
            "PROBABILITY: 0.70",
            "**PROBABILITY:** 0.70",
            "**PROBABILITY**: 0.70",
            "**PROBABILITY:** **0.70**",          # the live form
            "*PROBABILITY*: *0.70*",
            "__PROBABILITY__: __0.70__",
            "`PROBABILITY`: `0.70`",
            "PROBABILITY  :   **0.70**",
        ):
            assert labelled_probability(text, 0.5) == 0.70, text

    def test_found_at_the_end_of_a_long_assessment(self):
        body = "## Overview\n" + ("Narrative. " * 300) + "\n**PROBABILITY:** 0.91"
        assert labelled_probability(body, 0.5) == 0.91

    def test_leading_dot(self):
        assert labelled_probability("PROBABILITY: .85", 0.5) == 0.85

    def test_absent_falls_back(self):
        assert labelled_probability("No probability here.", 0.33) == 0.33
        assert labelled_probability("", 0.4) == 0.4

    def test_percent_style_is_not_clamped(self):
        """"PROBABILITY: 78" means percent; clamping would invent a judgement."""
        assert labelled_probability("PROBABILITY: 78", 0.5) == 0.5

    def test_zero_rejected_one_accepted(self):
        assert labelled_probability("PROBABILITY: 0.0", 0.5) == 0.5
        assert labelled_probability("PROBABILITY: 1.0", 0.5) == 1.0


class TestLabelledValue:
    def test_reads_a_plain_label(self):
        assert labelled_value("CONFIDENCE_LABEL: Likely", "CONFIDENCE_LABEL") == "Likely"

    def test_strips_surrounding_emphasis_from_the_value(self):
        assert labelled_value("**CONFIDENCE_LABEL:** **Likely**", "CONFIDENCE_LABEL") == "Likely"

    def test_absent_label_is_none_not_empty(self):
        """"not stated" and "stated as empty" are different answers."""
        assert labelled_value("nothing here", "PROBABILITY") is None

    def test_stops_at_the_end_of_the_line(self):
        text = "**VERDICT:** SATISFIED\n**NOTES:** something else"
        assert labelled_value(text, "VERDICT") == "SATISFIED"


class TestLabelledJson:
    def test_plain_config_line(self):
        got = labelled_json('CONFIG: {"url": "https://example.com"}', "CONFIG")
        assert got == {"url": "https://example.com"}

    def test_emphasised_config_line(self):
        got = labelled_json('**CONFIG:** {"url": "https://example.com"}', "CONFIG")
        assert got == {"url": "https://example.com"}

    def test_nested_object(self):
        got = labelled_json('CONFIG: {"urls": ["a", "b"], "max": 5}', "CONFIG")
        assert got["urls"] == ["a", "b"] and got["max"] == 5

    def test_malformed_json_is_empty_not_an_exception(self):
        assert labelled_json('CONFIG: {"url": broken}', "CONFIG") == {}

    def test_no_config_line(self):
        assert labelled_json("1. [web_scrape] Some source", "CONFIG") == {}

    def test_non_object_json_is_rejected(self):
        """A list is not a config; callers index it by key."""
        assert labelled_json('CONFIG: ["a", "b"]', "CONFIG") == {}


class TestPlanSourceConfigs:
    """The planner's CONFIG lines survive emphasis too.

    A miss here leaves the source with an empty config. The agentic RESOLVE
    phase fills those in at execution, so this was latent rather than breaking —
    but 28 of 162 stored sources carry an empty config.
    """

    def test_plain_config_is_read(self):
        from intel_platform.services.collection_planner import parse_plan_sources

        got = parse_plan_sources(
            '1. [web_scrape] Maritime incident reports\n'
            '   CONFIG: {"url": "https://www.ukmto.org/incidents"}\n'
        )
        assert got[0]["config"] == {"url": "https://www.ukmto.org/incidents"}

    def test_emphasised_config_is_read(self):
        from intel_platform.services.collection_planner import parse_plan_sources

        got = parse_plan_sources(
            '1. [web_scrape] Maritime incident reports\n'
            '   **CONFIG:** {"url": "https://www.ukmto.org/incidents"}\n'
        )
        assert got[0]["config"] == {"url": "https://www.ukmto.org/incidents"}

    def test_a_config_line_is_consumed_even_when_its_json_is_broken(self):
        """Otherwise the malformed line is read as the next source."""
        from intel_platform.services.collection_planner import parse_plan_sources

        got = parse_plan_sources(
            '1. [web_scrape] Maritime incident reports\n'
            '   CONFIG: {"url": broken}\n'
            '2. [rss_feed] Reuters world news feed\n'
        )
        assert len(got) == 2
        assert got[0]["config"] == {}
        assert got[1]["source_type"] == "rss_feed"

    def test_source_without_a_config_line_is_unaffected(self):
        from intel_platform.services.collection_planner import parse_plan_sources

        got = parse_plan_sources(
            '1. [web_scrape] Maritime incident reports\n'
            '2. [rss_feed] Reuters world news feed\n'
        )
        assert len(got) == 2 and got[0]["config"] == {}


class TestJsonObject:
    """Reading a JSON reply however the model chose to present it.

    `labelled_json` requires the object on the label's own line — the shape the
    prompt asks for, and not reliably the shape that comes back. Reading only
    the requested shape is the defect this module exists to stop, so the
    tolerant reader is tested against the forms models actually emit.
    """

    def test_one_line_labelled_object(self):
        assert json_object('ASSESSMENT: {"satisfied": true}', "ASSESSMENT") == {"satisfied": True}

    def test_pretty_printed_across_lines(self):
        content = 'ASSESSMENT:\n{\n  "satisfied": false,\n  "missing": "dates"\n}'
        assert json_object(content, "ASSESSMENT")["missing"] == "dates"

    def test_fenced_block(self):
        content = 'Here you go:\n```json\n{"satisfied": true, "confidence": "high"}\n```'
        assert json_object(content, "ASSESSMENT")["confidence"] == "high"

    def test_prose_before_and_after(self):
        content = 'I assessed it.\n{"satisfied": true}\nHope that helps.'
        assert json_object(content) == {"satisfied": True}

    def test_nested_objects_are_kept_whole(self):
        content = '{"a": {"b": {"c": 1}}, "d": 2}'
        assert json_object(content) == {"a": {"b": {"c": 1}}, "d": 2}

    def test_braces_inside_strings_do_not_end_the_object(self):
        content = '{"missing": "a } brace in prose", "satisfied": false}'
        assert json_object(content)["missing"] == "a } brace in prose"

    def test_escaped_quote_inside_a_string(self):
        content = r'{"missing": "he said \"no\"", "satisfied": false}'
        assert json_object(content)["missing"] == 'he said "no"'

    def test_label_is_preferred_over_an_earlier_object(self):
        content = '{"decoy": true}\nASSESSMENT: {"satisfied": true}'
        assert json_object(content, "ASSESSMENT") == {"satisfied": True}

    def test_malformed_candidate_does_not_stop_the_scan(self):
        content = "{not json at all}\n{\"satisfied\": true}"
        assert json_object(content) == {"satisfied": True}

    def test_no_object_returns_empty(self):
        assert json_object("no json here", "ASSESSMENT") == {}

    def test_empty_input_returns_empty(self):
        assert json_object("", "ASSESSMENT") == {}

    def test_a_json_array_is_not_an_object(self):
        assert json_object('[1, 2, 3]') == {}
