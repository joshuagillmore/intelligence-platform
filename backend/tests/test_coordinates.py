"""Tests for coordinate parsing/conversion (G3: MGRS/UTM/DMS/decimal)."""
from intel_platform.services.geo.coordinates import (
    latlng_to_mgrs,
    mgrs_to_latlng,
    parse_coordinates,
)


def test_parse_mgrs():
    coords = parse_coordinates("Target grid 38SMB4483 confirmed at dawn.")
    assert len(coords) == 1
    assert coords[0]["format"] == "mgrs"
    assert 33.0 < coords[0]["lat"] < 34.0 and 44.0 < coords[0]["lng"] < 45.0


def test_parse_decimal_with_hemisphere():
    coords = parse_coordinates("Vehicle last seen at 34.05N, 118.25W.")
    dec = [c for c in coords if c["format"] == "decimal"]
    assert dec and round(dec[0]["lat"], 2) == 34.05 and round(dec[0]["lng"], 2) == -118.25


def test_parse_dms():
    coords = parse_coordinates("The site at 34°01'12\"N 118°15'00\"W was struck.")
    dms = [c for c in coords if c["format"] == "dms"]
    assert dms and round(dms[0]["lat"], 3) == 34.020 and round(dms[0]["lng"], 2) == -118.25


def test_mgrs_roundtrip():
    lat, lng = mgrs_to_latlng("38SMB4483")
    back = latlng_to_mgrs(lat, lng).replace(" ", "")
    assert back.startswith("38S")  # same zone/band


def test_plain_number_pairs_are_not_coordinates():
    # No hemisphere / degree / grid structure -> not a coordinate.
    assert parse_coordinates("A ratio of 38.9 to 77 and a count of 12ab34.") == []


def test_mgrs_requires_context():
    # A bare MGRS-shaped token (part number / build id) with no coordinate
    # keyword nearby must NOT be extracted (avoids junk Location nodes)...
    assert parse_coordinates("Shipped serial 38SMB4483 today.") == []
    # ...but an explicit parse (whole input is the value) accepts it.
    coords = parse_coordinates("38SMB4483", require_context=False)
    assert coords and coords[0]["format"] == "mgrs"


def test_symbol_less_pair_needs_signal_or_context():
    # "10N 20E" with no degree/fraction/context reads as a measurement.
    assert parse_coordinates("The bracket takes 10N 20E of load.") == []
    # With a coordinate keyword nearby it is accepted.
    assert parse_coordinates("Coordinates 10N 20E were reported.")


def test_null_island_coordinate_parses():
    coords = parse_coordinates("Grid position 0N 10E on the line.")
    assert any(round(c["lat"], 1) == 0.0 for c in coords)


def test_empty():
    assert parse_coordinates("") == []
