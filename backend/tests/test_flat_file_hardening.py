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
