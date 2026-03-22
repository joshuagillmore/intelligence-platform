"""Tests for the shared text_utils module."""
from intel_platform.services.text_utils import extract_relevant_passages, count_keyword_matches


# ---------------------------------------------------------------------------
# extract_relevant_passages
# ---------------------------------------------------------------------------

def test_extract_relevant_passages_basic():
    text = (
        "Iran is expanding naval operations in the Caspian Sea. "
        "Russia continues military buildup near Ukraine. "
        "Iran tests new missile system aimed at regional targets."
    )
    passages = extract_relevant_passages(text, ["iran", "naval"])
    assert len(passages) >= 1
    # The passage mentioning both keywords should score highest
    assert passages[0]["score"] >= 2.0
    assert "iran" in passages[0]["matched_keywords"]
    assert "naval" in passages[0]["matched_keywords"]


def test_extract_relevant_passages_no_matches():
    text = "The weather is sunny today. Birds are singing."
    passages = extract_relevant_passages(text, ["iran", "nuclear"])
    assert passages == []


def test_extract_relevant_passages_empty_inputs():
    assert extract_relevant_passages("", ["keyword"]) == []
    assert extract_relevant_passages("some text", []) == []
    assert extract_relevant_passages("", []) == []


def test_extract_relevant_passages_max_chars():
    # Long text with multiple matching sentences
    sentences = [f"Iran mentioned in sentence {i}. " for i in range(20)]
    text = " ".join(sentences)
    passages = extract_relevant_passages(text, ["iran"], max_chars=200)
    total_chars = sum(len(p["text"]) for p in passages)
    assert total_chars <= 200 + 50  # small buffer for joining


def test_extract_relevant_passages_max_passages():
    sentences = [f"Iran mentioned in sentence {i}. " for i in range(20)]
    text = " ".join(sentences)
    passages = extract_relevant_passages(text, ["iran"], max_passages=3)
    assert len(passages) <= 3


def test_extract_relevant_passages_case_insensitive():
    text = "IRAN is a country. iran has nuclear ambitions. Iran's economy is growing."
    passages = extract_relevant_passages(text, ["iran"])
    assert len(passages) >= 2


def test_extract_relevant_passages_multiple_keywords():
    text = (
        "APT29 is attributed to Russian intelligence services. "
        "The group uses spearphishing to gain initial access. "
        "APT29 targets government networks with custom malware."
    )
    passages = extract_relevant_passages(text, ["apt29", "malware", "government"])
    assert len(passages) >= 1
    # The sentence mentioning apt29 + government + malware should be ranked high
    top = passages[0]
    assert top["score"] >= 2.0


def test_extract_relevant_passages_short_sentences_skipped():
    text = "Yes. No. Iran expands operations significantly."
    passages = extract_relevant_passages(text, ["iran"])
    # "Yes." and "No." should be skipped (< 20 chars)
    assert len(passages) == 1
    assert "expands" in passages[0]["text"]


# ---------------------------------------------------------------------------
# count_keyword_matches
# ---------------------------------------------------------------------------

def test_count_keyword_matches_basic():
    text = "Iran is expanding operations. Iran tests new systems."
    matches = count_keyword_matches(text, ["iran", "operations", "nuclear"])
    assert matches["iran"] == 2
    assert matches["operations"] == 1
    assert "nuclear" not in matches  # no match = not in result


def test_count_keyword_matches_case_insensitive():
    text = "RUSSIA and Russia are the same."
    matches = count_keyword_matches(text, ["russia"])
    assert matches["russia"] == 2


def test_count_keyword_matches_empty():
    assert count_keyword_matches("", ["keyword"]) == {}
    assert count_keyword_matches("some text", []) == {}


def test_count_keyword_matches_no_matches():
    text = "The quick brown fox jumps over the lazy dog."
    matches = count_keyword_matches(text, ["iran", "nuclear"])
    assert matches == {}
