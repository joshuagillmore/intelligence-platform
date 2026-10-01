"""Evidence passages: the text around each mention of a name in a document.

One implementation for every reader that quotes a stored document back at the
analyst — the per-document evidence route and the per-entity evidence chain —
so a passage is cut the same way wherever it is shown.
"""
from __future__ import annotations

import re

# Characters kept on each side of a mention.
CONTEXT_CHARS = 200


def find_passages(content: str, needle: str, limit: int, *, ignore_case: bool = False) -> tuple[list[dict], int]:
    """Up to `limit` passages around `needle` in `content`, and how many mentions exist.

    Each passage is `{"text", "offset"}`: the mention with `CONTEXT_CHARS` of
    context on each side, an ellipsis where it was cut, and the mention's
    character offset in `content`. Mentions are counted without overlap, so
    the passages and the total describe the same set. A blank needle finds
    nothing — it matched at every index, so one request against a 10 MB
    document built about ten million passages.
    """
    content = content or ""
    if not needle or not needle.strip():
        return [], 0
    # A regex rather than lower() on both sides: lowering can change a
    # string's length ("İ" becomes two characters), and the offsets must
    # index the original text.
    pattern = re.compile(re.escape(needle), re.IGNORECASE if ignore_case else 0)
    passages: list[dict] = []
    total = 0
    for match in pattern.finditer(content):
        total += 1
        if len(passages) >= limit:
            continue
        idx = match.start()
        context_start = max(0, idx - CONTEXT_CHARS)
        context_end = min(len(content), match.end() + CONTEXT_CHARS)
        text = content[context_start:context_end]
        if context_start > 0:
            text = "..." + text
        if context_end < len(content):
            text = text + "..."
        passages.append({"text": text, "offset": idx})
    return passages, total
