"""File upload through a collection plan source.

R-13: `await file.read()` buffered the whole upload before the 50 MB check, so
the cap bounded nothing — a 2 GB upload was read into memory to be refused.

Contract 15: the Neo4j driver, spaCy and the graph build are synchronous; run
on the event loop they stalled every request, `/health` included, for the
length of a 10 MB file.
"""
from __future__ import annotations

import io
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from intel_platform.api.routes.collection_plans import uploads as cp


class _CountingIO(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.bytes_read = 0

    def read(self, n=-1):
        chunk = super().read(n)
        self.bytes_read += len(chunk)
        return chunk


def _upload(data: bytes, name="data.csv", size=None):
    raw = _CountingIO(data)
    return UploadFile(file=raw, filename=name, size=size), raw


def _db(plan, source):
    db = MagicMock()

    async def _get(model, pid):
        return {plan.id: plan, source.id: source}.get(pid)

    db.get = _get
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _plan_and_source():
    plan = SimpleNamespace(
        id=uuid.uuid4(), project_id="p1",
        routing_rules={"extract_entities": True, "store_documents": True},
    )
    source = SimpleNamespace(
        id=uuid.uuid4(), plan_id=plan.id, source_type="file_upload", config={},
        last_failure_at=None, last_success_at=None, last_error="",
        acquisition_count=0, total_records_acquired=0,
    )
    return plan, source


class TestTheCapIsEnforcedWhileReading:
    async def test_an_oversized_upload_is_refused_without_reading_it_all(self, monkeypatch):
        monkeypatch.setattr(cp, "_MAX_UPLOAD_BYTES", 1000, raising=False)
        monkeypatch.setattr(cp, "_UPLOAD_CHUNK_BYTES", 256, raising=False)
        plan, source = _plan_and_source()
        upload, raw = _upload(b"a,b\n" * 750)                       # 3000 bytes, size unknown
        with pytest.raises(HTTPException) as err:
            await cp.upload_file_to_source(
                str(plan.id), str(source.id), file=upload, extraction_mode="nlp",
                reliability_rating="C3", db=_db(plan, source), store=MagicMock(),
            )
        assert err.value.status_code == 400
        assert "too large" in err.value.detail.lower()
        assert raw.bytes_read <= 1000 + 256, f"read {raw.bytes_read} bytes to refuse a 1000-byte cap"

    async def test_a_declared_size_over_the_cap_is_refused_before_reading(self, monkeypatch):
        monkeypatch.setattr(cp, "_MAX_UPLOAD_BYTES", 1000, raising=False)
        plan, source = _plan_and_source()
        upload, raw = _upload(b"x" * 3000, size=3000)
        with pytest.raises(HTTPException):
            await cp.upload_file_to_source(
                str(plan.id), str(source.id), file=upload, extraction_mode="nlp",
                reliability_rating="C3", db=_db(plan, source), store=MagicMock(),
            )
        assert raw.bytes_read == 0

    async def test_an_upload_under_the_cap_is_read_whole(self, monkeypatch):
        monkeypatch.setattr(cp, "_UPLOAD_CHUNK_BYTES", 7, raising=False)
        upload, _raw = _upload(b"name,city\nAda,London\nGrace,Arlington\n")
        assert await cp._read_upload_capped(upload, 1000) == b"name,city\nAda,London\nGrace,Arlington\n"


class TestBlockingWorkLeavesTheLoop:
    async def test_store_extraction_and_build_run_in_worker_threads(self, monkeypatch):
        loop_thread = threading.current_thread()
        on_loop: list[str] = []

        def _note(name):
            if threading.current_thread() is loop_thread:
                on_loop.append(name)

        store = MagicMock()
        store.create_entity.side_effect = lambda *_a, **_k: _note("create_entity")

        def _nlp(text, doc_id):
            _note("extract_entities_nlp")
            return [SimpleNamespace(name="Ada")], []

        def _build(*_a, **_k):
            _note("build_graph_from_extractions")
            return {"entities_created": 1, "relationships_created": 0}

        monkeypatch.setattr(cp, "extract_entities_nlp", _nlp)
        monkeypatch.setattr(cp, "build_graph_from_extractions", _build)

        plan, source = _plan_and_source()
        upload, _raw = _upload(b"name,city\nAda,London\n")
        body = await cp.upload_file_to_source(
            str(plan.id), str(source.id), file=upload, extraction_mode="nlp",
            reliability_rating="C3", db=_db(plan, source), store=store,
        )
        assert body["routing_results"]["entities_created"] == 1
        assert on_loop == [], f"ran on the event loop: {on_loop}"

    async def test_the_executor_runs_nlp_extraction_off_the_loop(self, monkeypatch):
        from intel_platform.services import extraction
        from intel_platform.services import plan_executor

        loop_thread = threading.current_thread()
        seen: list[bool] = []

        def _nlp(text, doc_id):
            seen.append(threading.current_thread() is loop_thread)
            return [], []

        monkeypatch.setattr(extraction, "extract_entities_nlp", _nlp)
        await plan_executor._extract("Ada Lovelace met Babbage.", "d1", "nlp")
        assert seen == [False]
