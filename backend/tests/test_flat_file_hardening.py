"""Uploads that are small on the wire and enormous in memory, or quietly misread.

These complement test_flat_file_connector.py with the cases the 2026-09-30
review found: each one is a file the parser accepted and then either exhausted
memory on or turned into a plausible-looking wrong answer.
"""
from __future__ import annotations

import io
import re
import threading
import zipfile

from intel_platform.connectors import flat_file
from intel_platform.connectors.flat_file import FlatFileConnector, parse_excel


def _xlsx(rows: list[list], *, cells: dict[tuple[int, int], object] | None = None) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    for (r, c), value in (cells or {}).items():
        ws.cell(row=r, column=c, value=value)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _declare_dimension(raw: bytes, ref: str) -> bytes:
    """Rewrite the sheet's <dimension ref> — the file states it, nothing checks it."""
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = re.sub(rb'<dimension ref="[^"]*"\s*/>', f'<dimension ref="{ref}"/>'.encode(), data)
            dst.writestr(item, data)
    return out.getvalue()


class TestExcelDeclaredDimensions:
    """Read-only openpyxl pads every row to the dimension the file *declares*.

    A ~1.5 KB workbook declaring A1:XFD1048576 made each row a 16,384-wide list
    before any limit was checked: 100k one-cell rows allocated ~13 GB on the
    event loop.
    """

    def test_declared_dimension_does_not_size_the_rows(self):
        rows = [["name", "lat", "lng"]] + [[f"site {i}", 1.0 * i, 2.0 * i] for i in range(40)]
        raw = _declare_dimension(_xlsx(rows), "A1:XFD1048576")

        result = parse_excel(raw, {})

        assert result.success, result.error
        assert result.record_count == 40
        assert result.profiling["column_count"] == 3

    def test_a_genuinely_wide_row_is_refused_where_it_occurs(self):
        raw = _xlsx([["a", "b"], ["1", "2"]], cells={(3, flat_file.MAX_COLUMNS + 500): "x"})
        result = parse_excel(raw, {})
        assert not result.success
        assert "Row 3" in result.error

    def test_sparse_rows_cannot_multiply_into_a_huge_table(self, monkeypatch):
        """A wide header over many one-cell rows is small on the wire and
        rows x columns in memory once records are built."""
        monkeypatch.setattr(flat_file, "MAX_CELLS", 1_000)
        header = [f"c{i}" for i in range(50)]
        raw = _xlsx([header] + [["v"] for _ in range(30)])

        result = parse_excel(raw, {})
        assert not result.success
        assert "cells" in result.error


class TestJsonIsNotMistakenForJsonl:
    """Any text starting with "{" that contained a newline was read as JSONL, so
    a pretty-printed object failed on every line — and was reported as a
    successful upload of zero records."""

    PRETTY = b'{\n  "source": "registry",\n  "records": [\n    {"name": "A", "lat": -33.9},\n' \
             b'    {"name": "B", "lat": 51.5}\n  ]\n}\n'

    def test_pretty_printed_object_with_records(self):
        result = flat_file.parse_json(self.PRETTY, {})
        assert result.success
        assert result.record_count == 2

    def test_pretty_printed_flat_object(self):
        result = flat_file.parse_json(b'{\n  "name": "Fordow",\n  "country": "Iran"\n}', {})
        assert result.success and result.record_count == 1

    def test_real_jsonl_still_reads_as_jsonl(self):
        result = flat_file.parse_json(b'{"a": 1}\n{"a": 2}\n{"a": 3}\n', {})
        assert result.record_count == 3

    def test_jsonl_where_every_line_fails_is_a_failure(self):
        result = flat_file.parse_json(b"{not json\n{also not\n", {"jsonl": True})
        assert not result.success
        assert "line" in result.error.lower()

    def test_skipped_jsonl_lines_are_counted(self):
        result = flat_file.parse_json(b'{"a": 1}\n{broken\n{"a": 3}\n', {"jsonl": True})
        assert result.success and result.record_count == 2
        assert result.metadata.get("lines_skipped") == 1

    async def test_pretty_json_named_jsonl_is_still_read(self):
        result = await FlatFileConnector().acquire({"file_bytes": self.PRETTY, "filename": "export.jsonl"})
        assert result.success and result.record_count == 2


class TestNumbersAreNotFormulas:
    """Formula-injection quoting prefixed every value starting with "-" or "+",
    so a negative coordinate became the text "'-33.87" and every
    southern-hemisphere or western location was lost."""

    def test_negative_coordinates_survive_csv(self):
        result = flat_file.parse_csv(b"name,lat,lng\nSydney,-33.87,151.21\nLima,-12.05,-77.04\n", {})
        assert [r["lat"] for r in result.records] == ["-33.87", "-12.05"]
        assert result.records[1]["lng"] == "-77.04"

    def test_negative_coordinates_survive_json(self):
        result = flat_file.parse_json(b'[{"name": "Lima", "lat": "-12.05", "note": "=HYPERLINK(1)"}]', {})
        assert result.records[0]["lat"] == "-12.05"
        assert result.records[0]["note"].startswith("'"), "a real formula is still neutralised"

    def test_formulas_are_still_quoted(self):
        for value in ("-1+1", "=1+1", "+cmd|' /C calc'!A0", "-2+3", "@SUM(A1)"):
            assert flat_file._sanitize_cell(value).startswith("'"), value

    def test_signed_numbers_are_left_alone(self):
        for value in ("-33.87", "+44", "-1e5", " -7 "):
            assert flat_file._sanitize_cell(value) == value, value


class TestParseErrorsDoNotLeakInternals:
    """An upload's error went back to the API client as raw exception text."""

    async def test_an_unexpected_parser_error_is_described_not_quoted(self, monkeypatch):
        def boom(raw, config):
            raise RuntimeError("cannot open /srv/app/.cache/tmp-9f2c: permission denied")

        monkeypatch.setattr(flat_file, "parse_csv", boom)
        result = await FlatFileConnector().acquire({"file_bytes": b"a,b\n", "file_format": "csv"})

        assert not result.success
        assert "/srv/app" not in result.error
        assert "RuntimeError" in result.error

    def test_an_invalid_workbook_names_the_problem_not_the_library_message(self):
        result = parse_excel(b"definitely not a zip archive", {})
        assert not result.success
        assert result.error.startswith("Invalid Excel file")
        assert "is not a zip file" not in result.error, "the library's own message reached the client"


class TestParsingLeavesTheEventLoop:
    async def test_acquire_parses_in_a_worker_thread(self, monkeypatch):
        seen = {}
        original = flat_file.parse_csv

        def spy(raw, config):
            seen["thread"] = threading.current_thread()
            return original(raw, config)

        monkeypatch.setattr(flat_file, "parse_csv", spy)
        result = await FlatFileConnector().acquire({"file_bytes": b"a,b\n1,2\n", "file_format": "csv"})

        assert result.success
        assert seen["thread"] is not threading.main_thread(), "parsing a large upload blocks every request"
