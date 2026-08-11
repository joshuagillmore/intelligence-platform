"""Shared text utilities for sentence-level relevance scoring and excerpt extraction."""
from __future__ import annotations

import re
from typing import Any

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def extract_relevant_passages(
    text: str,
    keywords: list[str],
    max_chars: int = 3000,
    max_passages: int = 5,
) -> list[dict[str, object]]:
    """Extract the most relevant sentences from text based on keyword matches.

    Returns a list of dicts with 'text', 'score', and 'matched_keywords'.
    Sorted by relevance score descending.
    """
    if not text or not keywords:
        return []

    sentences = _SENTENCE_SPLIT_RE.split(text)
    keyword_lower = [kw.lower() for kw in keywords]

    scored: list[tuple[float, str, list[str]]] = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:
            continue
        sent_lower = sent.lower()
        score = 0.0
        matched: list[str] = []
        for kw, kw_low in zip(keywords, keyword_lower):
            if kw_low in sent_lower:
                score += 1.0
                matched.append(kw)
        if score > 0:
            scored.append((score, sent, matched))

    scored.sort(key=lambda x: -x[0])

    results: list[dict[str, object]] = []
    total_chars = 0
    for score, sent, matched in scored:
        if len(results) >= max_passages:
            break
        if total_chars + len(sent) > max_chars:
            break
        results.append({
            "text": sent,
            "score": score,
            "matched_keywords": matched,
        })
        total_chars += len(sent) + 2

    return results


def count_keyword_matches(text: str, keywords: list[str]) -> dict[str, int]:
    """Count how many times each keyword appears in the text.

    Returns {keyword: count} for keywords that appear at least once.
    """
    if not text or not keywords:
        return {}

    text_lower = text.lower()
    counts: dict[str, int] = {}
    for kw in keywords:
        n = text_lower.count(kw.lower())
        if n > 0:
            counts[kw] = n
    return counts


def normalize_datetime(val: Any) -> str:
    """Normalize a Neo4j datetime value to an ISO string.

    Handles raw strings, Python datetime objects, and the internal Neo4j
    ``_DateTime__date`` / ``_DateTime__time`` dict representation.
    """
    if not val:
        return ""
    if isinstance(val, str):
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, dict):
        dt = val.get("_DateTime__date", {})
        tm = val.get("_DateTime__time", {})
        try:
            year = dt.get("_Date__year", 2026)
            month = dt.get("_Date__month", 1)
            day = dt.get("_Date__day", 1)
            hour = tm.get("_Time__hour", 0)
            minute = tm.get("_Time__minute", 0)
            second = tm.get("_Time__second", 0)
            return f"{year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
        except (TypeError, ValueError):
            return ""
    return str(val)


# ---------------------------------------------------------------------------
# Markup stripping
# ---------------------------------------------------------------------------

# A wiki citation marker: "[[27]](https://...#cite_note-eju-27)". Removed
# whole — the number refers to a reference list that is not in the chunk, so it
# carries nothing for either the model or the reader.
_CITATION = re.compile(r"\[\[\d+\]\]\([^)]*\)")
# Section-edit affordances scraped from wiki pages. They appear wrapped in a
# second pair of brackets — "[[edit](https://...)]" — so the wrapper goes too;
# stripping only the inner link leaves a stray "[]" behind.
_EDIT_LINK = re.compile(r"\[?\[\s*edit\s*\]\([^)]*\)\]?", re.I)
# A markdown link or image: keep what it says, drop where it points.
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# A link whose closing paren was lost to chunking: "[NATO](https://en.wiki
_TRUNCATED_LINK = re.compile(r"!?\[([^\]]*)\]\([^)\s]*$", re.M)
# Leading heading hashes and blockquote markers; the text after them is content.
_HEADING = re.compile(r"^[ \t]*(?:#{1,6}|>+)[ \t]*", re.M)
_EMPHASIS = re.compile(r"\*\*|__")
# Single-underscore italics — "_Yi Peng 3_". Bounded so snake_case identifiers
# and mid-word underscores are left alone.
_ITALIC = re.compile(r"(?<![A-Za-z0-9_])_([^_\n]{1,80})_(?![A-Za-z0-9_])")
# A chunk that begins inside a URL, because chunking split a markdown link:
# "://en.wikipedia.org/wiki/Baltic_Sea \"Baltic Sea\"). The incidents...".
# Only matched at the very start of the text, where it cannot be prose.
_ORPHAN_URL_HEAD = re.compile(r'^://\S*(?:\s+"[^"]*")?\)?[.,;:]?[ \t]*')
_BLANK_RUN = re.compile(r"\n{3,}")


def strip_markup(text: str) -> str:
    """Remove markdown syntax, keeping the words.

    Collected pages arrive as markdown, and 36% of the characters in a
    retrieved chunk were link and citation syntax rather than prose. That is
    context budget spent on URLs, embeddings partly driven by URL tokens, and
    evidence panels showing an analyst `[[27]](https://en.wikipedia.org/...)`
    mid-sentence.

    Deliberately conservative: link *text* survives, because "[NATO](url)"
    means NATO. Only the machinery goes.
    """
    if not text:
        return ""
    out = _CITATION.sub("", text)
    out = _EDIT_LINK.sub("", out)
    out = _LINK.sub(r"\1", out)
    out = _TRUNCATED_LINK.sub(r"\1", out)
    out = _HEADING.sub("", out)
    out = _EMPHASIS.sub("", out)
    out = _ITALIC.sub(r"\1", out)
    out = _ORPHAN_URL_HEAD.sub("", out)
    # Collapse the whitespace the removals leave behind, without joining
    # paragraphs that were always separate.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = _BLANK_RUN.sub("\n\n", out)
    return out.strip()
