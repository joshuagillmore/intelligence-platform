"""Is a fetched page real content, or chrome wearing a 200?

Crawlers succeed on captcha walls, cookie interstitials, login pages and empty
shells. Those pages are worse than useless: extraction produces entities that
look entirely real — a live crawl of an institute's login page contributed its
conference calendar to the graph as six intelligence "events" — and each one
spends a source from the collection budget that a real page could have had.

One place holds that judgement so the crawler (before storing) and anything
prompting a model (before spending context) agree on what counts as content.
Each rejection carries a reason, because a page dropped without explanation is
indistinguishable from a page that was never found.
"""
from __future__ import annotations

import re

# Login and paywall pages: judged on the URL path first, since these are the
# most reliable signal, then on the phrases such pages actually use.
_AUTH_WALL_PATH = re.compile(
    r"/(?:login|signin|sign-in|register|subscribe|paywall|account/login)(?:[/?#]|$)",
    re.IGNORECASE,
)

_AUTH_WALL_PHRASES = (
    "sign in to continue", "subscribe to read", "subscribe to continue",
    "log in to read", "login to continue", "this content is for subscribers",
    "create an account to read", "you have reached your article limit",
    "please sign in to access", "members only",
)

# Anti-bot interstitials. These return 200 with a body that is entirely
# challenge furniture, and plain headless Chromium trips them constantly.
_BLOCK_MARKERS = (
    "checking your browser", "just a moment", "recaptcha", "captcha",
    "are you a robot", "are you human", "access denied", "403 forbidden",
    "attention required", "verify you are human", "bot verification",
    "enable javascript to continue", "please enable cookies",
    "ddos protection", "cloudflare ray id",
)

# Only the head of the document is searched, so an article *about* paywalls or
# captchas is not discarded for describing one.
_HEAD_CHARS = 1500

# Below this a page carries nothing usable even though it loaded. Deliberately
# low: a short but real news item should survive, a shell should not.
MIN_CONTENT_WORDS = 60

# An interstitial is, by construction, a page with almost nothing on it. A
# thousand-word article that happens to mention captchas is not one, and
# rejecting it on the keyword alone would silently discard exactly the
# reporting a cyber requirement is most likely to want. So a marker condemns a
# page only when it appears in the title, or when the page is also too thin to
# be an article in its own right.
_INTERSTITIAL_MAX_WORDS = 200


def word_count(content: str) -> int:
    return len((content or "").split())


def rejection_reason(
    url: str, content: str, title: str = "", min_words: int = MIN_CONTENT_WORDS,
) -> str:
    """Why this page is not usable content, or "" when it is.

    Returning the reason rather than a bool is the point: it goes into the
    collection activity trail, so an analyst can tell "the site blocked us"
    from "there was nothing there".
    """
    if url and _AUTH_WALL_PATH.search(url):
        return "login or paywall page"

    head = (content or "")[:_HEAD_CHARS].lower()
    title_lower = (title or "").strip().lower()

    for phrase in _AUTH_WALL_PHRASES:
        if phrase in head:
            return f"paywalled content ({phrase})"

    count = word_count(content)
    for marker in _BLOCK_MARKERS:
        if marker in title_lower:
            return f"anti-bot or interstitial page ({marker})"
        if marker in head and count < _INTERSTITIAL_MAX_WORDS:
            return f"anti-bot or interstitial page ({marker})"

    if count < min_words:
        return f"only {count} words of content"

    return ""


def is_usable(
    url: str, content: str, title: str = "", min_words: int = MIN_CONTENT_WORDS,
) -> bool:
    return not rejection_reason(url, content, title, min_words)


def is_auth_wall(url: str, content: str) -> bool:
    """Login and paywall pages specifically, ignoring the other rejections."""
    reason = rejection_reason(url, content, min_words=0)
    return reason.startswith("login or paywall") or reason.startswith("paywalled")
