"""Per-document structured summarization.

Produces an analyst-facing summary card (summary / key_facts / topics / sentiment)
for a crawled document, mirroring Quarry's extractor but using the platform's
LLM provider abstraction. This complements graph entity/relationship extraction —
it gives analysts a fast read on each source without traversing the graph.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_MAX_CHARS = 20000

_SYSTEM = (
    "You are a data extraction assistant for intelligence analysts. "
    "Extract structured information from a web document. "
    "Always respond with ONLY valid JSON, no markdown, no preamble."
)

_PROMPT = (
    "Analyze this document and return JSON with exactly these keys:\n"
    '1. "summary": a 2-3 sentence summary of the content\n'
    '2. "key_facts": a list of the most important facts or claims (strings)\n'
    '3. "topics": a list of main topics or themes (strings)\n'
    '4. "sentiment": overall sentiment, one of "positive", "negative", "neutral", "mixed"\n'
)


def _parse_json(text: str) -> dict | None:
    """Best-effort JSON parse: strip code fences, direct parse, then brace-match."""
    if not text or not text.strip():
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start >= 0:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
                continue
            if c == "\\" and in_str:
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
    return None


async def summarize_document(content: str, provider) -> dict | None:
    """Generate a structured summary for a document's cleaned content.

    Args:
        content: cleaned document text (markdown/plain).
        provider: an LLM provider exposing async ``generate(messages, system, temperature, max_tokens)``
            that returns an object with a ``.content`` string.

    Returns:
        dict with keys summary/key_facts/topics/sentiment, or None on failure.
    """
    if not content or not content.strip() or provider is None:
        return None

    snippet = content[:_MAX_CHARS]
    if len(content) > _MAX_CHARS:
        snippet += "\n\n[...truncated...]"

    messages = [{"role": "user", "content": f"{_PROMPT}\n\n---\n{snippet}"}]

    try:
        result = await provider.generate(
            messages=messages,
            system=_SYSTEM,
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception as e:
        logger.warning("Summarization provider call failed: %s", e)
        return None

    parsed = _parse_json(getattr(result, "content", "") or "")
    if not isinstance(parsed, dict):
        logger.warning("Summarization returned unparseable content")
        return None

    # Normalize shape with safe defaults.
    return {
        "summary": str(parsed.get("summary", ""))[:2000],
        "key_facts": [str(f) for f in parsed.get("key_facts", []) if f][:20],
        "topics": [str(t) for t in parsed.get("topics", []) if t][:20],
        "sentiment": str(parsed.get("sentiment", "neutral")),
    }
