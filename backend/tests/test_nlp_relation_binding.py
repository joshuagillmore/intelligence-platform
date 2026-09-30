"""G-12: NLP relations bind to the entity the words actually refer to.

Two faults in the dependency-parse relation stage:

- Entities are renamed after determiner stripping ("the Russian Foreign
  Intelligence Service" -> "Russian Foreign Intelligence Service"), but the
  sentence pass looked spans up by their unstripped text, so those entities
  were never in any sentence and got no relations at all.
- A verb's subject/object was bound by substring: ``"it" in "Citrix"``, or
  the entity name appearing within 20 characters after the token. "It
  targeted Citrix servers last week" produced ``Citrix TARGETS last week``.
"""
from __future__ import annotations

from intel_platform.services.extraction import extract_entities_nlp


def _typed(text: str) -> set[tuple[str, str, str]]:
    _, rels = extract_entities_nlp(text, "doc-g12")
    return {(r["source_name"], r["rel_type"], r["target_name"])
            for r in rels if r["rel_type"] != "ASSOCIATED_WITH"}


def test_determiner_stripped_entities_keep_their_relations():
    rels = _typed("The Russian Foreign Intelligence Service targeted the German Federal Foreign Office.")
    assert ("Russian Foreign Intelligence Service", "TARGETS", "German Federal Foreign Office") in rels


def test_a_determiner_stripped_subject_and_object_both_bind():
    rels = _typed("The Lazarus Group targeted the Bank of Bangladesh in February 2016.")
    assert ("Lazarus Group", "TARGETS", "Bank of Bangladesh") in rels


def test_a_pronoun_is_not_bound_to_a_name_that_contains_its_letters():
    rels = _typed("It targeted Citrix servers last week.")
    assert not {r for r in rels if r[0] == "Citrix"}, rels
    assert ("Citrix", "TARGETS", "last week") not in rels


def test_an_entity_inside_the_subject_phrase_still_binds():
    """The legitimate case the old 20-character window approximated: the
    named actor sits inside the phrase the subject token ("Hackers") heads.
    (Subjects here are names en_core_web_sm tags; it does not tag APT29.)"""
    rels = _typed("Hackers from the Lazarus Group targeted the Bank of Bangladesh.")
    assert ("Lazarus Group", "TARGETS", "Bank of Bangladesh") in rels


def test_regex_indicators_still_bind_as_objects():
    assert ("Lazarus Group", "EXPLOITS", "CVE-2023-4966") in _typed(
        "The Lazarus Group exploited CVE-2023-4966 in March 2024.")
    assert ("Lazarus Group", "USES", "185.220.101.42") in _typed(
        "The Lazarus Group used 185.220.101.42 for command and control.")
