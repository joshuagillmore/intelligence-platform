"""Reading labelled values back out of model output.

A prompt asks for ``PROBABILITY: 0.78`` and the reply is ``**PROBABILITY:**
**0.70**``. Models emphasise the label they were told to emit, and they do it
inconsistently between calls, so a pattern written against the requested shape
matches until it silently does not.

That has now happened four times in this codebase — EEI verdict lines, EEI
section headings, generated-assessment probabilities, and collection-plan source
configs — and each failure was quiet: the value fell back to a default, and the
default looked like a real answer. An assessment reading "Likely" was stored at
"Roughly Even Chance" for exactly this reason.

These helpers treat markdown emphasis as noise around the value rather than
something to enumerate arrangements of.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Asterisks, underscores and whitespace are one interchangeable run. Enumerating
# arrangements ("**LABEL:**", "**LABEL**:", "**LABEL:** **value**") is what kept
# failing — each fix covered the form that had been seen and missed the next.
_EMPHASIS = r"[\s*_`]*"


def labelled_value(content: str, label: str, pattern: str = r"(.+?)\s*$") -> str | None:
    """The value following ``LABEL:``, whatever emphasis surrounds either.

    `pattern` matches the value itself and must contain exactly one group.
    Returns ``None`` when the label is absent, so a caller can tell "not stated"
    from "stated as empty" rather than conflating them with a default.
    """
    if not content:
        return None
    rx = re.compile(
        rf"{re.escape(label)}{_EMPHASIS}:{_EMPHASIS}{pattern}",
        re.IGNORECASE | re.MULTILINE,
    )
    match = rx.search(content)
    return match.group(1).strip().strip("*_` ") if match else None


def labelled_probability(content: str, fallback: float) -> float:
    """A probability stated as ``PROBABILITY: 0.78``, in any emphasis.

    A value outside 0..1 falls back rather than being clamped: a model writing
    ``PROBABILITY: 78`` meant percent, and clamping to 1.0 would silently
    substitute a different judgement for the one it made.
    """
    raw = labelled_value(content, "PROBABILITY", r"(\d?\.\d+|[01](?:\.\d+)?)")
    if raw is None:
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    return value if 0.0 < value <= 1.0 else fallback


def json_object(content: str, label: str | None = None) -> dict[str, Any]:
    """The first JSON object in a reply, however the model chose to present it.

    ``labelled_json`` requires the object on the label's own line, which is the
    shape the prompt asks for and not reliably the shape that comes back: models
    pretty-print across lines, wrap the object in a ```json fence, or introduce
    it with a sentence. Reading only the requested shape is the failure this
    module exists to stop, so this scans for a balanced object anywhere in the
    reply — preferring one that follows `label` when given.

    Returns ``{}`` when nothing parses.
    """
    if not content:
        return {}

    if label:
        direct = labelled_json(content, label)
        if direct:
            return direct
        marker = re.search(rf"{re.escape(label)}{_EMPHASIS}:", content, re.IGNORECASE)
        if marker:
            found = _first_balanced_object(content[marker.end():])
            if found:
                return found

    return _first_balanced_object(content) or {}


def _first_balanced_object(text: str) -> dict[str, Any]:
    """Scan for the first brace-balanced object that parses, ignoring strings."""
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for end in range(start, len(text)):
            ch = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:end + 1])
                    except json.JSONDecodeError:
                        break  # this candidate is not JSON; try the next brace
                    return parsed if isinstance(parsed, dict) else {}
    return {}


def labelled_json(line: str, label: str) -> dict[str, Any]:
    """A JSON object on a ``LABEL: {...}`` line, in any emphasis.

    Returns ``{}`` for a line that carries no such object or whose object does
    not parse — both are "nothing usable here", and the caller cannot act on the
    difference.
    """
    raw = labelled_value(line, label, r"(\{.*\})")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
