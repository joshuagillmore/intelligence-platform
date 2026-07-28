"""Off-topic documents are screened before extraction, not after.

Measured: a South China Sea requirement collected "Map of Moscow with street
names and house numbers — Yandex Maps". It consumed the source budget, ran 27
chunks of extraction, and contributed 925 entities of street names. A source
that succeeds off-topic costs more than one that fails — the failure is at
least visible.

The gate fails open by design: losing real collection because a screen could not
run is worse than the noise it exists to stop.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from intel_platform.collection.agentic import _is_relevant

PIR = "Which Chinese maritime militia vessels operated near Second Thomas Shoal?"
BODY = "Long document body. " * 40


def _provider(reply: str):
    p = MagicMock()
    p.generate = AsyncMock(return_value=SimpleNamespace(content=reply))
    return p


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestVerdicts:
    def test_offtopic_is_discarded(self):
        assert _run(_is_relevant(BODY, PIR, "Map of Moscow", _provider("OFFTOPIC"))) is False

    def test_relevant_is_kept(self):
        assert _run(_is_relevant(BODY, PIR, "AMTI tracker", _provider("RELEVANT"))) is True

    def test_verdict_with_surrounding_text(self):
        assert _run(_is_relevant(BODY, PIR, "x", _provider("**OFFTOPIC** — a street map"))) is False
        assert _run(_is_relevant(BODY, PIR, "x", _provider("RELEVANT.\n"))) is True


class TestFailsOpen:
    def test_provider_error_keeps_the_document(self):
        p = MagicMock()
        p.generate = AsyncMock(side_effect=RuntimeError("provider down"))
        assert _run(_is_relevant(BODY, PIR, "x", p)) is True

    def test_unrecognised_reply_keeps_the_document(self):
        for reply in ("", "maybe", "I am not sure", "42"):
            assert _run(_is_relevant(BODY, PIR, "x", _provider(reply))) is True, reply

    def test_short_documents_skip_the_screen(self):
        """Too little text to judge; the doc cap and cleaner handle these."""
        p = _provider("OFFTOPIC")
        assert _run(_is_relevant("tiny", PIR, "x", p)) is True
        p.generate.assert_not_called()
