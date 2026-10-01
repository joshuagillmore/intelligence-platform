"""Reading the judge's verdicts back out of its reply, and settling them into
the requirement's status.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from intel_platform.db.models import PirStatus
from intel_platform.services.llm_output import normalise_line

logger = logging.getLogger(__name__)


# Models emit the verdict block inconsistently: some print "EEI_ASSESSMENT:" once
# as a header, others repeat it on every line, and some wrap the line in bold.
# The justification is optional: requiring it meant "1 | SATISFIED |" parsed as
# nothing, became UNASSESSED, and blocked SATISFIED on a verdict the model did
# give.
# Named groups throughout: the optional echo sits between the number and the
# verdict, so positional indices would shift depending on whether the model
# supplied it.
#
# Lines are passed through `llm_output.normalise_line` first, so bold fields,
# bullets, list numbering and the outer pipes of a markdown table row are gone
# before this pattern sees them. It describes only the content. A table cell
# may still carry "2." as the element number, hence the optional `.`/`)`.
_VERDICT_LINE = re.compile(
    r"^\s*\**\s*(?:EEI_ASSESSMENT\s*:)?\s*\**\s*(?:EEI\s*)?(?P<num>\d+)[.)]?\s*\|\s*"
    # Optional echo of the element being judged. Present when the model follows
    # the requested format; absent on looser replies, which still parse.
    r"(?:(?!SATISFIED|PARTIAL|UNMET)(?P<echo>[^|]{0,120}?)\s*\|\s*)?"
    r"(?P<verdict>SATISFIED|PARTIAL|UNMET)\s*\|?\s*(?P<why>.*?)\s*\**\s*$",
    re.IGNORECASE,
)

_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "at", "for", "by",
    "with", "from", "is", "are", "was", "were", "be", "been", "what", "which",
    "who", "whom", "whose", "when", "where", "how", "any", "each", "their",
    "its", "this", "that", "these", "those", "does", "do", "did", "say", "says",
})


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOPWORDS}


def _echo_matches(echo: str, eei: str) -> bool:
    """Whether a verdict's echoed element plausibly names the EEI it claims.

    Semantically adjacent criteria make the model's numbering drift: on a live
    Iranian-enrichment run, the verdict numbered 2 ("enrichment levels")
    justified itself against element 1 ("which facilities are operating"), and
    3 justified itself against 2. The echo makes that visible; without it the
    misattribution is silent and lands in `unmet_criteria`.

    Deliberately permissive — one shared content word is enough. The echo is a
    few words against a full question, so demanding more would reject honest
    paraphrase, and a false drift report is worse than a missed one.
    """
    if not echo:
        return True  # no echo offered; nothing to check against
    echo_words = _content_words(echo)
    if not echo_words:
        return True
    return bool(echo_words & _content_words(eei))


def parse_verdicts(narrative: str, eeis: list[str]) -> list[dict]:
    """Read the `N | VERDICT | justification` block back out of the model's reply.

    A verdict the parser misses is indistinguishable from an unassessed
    requirement, so this is deliberately permissive about how the line is
    labelled and strict about its three fields.

    A verdict whose echoed element does not match the element it is numbered
    against is dropped rather than trusted. Those elements then fall through to
    the second pass, which asks about them one at a time and cannot drift.
    """
    out: list[dict] = []
    seen: set[int] = set()
    for line in (narrative or "").split("\n"):
        m = _VERDICT_LINE.match(normalise_line(line))
        if not m:
            continue
        idx = int(m.group("num")) - 1
        if not (0 <= idx < len(eeis)) or idx in seen:
            continue
        echo = (m.group("echo") or "").strip()
        if not _echo_matches(echo, eeis[idx]):
            logger.info(
                "Dropping verdict %d: echoed element %r does not match %r",
                idx + 1, echo[:60], eeis[idx][:60],
            )
            continue
        seen.add(idx)
        justification = (m.group("why") or "").strip().rstrip("*").strip()
        out.append({
            "index": idx,
            "eei": eeis[idx],
            "verdict": m.group("verdict").upper(),
            "justification": justification or "No justification given.",
        })
    return out


def _merge_retry(content: str, eeis: list[str], missing: list[int]) -> list[dict]:
    """Read a second-pass reply, tolerating a model that renumbered the elements.

    The retry lists only the unjudged elements. Models frequently renumber them
    1..N despite being told not to, which through absolute-index parsing gives
    element k the verdict and justification belonging to a different element —
    silently, and in the direction of looking answered. When the reply is exactly
    the renumbered shape, map it positionally onto `missing` instead.
    """
    if not missing:
        return []

    absolute = [a for a in parse_verdicts(content, eeis) if a["index"] in missing]
    seen = {a["index"] for a in absolute}

    # Renumbered shape: exactly one line per missing element, numbered 1..N.
    positional = parse_verdicts(content, [""] * len(missing))
    if len(positional) == len(missing) and {p["index"] for p in positional} == set(range(len(missing))):
        renumbered = [
            {
                "index": missing[p["index"]],
                "eei": eeis[missing[p["index"]]],
                "verdict": p["verdict"],
                "justification": p["justification"],
            }
            for p in positional
        ]
        # Prefer the absolute reading only when it already covers everything —
        # otherwise the renumbered reading is the coherent one.
        if len(absolute) < len(missing):
            return renumbered

    return [a for a in absolute if a["index"] in seen]


@dataclass
class Settlement:
    """The judge's verdicts made complete, and the status they add up to."""

    # Every element in element order: judged, or explicitly UNASSESSED.
    assessments: list[dict]
    satisfied: list[dict]
    unmet: list[dict]
    status: str
    # Whether the model returned any verdict at all.
    any_verdict: bool


def settle(assessments: list[dict], eeis: list[str]) -> Settlement:
    """Fill in the elements the judge was silent on, then decide the status.

    `assessments` is completed in place: an UNASSESSED entry is appended for
    each unjudged element and the list is sorted into element order.
    """
    # An element the model did not return a verdict for has NOT been shown to be
    # answered. Treating silence as success declared a requirement SATISFIED off
    # one verdict out of five, so unjudged elements are made explicit instead.
    # Whether the model returned anything at all — distinct from whether every
    # element got a verdict. A total judging failure must leave the stored status
    # untouched rather than reopening a satisfied requirement.
    any_verdict = bool(assessments)
    judged = {a["index"] for a in assessments}
    for i, eei in enumerate(eeis):
        if i not in judged:
            assessments.append({
                "index": i,
                "eei": eei,
                "verdict": "UNASSESSED",
                "justification": "The judging model returned no verdict for this element.",
            })
    assessments.sort(key=lambda a: a["index"])

    satisfied = [a for a in assessments if a["verdict"] == "SATISFIED"]
    unmet = [a for a in assessments if a["verdict"] != "SATISFIED"]

    if any_verdict and not unmet:
        status = PirStatus.SATISFIED
    elif any(a["verdict"] in ("SATISFIED", "PARTIAL") for a in assessments):
        # A PARTIAL verdict means the collection did answer part of the element.
        # Reporting that as OPEN loses the distinction between "we have something
        # on this" and "we have nothing at all", which is what drives whether the
        # next cycle re-collects or refines.
        status = PirStatus.PARTIAL
    else:
        status = PirStatus.OPEN

    return Settlement(
        assessments=assessments,
        satisfied=satisfied,
        unmet=unmet,
        status=status,
        any_verdict=any_verdict,
    )
