"""XML and GeoJSON ingestion.

`SUPPORTED_FORMATS` was {csv, tsv, xlsx, xls, json, jsonl}, which blocked a
whole class of open sources the collection planner should be able to use:
OFAC SDN, the EU consolidated sanctions list and most government feeds ship
XML, and every open boundary dataset ships GeoJSON.
"""
from __future__ import annotations

import json as _json

import pytest

from intel_platform.connectors.flat_file import (
    detect_format,
    parse_geojson,
    parse_xml,
)

# Shaped like OFAC's SDN list: records one level below the root, behind a
# metadata header, in a namespace, with repeated child elements.
SDN_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sdnList xmlns="http://tempuri.org/sdnList.xsd">
  <publshInformation><Publish_Date>08/09/2026</Publish_Date></publshInformation>
  <sdnEntry>
    <uid>12345</uid><lastName>SHIPPING CO</lastName><sdnType>Entity</sdnType>
    <programList><program>UKRAINE-EO14024</program><program>RUSSIA</program></programList>
  </sdnEntry>
  <sdnEntry>
    <uid>12346</uid><lastName>YI PENG 3</lastName><sdnType>Vessel</sdnType>
    <programList><program>UKRAINE-EO14024</program></programList>
  </sdnEntry>
</sdnList>"""


class TestXmlSafety:
    """defusedxml, not the stdlib parser.

    Verified on this Python (3.12): xml.etree.ElementTree refuses external
    entities but expands internal ones, so a billion-laughs document parses
    and inflates. These are ingest paths fed by uploads and remote fetches.
    """

    def test_billion_laughs_is_refused(self):
        payload = b"""<?xml version="1.0"?>
        <!DOCTYPE lolz [
         <!ENTITY lol "lol">
         <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
         <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
        ]>
        <root>&lol3;</root>"""
        result = parse_xml(payload, {})
        assert result.success is False
        assert "unsafe" in result.error.lower() or "entities" in result.error.lower()

    def test_external_entity_is_refused(self):
        payload = b"""<?xml version="1.0"?>
        <!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
        <root><a>&xxe;</a></root>"""
        assert parse_xml(payload, {}).success is False

    def test_the_error_names_what_went_wrong(self):
        """A hostile file and a truncated one need different responses."""
        result = parse_xml(b"<root><unclosed>", {})
        assert result.success is False
        assert "XML" in result.error


class TestXmlRecords:
    def test_finds_the_repeating_element_past_a_metadata_header(self):
        """The row element is rarely the first child of the root — OFAC puts a
        publication-date block ahead of the entries."""
        result = parse_xml(SDN_XML, {})
        assert result.success is True
        assert result.record_count == 2
        assert result.metadata["record_element"] == "sdnEntry"

    def test_namespaces_are_stripped_from_field_names(self):
        result = parse_xml(SDN_XML, {})
        assert "uid" in result.records[0]
        assert not any("}" in k for k in result.records[0])

    def test_repeated_siblings_are_kept_not_overwritten(self):
        """An entity on two sanctions programmes must not silently keep one."""
        programs = parse_xml(SDN_XML, {}).records[0]["programList.program"]
        assert "UKRAINE-EO14024" in programs
        assert "RUSSIA" in programs

    def test_nested_elements_become_dotted_keys(self):
        assert "programList.program" in parse_xml(SDN_XML, {}).records[0]

    def test_attributes_are_captured(self):
        payload = b'<list><item id="7" type="vessel"><name>Test</name></item></list>'
        rec = parse_xml(payload, {}).records[0]
        assert rec["@id"] == "7"
        assert rec["@type"] == "vessel"

    def test_record_path_overrides_detection(self):
        result = parse_xml(SDN_XML, {"record_path": "program"})
        assert result.record_count == 3

    def test_a_single_record_document_is_not_empty(self):
        result = parse_xml(b"<entry><name>Only one</name></entry>", {})
        assert result.success is True
        assert result.record_count == 1

    def test_profiling_matches_the_other_readers(self):
        """A new format should not produce a thinner result that looks like a
        partial parse."""
        result = parse_xml(SDN_XML, {})
        assert result.schema_info["columns"]
        assert result.profiling["row_count"] == 2
        assert result.preview_rows


class TestGeoJson:
    FEATURES = b"""{"type":"FeatureCollection","features":[
     {"type":"Feature","properties":{"name":"Finland EEZ","sovereign":"Finland"},
      "geometry":{"type":"Polygon","coordinates":[[[19.0,59.0],[26.0,59.0],[26.0,65.0],[19.0,65.0],[19.0,59.0]]]}},
     {"type":"Feature","properties":{"name":"Helsinki"},
      "geometry":{"type":"Point","coordinates":[24.94,60.17]}}
    ]}"""

    def test_one_record_per_feature(self):
        result = parse_geojson(self.FEATURES, {})
        assert result.success is True
        assert result.record_count == 2

    def test_properties_become_columns(self):
        rec = parse_geojson(self.FEATURES, {}).records[0]
        assert rec["name"] == "Finland EEZ"
        assert rec["sovereign"] == "Finland"

    def test_a_polygon_is_reduced_to_a_point_inside_its_own_box(self):
        """The platform stores lat/lng scalars, not geometry. A polygon has to
        arrive as something the map can plot."""
        rec = parse_geojson(self.FEATURES, {}).records[0]
        assert rec["bbox_min_lng"] <= rec["longitude"] <= rec["bbox_max_lng"]
        assert rec["bbox_min_lat"] <= rec["latitude"] <= rec["bbox_max_lat"]

    def test_the_bounding_box_is_preserved(self):
        """So containment can be answered without a spatial index."""
        rec = parse_geojson(self.FEATURES, {}).records[0]
        assert (rec["bbox_min_lng"], rec["bbox_min_lat"]) == (19.0, 59.0)
        assert (rec["bbox_max_lng"], rec["bbox_max_lat"]) == (26.0, 65.0)

    def test_a_derived_point_is_labelled_as_derived(self):
        """geo_source keeps a reduced polygon from reading as a surveyed
        coordinate — the geo view already ranks confidence by source."""
        recs = parse_geojson(self.FEATURES, {}).records
        assert recs[0]["geo_source"] == "geojson"
        assert recs[1]["geo_source"] == "geojson_point"

    def test_a_point_survives_unchanged(self):
        rec = parse_geojson(self.FEATURES, {}).records[1]
        assert (rec["longitude"], rec["latitude"]) == (24.94, 60.17)
        assert rec["vertex_count"] == 1

    @pytest.mark.parametrize("gtype,coords", [
        ("LineString", [[19.0, 59.0], [26.0, 65.0]]),
        ("MultiPoint", [[19.0, 59.0], [26.0, 65.0]]),
        ("MultiPolygon", [[[[19.0, 59.0], [26.0, 59.0], [26.0, 65.0], [19.0, 59.0]]]]),
    ])
    def test_every_geometry_type_reduces(self, gtype, coords):
        payload = _json.dumps({
            "type": "Feature", "properties": {"n": 1},
            "geometry": {"type": gtype, "coordinates": coords},
        }).encode()
        rec = parse_geojson(payload, {}).records[0]
        assert rec["latitude"] is not None
        assert rec["longitude"] is not None
        assert rec["geometry_type"] == gtype

    def test_a_geometrycollection_reduces(self):
        payload = (b'{"type":"Feature","properties":{},"geometry":{"type":"GeometryCollection",'
                   b'"geometries":[{"type":"Point","coordinates":[1.0,2.0]},'
                   b'{"type":"Point","coordinates":[3.0,4.0]}]}}')
        rec = parse_geojson(payload, {}).records[0]
        assert rec["longitude"] == 2.0
        assert rec["latitude"] == 3.0

    def test_a_feature_without_geometry_is_counted_not_dropped(self):
        """All-attributes-no-shapes is a different problem from a parse
        failure, and the caller should be able to tell them apart."""
        payload = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"n":1}}]}'
        result = parse_geojson(payload, {})
        assert result.record_count == 1
        assert result.metadata["features_without_geometry"] == 1

    def test_a_bare_geometry_is_accepted(self):
        result = parse_geojson(b'{"type":"Point","coordinates":[10.0,20.0]}', {})
        assert result.record_count == 1
        assert result.records[0]["latitude"] == 20.0

    def test_non_geojson_is_refused_clearly(self):
        assert parse_geojson(b'{"rows":[1,2,3]}', {}).success is False
        assert parse_geojson(b"not json", {}).success is False


class TestFormatDetection:
    @pytest.mark.parametrize("filename,expected", [
        ("sdn.xml", "xml"),
        ("boundaries.kml", "xml"),
        ("feed.atom", "xml"),
        ("eez.geojson", "geojson"),
        ("data.json", "json"),
        ("rows.csv", "csv"),
    ])
    def test_extensions_map_to_readers(self, filename, expected):
        assert detect_format(filename) == expected

    def test_geojson_is_not_treated_as_plain_json(self):
        """Parsing it as JSON keeps the geometry as an unusable nested blob
        instead of a point the map can plot."""
        assert detect_format("x.geojson") != "json"
