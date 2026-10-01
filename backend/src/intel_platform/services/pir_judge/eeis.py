"""Capturing a requirement's Essential Elements of Information (EEIs) from an
LLM refinement: the criteria the judge later scores collection against.
"""
from __future__ import annotations

import re


# No upper bound on the body: a 300-character cap silently discarded long EEIs
# with no trace, and a dropped criterion is invisible in the assessment. Length
# is trimmed in _clean_eei instead, so a long element is shortened, not lost.
_EEI_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)]|EEI\s*\d*\s*[:.\-])\s*(?P<body>.{8,}?)\s*$",
    re.IGNORECASE,
)

_EEI_MAX_CHARS = 400

# Anchored, and required to look like a heading. A bare `.search` opened the
# capture section on any sentence that merely mentioned EEIs — "The requirement
# should be decomposed into EEIs before collection begins." — after which the
# model's numbered critique of the PIR was captured as collection criteria that
# collection can never satisfy.
# The negative lookahead keeps "EEI 3: Specific devices…" out — that is a
# numbered item, handled by _EEI_LINE, not a section heading.
_EEI_HEADING = re.compile(
    # The optional `3.` is a numbered *section* heading — refinements routinely
    # write "3. **Essential Elements of Information (EEIs)**", and anchoring
    # without it broke EEI capture outright on that shape. Safe to allow,
    # because the heading words are still required immediately after.
    r"^[#*\s>]*(?:\d+[.)]\s*)?[#*\s>]*"
    r"(?:essential elements(?:\s+of\s+information)?|EEIs?)\b(?!\s*\d)"
    r"[\s*]*:?[\s*]*(?P<tail>.*)$",
    re.IGNORECASE,
)

# Models double-label: "3. EEI 3: Specific devices…". The outer marker is
# consumed by _EEI_LINE, so strip the inner one too or it lands in the criterion.
_EEI_PREFIX = re.compile(r"^EEI\s*\d*\s*[:.\-]\s*", re.IGNORECASE)

# Refinements narrate their own work ("The refined version provides a clearer
# focus on…"). Captured as a criterion it can never be satisfied by collection,
# so it would sit in unmet_criteria forever and block SATISFIED.
_EEI_META = re.compile(
    r"\b(?:refined|revised|original|updated)\s+"
    r"(?:pir|version|requirement|statement|question|wording)\b",
    re.IGNORECASE,
)

# Models annotate their own list: every real EEI is followed by a line
# explaining it. "This element focuses on identifying the exact vessel types
# involved" is a note about criterion 1, not criterion 2 — but captured as one
# it is unsatisfiable, and a maritime run was scored against three real criteria
# and three impossible ones. Matched at the start, so an EEI that legitimately
# contains the phrase mid-sentence survives.
_EEI_ANNOTATION = re.compile(
    r"^\s*this\s+(?:element|eei|criterion|requirement|question|sub-?question)\b",
    re.IGNORECASE,
)


def _clean_eei(raw: str) -> str:
    """Normalise one captured line into a usable collection criterion.

    Observed live, in order of appearance: an inner `EEI 3:` label surviving the
    outer marker, `**bold**` runs left mid-string by "**Initial Access
    Vectors:** Determine…", and section labels like "Refined PIR:" picked up as
    if they were criteria. A criterion that is only a label cannot be judged,
    so it is dropped rather than assessed and reported as unmet.
    """
    body = _EEI_PREFIX.sub("", raw.strip().strip("*_ ")).replace("**", "").strip("*_ ").strip()
    # A real criterion states something; a trailing colon means this was a
    # heading introducing the content below it.
    if not body or body.endswith(":"):
        return ""
    # Commentary about the refinement, or about a criterion, is not something
    # collection can answer — and left in it can never be satisfied.
    if _EEI_META.search(body) or _EEI_ANNOTATION.match(body):
        return ""
    if len(body) > _EEI_MAX_CHARS:
        body = body[:_EEI_MAX_CHARS].rstrip() + "…"
    return body


def extract_eeis(analysis: str, limit: int = 8) -> list[str]:
    """Pull Essential Elements of Information out of an LLM refinement.

    The refinement prompt already asks the model to break the requirement into
    EEIs, so they exist in the analysis prose — they were simply never captured
    onto the PIR, which left `Pir.eeis` empty and satisfaction unmeasurable.
    """
    if not analysis:
        return []
    eeis: list[str] = []
    in_section = False
    for raw in analysis.split("\n"):
        line = raw.strip()
        if not line:
            continue
        heading = _EEI_HEADING.match(line)
        if heading and len(line) < 160:
            in_section = True
            # A heading may carry the first EEI inline after its colon.
            tail = _clean_eei(heading.group("tail"))
            if len(tail) >= 8:
                eeis.append(tail)
            continue
        if not in_section:
            continue
        match = _EEI_LINE.match(line)
        if match:
            body = _clean_eei(match.group("body"))
            if body and body.lower() not in {e.lower() for e in eeis}:
                eeis.append(body)
        elif line.startswith("#") or line.startswith("**"):
            # A new heading ends the EEI list.
            in_section = False
        if len(eeis) >= limit:
            break
    return eeis[:limit]
