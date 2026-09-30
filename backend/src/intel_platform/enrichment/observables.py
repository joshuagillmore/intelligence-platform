"""Observable normalization: refang/defang + type classification.

Threat-intel text routinely *defangs* indicators so they can't be clicked or
auto-resolved — ``evil[.]com``, ``hxxps://``, ``a[at]b[.]com``. The platform's
regex extractors need literal values, so :func:`refang` reverses that notation
before extraction. :func:`defang` is the inverse (for safe display), and
:func:`classify_observable` maps a lone value to its entity type.

Pure functions, no I/O — safe to import from ``services.extraction`` without
pulling in the rest of the enrichment subsystem.
"""
from __future__ import annotations

import re

# --- refang / defang --------------------------------------------------------

# hxxp / hXXp / HXXP -> http (the trailing "s" of hxxps survives -> https).
_HXXP_RE = re.compile(r"h[x]{2}p", re.IGNORECASE)
# A bracketed symbol is unambiguous wherever it appears:  [.]  (.)  {.}  [@]
_DOT_SYMBOL_RE = re.compile(r"[\[\(\{]\s*\.\s*[\]\)\}]")
_AT_SYMBOL_RE = re.compile(r"[\[\(\{]\s*@\s*[\]\)\}]")
# A bracketed *word* is only a marker inside a token — "evil(dot)com",
# "user[at]host" — never between words: "Department of Transportation (DOT)
# issued" and "Austria (AT)" are prose, and this runs over whole documents.
_DOT_WORD_RE = re.compile(r"(?<=[A-Za-z0-9])[\[\(\{]\s*dot\s*[\]\)\}](?=[A-Za-z0-9])", re.IGNORECASE)
_AT_WORD_RE = re.compile(r"(?<=[A-Za-z0-9])[\[\(\{]\s*at\s*[\]\)\}](?=[A-Za-z0-9])", re.IGNORECASE)
# Bracketed colon:  [:]  (:)  — covers [://] via the colon plus surviving //.
_COLON_RE = re.compile(r"[\[\(\{]\s*:\s*[\]\)\}]")


def refang(text: str) -> str:
    """Reverse common defang notation so real IOC values are recoverable.

    Only well-known markers are touched (``[.]``, ``hxxp``, ``[@]``, ``[:]``
    anywhere; ``(dot)``/``[at]`` only inside a token), so ordinary prose such
    as "(DOT)" or "Austria (AT)" is left intact.
    """
    if not text:
        return text
    text = _HXXP_RE.sub("http", text)
    text = _DOT_SYMBOL_RE.sub(".", text)
    text = _DOT_WORD_RE.sub(".", text)
    text = _AT_SYMBOL_RE.sub("@", text)
    text = _AT_WORD_RE.sub("@", text)
    text = _COLON_RE.sub(":", text)
    return text


def defang(text: str) -> str:
    """Defang an indicator for safe display. Inverse of :func:`refang`."""
    if not text:
        return text
    text = text.replace("http", "hxxp")
    text = text.replace(".", "[.]")
    text = text.replace("@", "[at]")
    return text


# --- classification ---------------------------------------------------------

_IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_DOMAIN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_HASH_RE = re.compile(r"^(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$")


_CVE_ID_STRICT = re.compile(r"^CVE-\d{4}-\d{4,}$")


def cve_id(value: str) -> str:
    """``value`` as a canonical (upper-case) CVE id, or ``""`` if it is not one.

    KEV and NVD are keyed by CVE id, so anything else ("Log4Shell", "N/A") must
    not be looked up as if it were one.
    """
    v = refang(value or "").strip().upper()
    return v if _CVE_ID_STRICT.match(v) else ""


def _valid_ip(value: str) -> bool:
    return all(o.isdigit() and 0 <= int(o) <= 255 for o in value.split("."))


def classify_observable(value: str) -> str:
    """Return the entity type for a lone observable value, or "" if unknown.

    Refangs first, so ``evil[.]com`` classifies as ``Domain``. Order is
    URL → EmailAddress → IPAddress → Vulnerability → Hash → Domain.
    """
    if not value:
        return ""
    v = refang(value.strip())
    if _URL_RE.match(v):
        return "URL"
    if _EMAIL_RE.match(v):
        return "EmailAddress"
    if _IP_RE.match(v):
        return "IPAddress" if _valid_ip(v) else ""
    if _CVE_RE.match(v):
        return "Vulnerability"
    if _HASH_RE.match(v):
        return "Hash"
    if _DOMAIN_RE.match(v):
        return "Domain"
    return ""
