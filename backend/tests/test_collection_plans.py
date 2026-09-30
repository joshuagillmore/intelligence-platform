"""Integration tests for collection plan management.

Tests the full workflow:
1. Create collection plans with requirements
2. Add sources to plans
3. Upload files through sources
4. Verify data flows through the pipeline (profiling, catalog, acquisition log)
5. Status lifecycle transitions
6. Security: UUID validation, invalid inputs
"""
from __future__ import annotations

import io
import json
import uuid

import pytest

from intel_platform.connectors.base import get_connector
from intel_platform.connectors.flat_file import parse_csv, parse_excel, parse_json


def _has_fastapi() -> bool:
    try:
        import fastapi
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Collection Plan → Source → Acquire workflow (no DB, connector-level)
# ---------------------------------------------------------------------------

class TestCollectionWorkflow:
    """Tests the collection workflow at the connector level without a database.

    Simulates what the API route does: create plan → add source → acquire data.
    """

    async def test_csv_acquisition_workflow(self):
        """Full workflow: configure → acquire → verify profiling + schema."""
        connector = get_connector("file_upload")

        # Step 1: Configure for CSV
        config = connector.configure({
            "file_format": "csv",
            "filename": "threat_indicators.csv",
        })
        assert config["file_format"] == "csv"

        # Step 2: Acquire (parse) the file
        csv_data = (
            b"indicator,type,confidence,source,first_seen\n"
            b"192.168.1.100,ip,0.95,honeypot,2024-01-15\n"
            b"evil-domain.com,domain,0.87,osint,2024-01-16\n"
            b"d41d8cd98f00b204e9800998ecf8427e,md5,0.99,sandbox,2024-01-17\n"
            b"CVE-2024-1234,vulnerability,0.92,nist,2024-01-18\n"
            b"T1059.001,technique,0.88,mitre,2024-01-19\n"
        )
        result = await connector.acquire({
            **config,
            "file_bytes": csv_data,
        })

        assert result.success
        assert result.record_count == 5

        # Step 3: Verify schema inference
        schema_cols = {c["name"]: c["type"] for c in result.schema_info["columns"]}
        assert schema_cols["indicator"] == "string"
        assert schema_cols["confidence"] == "float"
        assert "first_seen" in schema_cols

        # Step 4: Verify profiling
        assert result.profiling["row_count"] == 5
        assert result.profiling["column_count"] == 5
        conf_profile = result.profiling["columns"]["confidence"]
        assert conf_profile["null_count"] == 0

        # Step 5: Verify preview
        assert len(result.preview_rows) == 5
        assert result.preview_rows[0]["indicator"] == "192.168.1.100"

    async def test_excel_acquisition_workflow(self):
        """Full workflow for Excel ingestion."""
        from openpyxl import Workbook

        # Create a realistic intel Excel file
        wb = Workbook()
        ws = wb.active
        ws.title = "Threat Actors"
        ws.append(["Name", "Country", "Active", "First Seen", "Confidence"])
        ws.append(["Fancy Bear", "Russia", True, "2004-01-01", 0.95])
        ws.append(["Lazarus Group", "North Korea", True, "2007-06-01", 0.92])
        ws.append(["Charming Kitten", "Iran", True, "2011-03-01", 0.88])
        ws.append(["APT41", "China", True, "2012-01-01", 0.91])

        # Add a second sheet
        ws2 = wb.create_sheet("TTPs")
        ws2.append(["TTP ID", "Name", "Actor"])
        ws2.append(["T1566", "Phishing", "Fancy Bear"])
        ws2.append(["T1059", "Command Line", "Lazarus Group"])

        buf = io.BytesIO()
        wb.save(buf)

        connector = get_connector("file_upload")
        config = connector.configure({"file_format": "xlsx"})

        # Acquire from default sheet
        result = await connector.acquire({
            **config,
            "file_bytes": buf.getvalue(),
            "filename": "threat_actors.xlsx",
        })

        assert result.success
        assert result.record_count == 4
        assert result.records[0]["Name"] == "Fancy Bear"
        assert result.records[0]["Active"] is True
        assert result.schema_info["available_sheets"] == ["Threat Actors", "TTPs"]

        # Acquire from second sheet
        result2 = await connector.acquire({
            **config,
            "file_bytes": buf.getvalue(),
            "filename": "threat_actors.xlsx",
            "sheet_name": "TTPs",
        })
        assert result2.success
        assert result2.record_count == 2
        assert result2.records[0]["TTP ID"] == "T1566"

    async def test_json_api_response_workflow(self):
        """Simulate ingesting a JSON API response with nested records."""
        api_response = json.dumps({
            "status": "success",
            "count": 3,
            "results": [
                {"ioc": "malware.exe", "type": "file", "severity": "high", "tags": ["ransomware"]},
                {"ioc": "evil.com", "type": "domain", "severity": "medium", "tags": ["phishing"]},
                {"ioc": "10.0.0.1", "type": "ip", "severity": "low", "tags": ["scanner"]},
            ]
        }).encode()

        connector = get_connector("file_upload")
        result = await connector.acquire({
            "file_bytes": api_response,
            "filename": "api_response.json",
            "file_format": "json",
            "records_path": "results",
        })

        assert result.success
        assert result.record_count == 3
        assert result.records[0]["ioc"] == "malware.exe"
        assert result.records[0]["tags"] == ["ransomware"]

    async def test_jsonl_feed_workflow(self):
        """Simulate ingesting a JSONL log feed."""
        feed_data = (
            b'{"timestamp": "2024-01-15T10:00:00Z", "src_ip": "192.168.1.1", "dst_ip": "10.0.0.1", "action": "BLOCK"}\n'
            b'{"timestamp": "2024-01-15T10:00:01Z", "src_ip": "192.168.1.2", "dst_ip": "10.0.0.2", "action": "ALLOW"}\n'
            b'{"timestamp": "2024-01-15T10:00:02Z", "src_ip": "192.168.1.3", "dst_ip": "10.0.0.3", "action": "BLOCK"}\n'
        )

        connector = get_connector("file_upload")
        result = await connector.acquire({
            "file_bytes": feed_data,
            "filename": "firewall.jsonl",
        })

        assert result.success
        assert result.record_count == 3
        assert result.records[0]["action"] == "BLOCK"

    async def test_multi_source_plan(self):
        """Simulate a collection plan with multiple sources providing different data."""
        connector = get_connector("file_upload")

        # Source 1: CSV of IOCs (explicitly set has_header)
        ioc_result = await connector.acquire({
            "file_bytes": b"ioc,type\n192.168.1.1,ip\nevil.com,domain",
            "filename": "iocs.csv",
            "has_header": True,
        })

        # Source 2: Excel of threat actors
        xlsx_data = _make_xlsx_helper([
            ["Actor", "Country"],
            ["APT29", "Russia"],
            ["APT38", "DPRK"],
        ])
        actor_result = await connector.acquire({
            "file_bytes": xlsx_data,
            "filename": "actors.xlsx",
        })

        # Source 3: JSON of vulnerabilities
        vuln_result = await connector.acquire({
            "file_bytes": json.dumps([
                {"cve": "CVE-2024-0001", "cvss": 9.8},
                {"cve": "CVE-2024-0002", "cvss": 7.2},
            ]).encode(),
            "filename": "vulns.json",
        })

        # All sources should succeed
        assert ioc_result.success and ioc_result.record_count == 2
        assert actor_result.success and actor_result.record_count == 2
        assert vuln_result.success and vuln_result.record_count == 2

        # Total records across all sources
        total = ioc_result.record_count + actor_result.record_count + vuln_result.record_count
        assert total == 6


def _make_xlsx_helper(rows: list[list]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Status Lifecycle Tests
# ---------------------------------------------------------------------------

class _PlanDb:
    """Async session stand-in holding one plan."""

    def __init__(self, plan):
        self.plan = plan
        self.commits = 0

    async def get(self, _model, pid):
        return self.plan if pid == self.plan.id else None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        pass


def _lifecycle_plan(status):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid.uuid4(), project_id="p1", name="plan", description="", requirement="",
        pir="", pir_id=None, refined_pir="", status=status, routing_rules={},
        created_by="t", assigned_to="", schedule_cron="", next_run_at=None,
        created_at=None, updated_at=None, sources=[],
    )


async def _transition(endpoint: str, status: str):
    """Call a transition endpoint on a plan in `status`: (new status, HTTP code)."""
    from fastapi import HTTPException

    from intel_platform.api.routes import collection_plans as cp

    plan = _lifecycle_plan(status)
    try:
        body = await getattr(cp, f"{endpoint}_plan")(str(plan.id), db=_PlanDb(plan))
    except HTTPException as err:
        return plan.status, err.status_code
    return body["status"], 200


class TestStatusLifecycle:
    """The lifecycle the transition endpoints and PUT actually enforce.

    This class held one test asserting `PlanStatus.DRAFT in ("DRAFT",
    PlanStatus.DRAFT)` — true by construction, of any code. It now drives the
    endpoints.
    """

    @pytest.mark.parametrize("endpoint,start,expected", [
        ("activate", "DRAFT", ("ACTIVE", 200)),
        ("activate", "PAUSED", ("ACTIVE", 200)),
        ("activate", "ACTIVE", ("ACTIVE", 400)),
        ("activate", "ARCHIVED", ("ARCHIVED", 400)),
        ("pause", "ACTIVE", ("PAUSED", 200)),
        ("pause", "DRAFT", ("DRAFT", 400)),
        ("complete", "ACTIVE", ("COMPLETED", 200)),
        ("complete", "ARCHIVED", ("ARCHIVED", 400)),   # completing must not un-archive
        ("archive", "ACTIVE", ("ARCHIVED", 200)),
        ("archive", "COMPLETED", ("ARCHIVED", 200)),
    ])
    async def test_valid_transitions(self, endpoint, start, expected):
        assert await _transition(endpoint, start) == expected

    async def _put(self, start, **fields):
        from fastapi import HTTPException

        from intel_platform.api.routes import collection_plans as cp

        plan = _lifecycle_plan(start)
        try:
            body = await cp.update_plan(str(plan.id), cp.UpdatePlanRequest(**fields), db=_PlanDb(plan))
        except HTTPException as err:
            return plan.status, err.status_code
        return body["status"], 200

    async def test_put_rejects_an_unknown_status(self):
        """Any string used to be stored: the column is String(20)."""
        assert await self._put("DRAFT", status="SHIPPED") == ("DRAFT", 400)

    async def test_put_cannot_revive_an_archived_plan(self):
        assert await self._put("ARCHIVED", status="ACTIVE") == ("ARCHIVED", 409)

    async def test_put_can_still_edit_an_archived_plans_text(self):
        assert (await self._put("ARCHIVED", description="note"))[1] == 200

    async def test_put_accepts_a_known_status(self):
        assert await self._put("DRAFT", status="PAUSED") == ("PAUSED", 200)

    @pytest.mark.parametrize("field,size", [
        ("name", 257), ("assigned_to", 129), ("schedule_cron", 129), ("status", 21),
    ])
    def test_overlong_fields_are_a_validation_error_not_a_500(self, field, size):
        from pydantic import ValidationError

        from intel_platform.api.routes.collection_plans import CreatePlanRequest, UpdatePlanRequest

        with pytest.raises(ValidationError):
            UpdatePlanRequest(**{field: "x" * size})
        with pytest.raises(ValidationError):
            CreatePlanRequest(**{"project_id": "p", "name": "n", field: "x" * size})


# ---------------------------------------------------------------------------
# Security: Input Validation
# ---------------------------------------------------------------------------

class TestSecurityValidation:
    @pytest.mark.skipif(
        not _has_fastapi(), reason="FastAPI not installed in test environment"
    )
    def test_invalid_uuid_format(self):
        """UUID parsing should reject invalid formats."""
        from intel_platform.api.routes.collection_plans import _parse_uuid
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _parse_uuid("not-a-uuid", "test_id")
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPException):
            _parse_uuid("", "test_id")

        with pytest.raises(HTTPException):
            _parse_uuid("12345", "test_id")

    @pytest.mark.skipif(
        not _has_fastapi(), reason="FastAPI not installed in test environment"
    )
    def test_valid_uuid_accepted(self):
        from intel_platform.api.routes.collection_plans import _parse_uuid

        test_id = str(uuid.uuid4())
        result = _parse_uuid(test_id, "test_id")
        assert str(result) == test_id

    def test_sql_injection_in_project_id(self):
        """SQLAlchemy parameterized queries should prevent SQL injection.
        This test verifies the connector doesn't execute arbitrary strings."""
        connector = get_connector("file_upload")
        # Even if someone passes SQL in the config, the connector just
        # validates file format parameters — it never executes SQL
        config = connector.configure({
            "file_format": "csv",
            "filename": "'; DROP TABLE users; --",
        })
        assert config["filename"] == "'; DROP TABLE users; --"
        # The filename is sanitized at the API level, not the connector level

    async def test_path_traversal_in_filename(self):
        """Path traversal in filename should not affect parsing."""
        connector = get_connector("file_upload")
        result = await connector.acquire({
            "file_bytes": b"a,b\n1,2",
            "filename": "../../../etc/passwd.csv",
        })
        assert result.success
        # File bytes are parsed in-memory; filename is just metadata


# ---------------------------------------------------------------------------
# Data Provenance
# ---------------------------------------------------------------------------

class TestDataProvenance:
    """Test that every record carries provenance information."""

    def test_csv_row_numbers(self):
        data = b"name,value\nA,1\nB,2\nC,3"
        result = parse_csv(data, {})
        for i, record in enumerate(result.records, 1):
            assert record["_row_number"] == i

    def test_json_row_numbers(self):
        data = json.dumps([{"a": 1}, {"a": 2}, {"a": 3}]).encode()
        result = parse_json(data, {})
        for i, record in enumerate(result.records, 1):
            assert record["_row_number"] == i

    def test_jsonl_line_numbers(self):
        data = b'{"a": 1}\n{"a": 2}\n{"a": 3}'
        result = parse_json(data, {"jsonl": True})
        assert result.records[0]["_row_number"] == 1
        assert result.records[1]["_row_number"] == 2
        assert result.records[2]["_row_number"] == 3

    async def test_metadata_format_tracking(self):
        connector = get_connector("file_upload")

        csv_result = await connector.acquire({
            "file_bytes": b"a\n1",
            "filename": "test.csv",
        })
        assert csv_result.metadata["format"] == "csv"

        json_result = await connector.acquire({
            "file_bytes": b'[{"a": 1}]',
            "filename": "test.json",
        })
        assert json_result.metadata["format"] == "json"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_column_csv(self):
        data = b"name\nAlice\nBob"
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 2

    def test_single_row_csv(self):
        data = b"name,age\nAlice,30"
        result = parse_csv(data, {})
        assert result.success
        assert result.record_count == 1

    def test_csv_with_empty_cells(self):
        data = b"a,b,c\n1,,3\n,2,\n,,"
        result = parse_csv(data, {"has_header": True})
        assert result.success
        assert result.record_count == 3

    def test_json_with_null_values(self):
        data = json.dumps([
            {"name": "test", "value": None},
            {"name": None, "value": 42},
        ]).encode()
        result = parse_json(data, {})
        assert result.success
        assert result.records[0]["value"] is None

    def test_json_with_nested_objects(self):
        """Nested objects should be preserved as-is in records."""
        data = json.dumps([{
            "name": "test",
            "metadata": {"key": "value", "nested": True},
        }]).encode()
        result = parse_json(data, {})
        assert result.success
        assert isinstance(result.records[0]["metadata"], dict)

    def test_excel_with_none_header(self):
        """Excel sheets with None in header positions."""
        data = _make_xlsx_helper([[None, "Name", None], [1, "Alice", 3]])
        result = parse_excel(data, {})
        assert result.success
        headers = [c["name"] for c in result.schema_info["columns"]]
        assert "column_0" in headers  # None headers get default names
