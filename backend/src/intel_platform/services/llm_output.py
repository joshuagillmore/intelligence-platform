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


# The value must not run on into another digit or a percent sign. Without the
# boundary the leading `1` of `15%`, `10` or `12.5%` matched on its own, read as
# 1.0 — "Almost Certain" or, past the label table, "Unknown" — a judgement the
# model never made.
_PROBABILITY_VALUE = r"(\d?\.\d+|[01](?:\.\d+)?)(?![\d%])"

# `:` is the requested separator; `|` is the same label as a markdown table row
# ("| **PROBABILITY** | 0.40 |"). A header row naming the column is not a value
# and fails the number pattern, so the scan moves on rather than misreading it.
_PROBABILITY_LINE = re.compile(
    rf"PROBABILITY{_EMPHASIS}[:|]{_EMPHASIS}{_PROBABILITY_VALUE}",
    re.IGNORECASE,
)


def labelled_probability_parsed(content: str | None, fallback: float) -> tuple[float, bool]:
    """A stated probability and whether it was actually stated.

    Returns ``(value, True)`` when the reply carries a readable probability in
    0 < p <= 1, and ``(fallback, False)`` otherwise — including a reply that is
    prose with no label at all. The flag is what lets a caller report that a
    stored 0.5 is a default rather than the model's judgement.

    A value outside 0..1 falls back rather than being clamped: a model writing
    ``PROBABILITY: 78`` meant percent, and clamping to 1.0 would silently
    substitute a different judgement for the one it made.
    """
    if not content:
        return fallback, False
    for match in _PROBABILITY_LINE.finditer(content):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if 0.0 < value <= 1.0:
            return value, True
    return fallback, False


def labelled_probability(content: str | None, fallback: float) -> float:
    """A probability stated as ``PROBABILITY: 0.78``, in any emphasis.

    See `labelled_probability_parsed`, which also says whether the value was
    stated or is the fallback.
    """
    return labelled_probability_parsed(content, fallback)[0]


# Emphasis underscores sit at a word edge; an underscore between word characters
# is part of a name (`EEI_ASSESSMENT`, `snake_case`) and must survive.
_EDGE_UNDERSCORES = re.compile(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])")
# One leading marker at a time: blockquote, heading, bullet, or a list number.
# A number followed by a pipe is a table cell carrying the element number, not
# list decoration, so it is left for the caller's pattern to read.
_LEADING_MARKER = re.compile(r"^(?:>+\s*|#{1,6}\s+|[-+•–—]\s+|\d+[.)]\s+(?!\|))")


def normalise_line(line: str | None) -> str:
    """A model's line with its decoration removed, for line-oriented parsers.

    Strips `*`, backticks and emphasis underscores anywhere; leading
    blockquote, heading, bullet and ``1.``/``1)`` numbering markers; and the
    outer pipes of a markdown table row. Whitespace is collapsed to single
    spaces. Inner table pipes are kept — they are the field separators a
    verdict-style line is read by.

    Parsers written against the requested shape kept failing on the same
    handful of decorations (bold fields, numbered headings, table rows), each
    fixed one form at a time. Normalising first means a parser only has to
    describe the content.
    """
    if not line:
        return ""
    s = line.replace("`", "").replace("*", "")
    s = _EDGE_UNDERSCORES.sub("", s)
    s = " ".join(s.split())
    while True:
        before = s
        s = s.strip("|").strip()
        s = _LEADING_MARKER.sub("", s).strip()
        if s == before:
            return s


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
