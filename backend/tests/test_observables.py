"""Tests for cyber observable normalization (refang/defang + classification)."""
from intel_platform.enrichment.observables import (
    classify_observable,
    defang,
    refang,
)


# --- refang: turn defanged threat-intel notation back into real values ------

def test_refang_bracketed_dot():
    assert refang("1.2.3[.]4") == "1.2.3.4"


def test_refang_scheme_and_dot():
    assert refang("hxxps://evil[.]com/x") == "https://evil.com/x"


def test_refang_at_and_dot_words():
    assert refang("a(at)b(dot)com") == "a@b.com"


def test_refang_mixed_case_scheme():
    assert refang("hXXp://bad[.]actor[.]ru") == "http://bad.actor.ru"


def test_refang_plain_text_unchanged():
    # No defang markers -> text is returned untouched.
    assert refang("the meeting is at noon on 3.5 acres") == "the meeting is at noon on 3.5 acres"


def test_refang_empty():
    assert refang("") == ""


# --- refang must leave ordinary prose alone (Low -> E) ----------------------
# refang runs over whole documents before spaCy; "(DOT)" and "(AT)" are
# everyday acronyms, and rewriting them corrupted the text being extracted.

def test_refang_leaves_a_parenthesised_dot_acronym_alone():
    text = "Department of Transportation (DOT) issued new guidance."
    assert refang(text) == text


def test_refang_leaves_a_parenthesised_at_country_code_alone():
    assert refang("Vienna, Austria (AT)") == "Vienna, Austria (AT)"
    assert refang("Offices in Austria (AT) and Germany (DE).") == "Offices in Austria (AT) and Germany (DE)."


def test_refang_word_markers_inside_a_token_still_refang():
    assert refang("evil(dot)com") == "evil.com"
    assert refang("user(at)host") == "user@host"
    assert refang("user[at]evil[dot]com") == "user@evil.com"
    assert refang("EVIL{DOT}COM") == "EVIL.COM"


def test_refang_symbol_markers_refang_anywhere():
    assert refang("evil (.) com") == "evil . com"  # unambiguous symbol, token or not
    assert refang("user[@]evil[.]com") == "user@evil.com"


# --- defang: inverse, and it must round-trip through refang ------------------

def test_defang_ip_roundtrips():
    assert refang(defang("1.2.3.4")) == "1.2.3.4"


# --- classify_observable: value -> entity type ------------------------------

def test_classify_ip():
    assert classify_observable("8.8.8.8") == "IPAddress"


def test_classify_domain():
    assert classify_observable("evil.com") == "Domain"


def test_classify_url():
    assert classify_observable("http://x.com/a") == "URL"


def test_classify_email():
    assert classify_observable("a@b.com") == "EmailAddress"


def test_classify_refangs_first():
    # A defanged value classifies as its real type.
    assert classify_observable("evil[.]com") == "Domain"
    assert classify_observable("1.2.3[.]4") == "IPAddress"


def test_classify_unknown():
    assert classify_observable("just some words") == ""


def test_classify_rejects_bad_octets():
    # 999 is not a valid octet -> not an IP (falls through, no domain either).
    assert classify_observable("999.1.1.1") == ""
