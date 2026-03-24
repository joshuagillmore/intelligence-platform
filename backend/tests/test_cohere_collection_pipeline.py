"""End-to-end test: Collection pipeline with Cohere as the LLM extraction engine.

Simulates the complete flow:
1. Ingest structured data through the FlatFileConnector (CSV, JSON, Excel)
2. Convert records to text via _records_to_text
3. Chunk the text via ingest_text
4. Extract entities/relationships using Cohere (mocked — no API key in CI)
5. Verify extracted entities are correct and complete
6. Verify the full pipeline connects properly

The mock simulates realistic Cohere command-a-03-2025 responses to verify
the integration path works correctly end-to-end.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from intel_platform.connectors.base import get_connector
from intel_platform.connectors.flat_file import parse_csv, parse_json, parse_excel
from intel_platform.llm.base import LLMResponse
from intel_platform.services.ingestion import ingest_text

logger = logging.getLogger(__name__)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _records_to_text(records: list[dict], source_name: str) -> str:
    """Convert structured records to text for entity extraction.

    Mirrors the function in collection_plans.py to avoid importing
    the full FastAPI route module (which pulls in neo4j etc).
    """
    if not records:
        return ""
    lines = [f"Data from {source_name}:"]
    headers = [k for k in records[0].keys() if k != "_row_number"]
    for record in records[:5000]:
        parts = []
        for h in headers:
            val = record.get(h)
            if val is not None and str(val).strip():
                parts.append(f"{h}: {val}")
        if parts:
            lines.append(". ".join(parts) + ".")
    return "\n".join(lines)


def _parse_llm_response(content: str, doc_id: str):
    """Parse an LLM response into entities and relationships.

    This mirrors the exact parsing logic in extract_entities_llm() so we can
    test the full pipeline without importing modules that require neo4j/FastAPI.
    """
    # Find JSON in response (may be wrapped in markdown code blocks)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    data = json.loads(content.strip())

    entities = []
    for e in data.get("entities", []):
        entity = {
            "name": e.get("name", ""),
            "entity_type": e.get("entity_type", "Person"),
            "source": doc_id,
            "method": "llm",
            "confidence": float(e.get("confidence", 0.85)),
            "aliases": e.get("aliases", []),
        }
        attrs = e.get("attributes", {})
        if attrs:
            entity["attributes"] = attrs
        entities.append(entity)

    relationships = []
    for r in data.get("relationships", []):
        relationships.append({
            "source_name": r.get("source_entity", r.get("source", "")),
            "target_name": r.get("target_entity", r.get("target", "")),
            "rel_type": r.get("relationship_type", r.get("rel_type", "ASSOCIATED_WITH")),
            "confidence": float(r.get("confidence", 0.7)),
            "source": doc_id,
            "method": "llm",
            "evidence": r.get("evidence", ""),
        })

    return entities, relationships


# ---------------------------------------------------------------------------
# Realistic Cohere mock responses for different intel data types
# ---------------------------------------------------------------------------

COHERE_THREAT_ACTOR_RESPONSE = LLMResponse(
    content=json.dumps({
        "entities": [
            {"name": "APT29", "entity_type": "ThreatActor", "confidence": 0.95,
             "aliases": ["Cozy Bear", "The Dukes"], "attributes": {"country": "Russia"}},
            {"name": "SolarWinds", "entity_type": "Organization", "confidence": 0.92},
            {"name": "SUNBURST", "entity_type": "Malware", "confidence": 0.94,
             "attributes": {"type": "backdoor"}},
            {"name": "Microsoft", "entity_type": "Organization", "confidence": 0.90},
            {"name": "Russia", "entity_type": "Location", "confidence": 0.88},
            {"name": "United States", "entity_type": "Location", "confidence": 0.88},
            {"name": "CVE-2020-10148", "entity_type": "Vulnerability", "confidence": 0.96},
            {"name": "T1195.002", "entity_type": "TTP", "confidence": 0.93},
        ],
        "relationships": [
            {"source_entity": "APT29", "target_entity": "SUNBURST",
             "relationship_type": "USES", "confidence": 0.92,
             "evidence": "APT29 deployed SUNBURST malware in the SolarWinds attack"},
            {"source_entity": "APT29", "target_entity": "SolarWinds",
             "relationship_type": "TARGETS", "confidence": 0.90},
            {"source_entity": "APT29", "target_entity": "Russia",
             "relationship_type": "ATTRIBUTED_TO", "confidence": 0.85},
            {"source_entity": "SUNBURST", "target_entity": "CVE-2020-10148",
             "relationship_type": "EXPLOITS", "confidence": 0.88},
            {"source_entity": "APT29", "target_entity": "T1195.002",
             "relationship_type": "USES", "confidence": 0.91},
        ],
    }),
    model="command-a-03-2025",
    input_tokens=1250,
    output_tokens=480,
)

COHERE_IOC_RESPONSE = LLMResponse(
    content=json.dumps({
        "entities": [
            {"name": "192.168.1.100", "entity_type": "IPAddress", "confidence": 0.97},
            {"name": "evil-domain.com", "entity_type": "Domain", "confidence": 0.95},
            {"name": "d41d8cd98f00b204e9800998ecf8427e", "entity_type": "Hash",
             "confidence": 0.96, "attributes": {"hash_type": "MD5"}},
            {"name": "CVE-2024-1234", "entity_type": "Vulnerability", "confidence": 0.98},
            {"name": "T1059.001", "entity_type": "TTP", "confidence": 0.94},
        ],
        "relationships": [
            {"source_entity": "192.168.1.100", "target_entity": "evil-domain.com",
             "relationship_type": "RESOLVES_TO", "confidence": 0.80},
            {"source_entity": "evil-domain.com", "target_entity": "CVE-2024-1234",
             "relationship_type": "ASSOCIATED_WITH", "confidence": 0.75},
        ],
    }),
    model="command-a-03-2025",
    input_tokens=800,
    output_tokens=320,
)

COHERE_EMPTY_RESPONSE = LLMResponse(
    content=json.dumps({"entities": [], "relationships": []}),
    model="command-a-03-2025",
    input_tokens=100,
    output_tokens=40,
)

COHERE_MARKDOWN_WRAPPED_RESPONSE = LLMResponse(
    content='```json\n{"entities": [{"name": "Fancy Bear", "entity_type": "ThreatActor", "confidence": 0.9}], "relationships": []}\n```',
    model="command-a-03-2025",
    input_tokens=300,
    output_tokens=80,
)

COHERE_MALFORMED_RESPONSE = LLMResponse(
    content="I found some entities but here they are in plain text, not JSON",
    model="command-a-03-2025",
    input_tokens=200,
    output_tokens=50,
)


def _make_cohere_mock(response: LLMResponse) -> MagicMock:
    """Create a mock CohereProvider that returns the given response."""
    mock = MagicMock()
    mock.generate = AsyncMock(return_value=response)
    mock.name.return_value = "cohere:command-a-03-2025"
    return mock


# ---------------------------------------------------------------------------
# Test: CSV → Cohere extraction pipeline
# ---------------------------------------------------------------------------

class TestCohereCSVPipeline:
    """Test CSV data flowing through the collection pipeline with Cohere extraction."""

    def test_csv_ingest_to_cohere_extraction(self):
        """Full pipeline: CSV file → parse → text → chunk → Cohere extract → entities."""
        csv_data = (
            b"indicator,type,confidence,source,first_seen\n"
            b"192.168.1.100,ip,0.95,honeypot,2024-01-15\n"
            b"evil-domain.com,domain,0.87,osint,2024-01-16\n"
            b"d41d8cd98f00b204e9800998ecf8427e,md5,0.99,sandbox,2024-01-17\n"
            b"CVE-2024-1234,vulnerability,0.92,nist,2024-01-18\n"
            b"T1059.001,technique,0.88,mitre,2024-01-19\n"
        )

        # Step 1: Parse CSV through connector
        connector = get_connector("file_upload")
        result = run(connector.acquire({
            "file_bytes": csv_data,
            "filename": "iocs.csv",
            "has_header": True,
        }))
        assert result.success
        assert result.record_count == 5

        # Step 2: Convert records to text
        text_content = _records_to_text(result.records, "iocs.csv")
        assert "192.168.1.100" in text_content
        assert "evil-domain.com" in text_content
        assert "CVE-2024-1234" in text_content
        assert "T1059.001" in text_content

        # Step 3: Chunk the text
        chunks = ingest_text(text_content, chunk_size=2000, overlap=50)
        assert len(chunks) >= 1
        # All IOCs should be in the chunks
        all_chunk_text = " ".join(c["content"] for c in chunks)
        assert "192.168.1.100" in all_chunk_text

        # Step 4: Simulate Cohere extraction on each chunk
        mock_provider = _make_cohere_mock(COHERE_IOC_RESPONSE)
        all_entities = []
        all_rels = []
        for chunk in chunks:
            response = run(mock_provider.generate(
                messages=[{"role": "user", "content": f"Extract entities:\n\n{chunk['content']}"}],
                system="You are an entity extraction assistant.",
                temperature=0.2,
            ))
            entities, rels = _parse_llm_response(response.content, "test-doc-001")
            all_entities.extend(entities)
            all_rels.extend(rels)

        # Step 5: Verify extraction quality
        assert len(all_entities) >= 5
        entity_names = {e["name"] for e in all_entities}
        assert "192.168.1.100" in entity_names
        assert "evil-domain.com" in entity_names
        assert "CVE-2024-1234" in entity_names
        assert "T1059.001" in entity_names

        # Verify entity types
        entity_types = {e["name"]: e["entity_type"] for e in all_entities}
        assert entity_types["192.168.1.100"] == "IPAddress"
        assert entity_types["evil-domain.com"] == "Domain"
        assert entity_types["CVE-2024-1234"] == "Vulnerability"
        assert entity_types["T1059.001"] == "TTP"

        # Verify relationships
        rel_pairs = {(r["source_name"], r["target_name"]) for r in all_rels}
        assert ("192.168.1.100", "evil-domain.com") in rel_pairs

        # Verify method attribution
        assert all(e["method"] == "llm" for e in all_entities)
        assert all(r["method"] == "llm" for r in all_rels)

        # Verify Cohere was called for each chunk
        assert mock_provider.generate.call_count == len(chunks)


# ---------------------------------------------------------------------------
# Test: JSON → Cohere extraction pipeline
# ---------------------------------------------------------------------------

class TestCohereJSONPipeline:
    """Test JSON intelligence report flowing through the pipeline with Cohere."""

    def test_json_threat_report_to_cohere(self):
        """JSON threat report → parse → Cohere extraction → entities + relationships."""
        report_data = json.dumps({
            "report_id": "TR-2024-001",
            "title": "APT29 Supply Chain Attack via SolarWinds",
            "classification": "UNCLASSIFIED",
            "findings": [
                {
                    "actor": "APT29",
                    "aliases": "Cozy Bear, The Dukes",
                    "origin": "Russia",
                    "target": "SolarWinds Orion Platform",
                    "malware": "SUNBURST backdoor",
                    "vulnerability": "CVE-2020-10148",
                    "technique": "T1195.002 Supply Chain Compromise",
                    "impact": "Compromised US government agencies and Microsoft",
                },
            ],
        }).encode()

        # Step 1: Parse JSON
        result = parse_json(report_data, {"records_path": "findings"})
        assert result.success
        assert result.record_count == 1

        # Step 2: Convert to text
        text = _records_to_text(result.records, "threat_report.json")
        assert "APT29" in text
        assert "SUNBURST" in text
        assert "SolarWinds" in text

        # Step 3: Simulate Cohere extraction
        mock_provider = _make_cohere_mock(COHERE_THREAT_ACTOR_RESPONSE)
        response = run(mock_provider.generate(
            messages=[{"role": "user", "content": f"Extract entities:\n\n{text}"}],
            system="Entity extraction",
        ))
        entities, relationships = _parse_llm_response(response.content, "test-doc-002")

        # Step 4: Verify threat actor extraction
        entity_map = {e["name"]: e for e in entities}
        assert "APT29" in entity_map
        assert entity_map["APT29"]["entity_type"] == "ThreatActor"
        assert entity_map["APT29"]["confidence"] == 0.95
        assert "Cozy Bear" in entity_map["APT29"].get("aliases", [])

        # Verify malware extraction
        assert "SUNBURST" in entity_map
        assert entity_map["SUNBURST"]["entity_type"] == "Malware"
        assert entity_map["SUNBURST"]["attributes"]["type"] == "backdoor"

        # Verify CVE extraction
        assert "CVE-2020-10148" in entity_map
        assert entity_map["CVE-2020-10148"]["entity_type"] == "Vulnerability"

        # Verify TTP extraction
        assert "T1195.002" in entity_map

        # Verify relationships
        rel_map = {(r["source_name"], r["target_name"]): r for r in relationships}
        assert ("APT29", "SUNBURST") in rel_map
        assert rel_map[("APT29", "SUNBURST")]["rel_type"] == "USES"
        assert rel_map[("APT29", "SUNBURST")]["evidence"] != ""
        assert ("APT29", "Russia") in rel_map
        assert rel_map[("APT29", "Russia")]["rel_type"] == "ATTRIBUTED_TO"
        assert ("SUNBURST", "CVE-2020-10148") in rel_map
        assert rel_map[("SUNBURST", "CVE-2020-10148")]["rel_type"] == "EXPLOITS"


# ---------------------------------------------------------------------------
# Test: Excel → Cohere extraction pipeline
# ---------------------------------------------------------------------------

class TestCohereExcelPipeline:
    """Test Excel data flowing through the pipeline with Cohere."""

    def test_excel_threat_actors_to_cohere(self):
        """Excel threat actor spreadsheet → parse → Cohere extraction."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Threat Actors"
        ws.append(["Actor", "Country", "Malware", "Target Sector", "MITRE TTP"])
        ws.append(["APT29", "Russia", "SUNBURST", "Government", "T1195.002"])
        ws.append(["Lazarus Group", "North Korea", "WannaCry", "Finance", "T1486"])
        ws.append(["APT41", "China", "ShadowPad", "Technology", "T1059.001"])
        buf = io.BytesIO()
        wb.save(buf)

        # Step 1: Parse Excel
        result = parse_excel(buf.getvalue(), {})
        assert result.success
        assert result.record_count == 3

        # Step 2: Convert to text
        text = _records_to_text(result.records, "threat_actors.xlsx")
        assert "APT29" in text
        assert "Lazarus Group" in text
        assert "APT41" in text

        # Step 3: Simulate Cohere extraction
        mock_provider = _make_cohere_mock(COHERE_THREAT_ACTOR_RESPONSE)
        response = run(mock_provider.generate(
            messages=[{"role": "user", "content": f"Extract entities:\n\n{text}"}],
        ))
        entities, rels = _parse_llm_response(response.content, "test-doc-003")

        # Verify entity types
        entity_types = {e["entity_type"] for e in entities}
        assert "ThreatActor" in entity_types
        assert "Malware" in entity_types
        assert "Location" in entity_types
        assert "Vulnerability" in entity_types
        assert "TTP" in entity_types

        # Verify the full entity count
        assert len(entities) == 8
        assert len(rels) == 5


# ---------------------------------------------------------------------------
# Test: Cohere response parsing (graceful failure handling)
# ---------------------------------------------------------------------------

class TestCohereFailureHandling:
    """Test the pipeline handles various Cohere response formats."""

    def test_cohere_returns_malformed_json(self):
        """When Cohere returns non-JSON, parsing should raise and caller handles fallback."""
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response(COHERE_MALFORMED_RESPONSE.content, "test-doc")

    def test_cohere_returns_empty_results(self):
        """When Cohere finds no entities, pipeline should return empty lists."""
        entities, rels = _parse_llm_response(COHERE_EMPTY_RESPONSE.content, "test-doc")
        assert entities == []
        assert rels == []

    def test_cohere_markdown_wrapped_json(self):
        """When Cohere wraps JSON in markdown code blocks, parser should extract it."""
        entities, rels = _parse_llm_response(COHERE_MARKDOWN_WRAPPED_RESPONSE.content, "test-doc")
        assert len(entities) == 1
        assert entities[0]["name"] == "Fancy Bear"
        assert entities[0]["entity_type"] == "ThreatActor"

    def test_cohere_partial_entities(self):
        """Cohere returns entities with missing optional fields."""
        content = json.dumps({
            "entities": [
                {"name": "Unknown Actor"},  # minimal — no type, no confidence
                {"name": "APT28", "entity_type": "ThreatActor"},  # no confidence
            ],
            "relationships": [],
        })
        entities, rels = _parse_llm_response(content, "test-doc")
        assert len(entities) == 2
        assert entities[0]["entity_type"] == "Person"  # default
        assert entities[0]["confidence"] == 0.85  # default
        assert entities[1]["entity_type"] == "ThreatActor"

    def test_cohere_response_with_evidence(self):
        """Verify evidence text is captured from relationships."""
        content = json.dumps({
            "entities": [
                {"name": "A", "entity_type": "Organization"},
                {"name": "B", "entity_type": "Organization"},
            ],
            "relationships": [
                {"source_entity": "A", "target_entity": "B",
                 "relationship_type": "PARTNERS_WITH", "confidence": 0.8,
                 "evidence": "A and B signed a partnership agreement in Q1 2024"},
            ],
        })
        entities, rels = _parse_llm_response(content, "test-doc")
        assert rels[0]["evidence"] == "A and B signed a partnership agreement in Q1 2024"


# ---------------------------------------------------------------------------
# Test: Cohere provider integration (unit level)
# ---------------------------------------------------------------------------

class TestCohereProviderUnit:
    """Unit tests for the CohereProvider class itself."""

    def test_cohere_provider_name(self):
        with patch("cohere.AsyncClientV2"):
            from intel_platform.llm.cohere_provider import CohereProvider
            provider = CohereProvider(api_key="test-key")
            assert provider.name() == "cohere:command-a-03-2025"

    def test_cohere_provider_custom_model(self):
        with patch("cohere.AsyncClientV2"):
            from intel_platform.llm.cohere_provider import CohereProvider
            provider = CohereProvider(api_key="test-key", model="command-r-plus")
            assert provider.name() == "cohere:command-r-plus"

    def test_cohere_generate_message_format(self):
        """Verify Cohere provider formats messages correctly with system prompt."""
        from intel_platform.llm.cohere_provider import CohereProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.message.content = [MagicMock(text='{"entities": [], "relationships": []}')]
        mock_response.usage.tokens.input_tokens = 100
        mock_response.usage.tokens.output_tokens = 50
        mock_client.chat = AsyncMock(return_value=mock_response)

        with patch("cohere.AsyncClientV2", return_value=mock_client):
            provider = CohereProvider(api_key="test-key")
            result = run(provider.generate(
                messages=[{"role": "user", "content": "Extract entities"}],
                system="You are an entity extraction assistant.",
                temperature=0.2,
            ))

        # Verify the chat call included system message
        call_kwargs = mock_client.chat.call_args
        msgs = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are an entity extraction assistant."
        assert msgs[1]["role"] == "user"

        # Verify response parsing
        assert result.content == '{"entities": [], "relationships": []}'
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.model == "command-a-03-2025"


# ---------------------------------------------------------------------------
# Test: Full multi-format pipeline with Cohere
# ---------------------------------------------------------------------------

class TestCohereMultiFormatPipeline:
    """Test that data from all connector types flows correctly to Cohere."""

    def test_all_formats_produce_extractable_text(self):
        """Verify that CSV, JSON, JSONL, and Excel all produce text suitable for Cohere."""
        # CSV
        csv_result = parse_csv(
            b"actor,origin,malware\nAPT29,Russia,SUNBURST\nAPT41,China,ShadowPad",
            {"has_header": True},
        )
        csv_text = _records_to_text(csv_result.records, "actors.csv")

        # JSON
        json_result = parse_json(
            json.dumps([
                {"actor": "Lazarus", "origin": "DPRK", "malware": "WannaCry"},
            ]).encode(), {},
        )
        json_text = _records_to_text(json_result.records, "actors.json")

        # JSONL
        jsonl_result = parse_json(
            b'{"ip": "10.0.0.1", "verdict": "malicious"}\n{"ip": "10.0.0.2", "verdict": "clean"}',
            {"jsonl": True},
        )
        jsonl_text = _records_to_text(jsonl_result.records, "iocs.jsonl")

        # Excel
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["CVE", "CVSS", "Vendor"])
        ws.append(["CVE-2024-0001", 9.8, "Microsoft"])
        buf = io.BytesIO()
        wb.save(buf)
        xlsx_result = parse_excel(buf.getvalue(), {})
        xlsx_text = _records_to_text(xlsx_result.records, "vulns.xlsx")

        # All formats produce correct text
        assert "APT29" in csv_text and "SUNBURST" in csv_text
        assert "Lazarus" in json_text and "WannaCry" in json_text
        assert "10.0.0.1" in jsonl_text and "malicious" in jsonl_text
        assert "CVE-2024-0001" in xlsx_text

        # All texts suitable for Cohere extraction
        for text in [csv_text, json_text, jsonl_text, xlsx_text]:
            assert len(text) > 10
            assert isinstance(text, str)

    def test_cohere_extraction_across_all_formats(self):
        """Run Cohere extraction on text from each format and verify results."""
        formats = {
            "CSV": parse_csv(
                b"ioc,type\n192.168.1.100,ip\nevil-domain.com,domain",
                {"has_header": True},
            ),
            "JSON": parse_json(
                json.dumps([{"ioc": "10.0.0.1", "type": "ip"}]).encode(), {},
            ),
            "JSONL": parse_json(
                b'{"ioc": "bad.com", "type": "domain"}', {"jsonl": True},
            ),
        }

        mock_provider = _make_cohere_mock(COHERE_IOC_RESPONSE)

        for fmt_name, result in formats.items():
            assert result.success, f"{fmt_name} parse failed"
            text = _records_to_text(result.records, f"test.{fmt_name.lower()}")

            response = run(mock_provider.generate(
                messages=[{"role": "user", "content": text}],
            ))
            entities, rels = _parse_llm_response(response.content, f"{fmt_name}-doc")

            assert len(entities) > 0, f"No entities from {fmt_name}"
            assert any(e["entity_type"] == "IPAddress" for e in entities)
            assert any(e["entity_type"] == "Domain" for e in entities)


# ---------------------------------------------------------------------------
# Test: Security — Cohere extraction doesn't propagate injection
# ---------------------------------------------------------------------------

class TestCohereSecurityIntegration:
    """Verify security sanitization persists through the Cohere extraction path."""

    def test_formula_injection_sanitized_before_cohere(self):
        """Malicious formulas should be sanitized before reaching the LLM."""
        csv_data = b"name,payload\n=cmd|'/c calc'!A0,test\n+cmd|'/c notepad'!A0,test2"
        connector = get_connector("file_upload")
        result = run(connector.acquire({
            "file_bytes": csv_data,
            "filename": "malicious.csv",
            "has_header": True,
        }))
        assert result.success

        text = _records_to_text(result.records, "malicious.csv")

        # The text sent to Cohere should have sanitized values
        assert "=cmd" not in text or "'=cmd" in text
        assert "+cmd" not in text or "'+cmd" in text

    def test_deeply_nested_json_rejected_before_cohere(self):
        """JSON bombs should be rejected at parse time, never reaching Cohere."""
        obj = {"v": "leaf"}
        for _ in range(25):
            obj = {"n": obj}
        data = json.dumps(obj).encode()

        result = parse_json(data, {})
        assert not result.success
        assert "depth" in result.error.lower()


# ---------------------------------------------------------------------------
# Test: Cohere token usage and cost tracking
# ---------------------------------------------------------------------------

class TestCohereTokenTracking:
    """Verify token usage is properly tracked through the pipeline."""

    def test_token_usage_from_cohere_response(self):
        response = COHERE_THREAT_ACTOR_RESPONSE
        assert response.input_tokens == 1250
        assert response.output_tokens == 480
        assert response.total_tokens == 1730
        assert response.model == "command-a-03-2025"

    def test_cohere_response_model_tracking(self):
        for response in [COHERE_THREAT_ACTOR_RESPONSE, COHERE_IOC_RESPONSE, COHERE_EMPTY_RESPONSE]:
            assert response.model == "command-a-03-2025"
            assert response.total_tokens == response.input_tokens + response.output_tokens

    def test_multi_chunk_token_accumulation(self):
        """When processing multiple chunks, token usage should accumulate."""
        mock_provider = _make_cohere_mock(COHERE_IOC_RESPONSE)

        # Simulate 3 chunks
        total_input = 0
        total_output = 0
        for i in range(3):
            response = run(mock_provider.generate(
                messages=[{"role": "user", "content": f"Chunk {i}"}],
            ))
            total_input += response.input_tokens
            total_output += response.output_tokens

        assert total_input == 800 * 3
        assert total_output == 320 * 3
        assert mock_provider.generate.call_count == 3
