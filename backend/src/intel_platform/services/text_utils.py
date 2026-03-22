"""Shared text utilities for sentence-level relevance scoring and excerpt extraction."""
from __future__ import annotations

import re

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
