"""Coordinate literacy for GEOINT — parse + convert MGRS / UTM / DMS / decimal.

Recognizes coordinate strings in document text and converts them to decimal
lat/lon (WGS84), so a *stated* coordinate becomes an instantly placeable point
with no gazetteer needed — and GEOINT's native MGRS is first-class. MGRS/UTM
conversion uses ``pygeodesy`` (pure Python, no compiled PROJ dependency).

Only distinctive, high-signal formats are matched (MGRS grid structure, DMS with
°/′, decimal with an N/S–E/W hemisphere) so ordinary number pairs in prose are
not misread as coordinates; every candidate is validated (parses + in range)
before it is returned.
"""
from __future__ import annotations

import re

import pygeodesy as _geo

# MGRS: zone(1–2 digits) + latitude band (C–X, excl I/O) + 100km square (2
# letters, excl I/O) + an even number of easting/northing digits (2–10).
_MGRS_RE = re.compile(r"\b(\d{1,2}[C-HJ-NP-X][A-HJ-NP-Z]{2}(?:\d{2}){1,5})\b")

# Decimal with hemisphere: "38.9N 77.0W", "38.9° N, 77.0° W".
_DECHEM_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*°?\s*([NSns])[ ,]+(\d{1,3}(?:\.\d+)?)\s*°?\s*([EWew])"
)

# DMS: 34°01'12"N 118°15'30"W (seconds optional).
_DMS_RE = re.compile(
    r"(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*([\d.]+)?\s*[\"″]?\s*([NSns])"
    r"[ ,]+(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*([\d.]+)?\s*[\"″]?\s*([EWew])"
)


def _valid(lat: float, lng: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def mgrs_to_latlng(value: str) -> tuple[float, float]:
    ll = _geo.parseMGRS(value).toLatLon()
    return float(ll.lat), float(ll.lon)


def utm_to_latlng(value: str) -> tuple[float, float]:
    ll = _geo.parseUTM5(value).toLatLon()
    return float(ll.lat), float(ll.lon)


def latlng_to_mgrs(lat: float, lng: float) -> str:
    """Decimal lat/lon → MGRS grid reference (via UTM)."""
    return str(_geo.toUtm8(lat, lng).toMgrs())


def _dms_to_decimal(deg: str, minutes: str, seconds: str | None, hemi: str) -> float:
    val = float(deg) + float(minutes) / 60.0 + (float(seconds) if seconds else 0.0) / 3600.0
    return -val if hemi.upper() in ("S", "W") else val


def parse_coordinates(text: str) -> list[dict]:
    """Return [{raw, lat, lng, format}] for coordinate strings found in text.

    Formats: mgrs, dms, decimal (with hemisphere). Deduped by raw string.
    """
    if not text:
        return []
    found: list[dict] = []
    seen: set[str] = set()

    def _add(raw: str, lat: float, lng: float, fmt: str) -> None:
        raw = raw.strip()
        if raw and raw not in seen and _valid(lat, lng):
            seen.add(raw)
            found.append({"raw": raw, "lat": lat, "lng": lng, "format": fmt})

    for m in _MGRS_RE.finditer(text):
        try:
            lat, lng = mgrs_to_latlng(m.group(1))
        except Exception:
            continue
        _add(m.group(1), lat, lng, "mgrs")

    for m in _DMS_RE.finditer(text):
        try:
            lat = _dms_to_decimal(m.group(1), m.group(2), m.group(3), m.group(4))
            lng = _dms_to_decimal(m.group(5), m.group(6), m.group(7), m.group(8))
        except Exception:
            continue
        _add(m.group(0), lat, lng, "dms")

    for m in _DECHEM_RE.finditer(text):
        try:
            lat = float(m.group(1)) * (-1.0 if m.group(2).upper() == "S" else 1.0)
            lng = float(m.group(3)) * (-1.0 if m.group(4).upper() == "W" else 1.0)
        except Exception:
            continue
        _add(m.group(0), lat, lng, "decimal")

    return found
