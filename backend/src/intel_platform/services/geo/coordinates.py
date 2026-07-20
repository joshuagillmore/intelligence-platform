"""Coordinate literacy for GEOINT — parse + convert MGRS / DMS / decimal.

Recognizes coordinate strings in document text and converts them to decimal
lat/lon (WGS84), so a *stated* coordinate becomes an instantly placeable point
with no gazetteer needed — and GEOINT's native MGRS is first-class. MGRS
conversion uses ``pygeodesy`` (pure Python, no compiled PROJ dependency).

False positives are the real risk on the ingest path: an MGRS grid is
structurally indistinguishable from many part numbers / build ids, and range
validation can't tell them apart (any valid grid is in-range by construction).
So MGRS (and a symbol-less decimal pair) are only accepted when a coordinate
keyword sits nearby — mirroring the extractor's hash-context gate. DMS and
decimal-with-degree/fraction are distinctive enough to stand alone.
"""
from __future__ import annotations

import re

import pygeodesy as _geo

# MGRS: zone(1–2 digits) + latitude band (C–X, excl I/O) + 100km square (2
# letters, excl I/O) + an even number of easting/northing digits (2–10).
_MGRS_RE = re.compile(r"\b(\d{1,2}[C-HJ-NP-X][A-HJ-NP-Z]{2}(?:\d{2}){1,5})\b")

# Decimal with hemisphere: "38.9N 77.0W", "38.9° N, 77.0° W". Whitespace is
# bounded (no unbounded \s* around an optional — that backtracks quadratically).
_DECHEM_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)[ ]{0,3}°?[ ]{0,3}([NSns])[ ,]{1,3}(\d{1,3}(?:\.\d+)?)[ ]{0,3}°?[ ]{0,3}([EWew])"
)

# DMS: 34°01'12"N 118°15'30"W (seconds optional). Requires °/′, so distinctive.
_DMS_RE = re.compile(
    r"(\d{1,3})[ ]{0,2}°[ ]{0,2}(\d{1,2})[ ]{0,2}['′][ ]{0,2}([\d.]+)?[ ]{0,2}[\"″]?[ ]{0,2}([NSns])"
    r"[ ,]{1,3}(\d{1,3})[ ]{0,2}°[ ]{0,2}(\d{1,2})[ ]{0,2}['′][ ]{0,2}([\d.]+)?[ ]{0,2}[\"″]?[ ]{0,2}([EWew])"
)

# Coordinate keywords that qualify an ambiguous match as a real coordinate.
_CONTEXT_RE = re.compile(
    r"\b(grid|coord|coordinate|coordinates|mgrs|utm|position|located|location|"
    r"lat|lon|long|latitude|longitude|geo|geolocat)\w*",
    re.IGNORECASE,
)


def _valid(lat: float, lng: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def _has_context(text: str, start: int, end: int, window: int = 45) -> bool:
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    return bool(_CONTEXT_RE.search(text[lo:hi]))


def mgrs_to_latlng(value: str) -> tuple[float, float]:
    ll = _geo.parseMGRS(value).toLatLon()
    return float(ll.lat), float(ll.lon)


def latlng_to_mgrs(lat: float, lng: float) -> str:
    """Decimal lat/lon → MGRS grid reference (via UTM)."""
    return str(_geo.toUtm8(lat, lng).toMgrs())


def _dms_to_decimal(deg: str, minutes: str, seconds: str | None, hemi: str) -> float:
    val = float(deg) + float(minutes) / 60.0 + (float(seconds) if seconds else 0.0) / 3600.0
    return -val if hemi.upper() in ("S", "W") else val


def parse_coordinates(text: str, require_context: bool = True) -> list[dict]:
    """Return [{raw, lat, lng, format}] for coordinate strings found in text.

    Formats: mgrs, dms, decimal (with hemisphere). Deduped by raw string, and
    the dedup/keyword checks run BEFORE the (relatively costly) pygeodesy
    conversion so cost scales with unique tokens, not occurrences.
    ``require_context=False`` accepts a bare MGRS / symbol-less decimal (for an
    explicit "parse this coordinate" call where the whole input is the value).
    """
    if not text:
        return []
    found: list[dict] = []
    seen: set[str] = set()

    def _add(raw: str, lat: float, lng: float, fmt: str) -> None:
        if _valid(lat, lng):
            seen.add(raw)
            found.append({"raw": raw, "lat": lat, "lng": lng, "format": fmt})

    # MGRS — high false-positive surface (part numbers, build ids). Dedup +
    # context gate before conversion.
    for m in _MGRS_RE.finditer(text):
        raw = m.group(1)
        if raw in seen:
            continue
        if require_context and not _has_context(text, m.start(), m.end()):
            continue
        try:
            lat, lng = mgrs_to_latlng(raw)
        except Exception:
            continue
        _add(raw, lat, lng, "mgrs")

    # DMS — distinctive; stands alone.
    for m in _DMS_RE.finditer(text):
        raw = m.group(0).strip()
        if raw in seen:
            continue
        try:
            lat = _dms_to_decimal(m.group(1), m.group(2), m.group(3), m.group(4))
            lng = _dms_to_decimal(m.group(5), m.group(6), m.group(7), m.group(8))
        except Exception:
            continue
        _add(raw, lat, lng, "dms")

    # Decimal with hemisphere — accept only with a degree symbol, a decimal
    # fraction, or nearby context, so "10N 20E" (a measurement) isn't a coord.
    for m in _DECHEM_RE.finditer(text):
        raw = m.group(0).strip()
        if raw in seen:
            continue
        has_signal = ("°" in raw) or ("." in m.group(1)) or ("." in m.group(3))
        if not has_signal and require_context and not _has_context(text, m.start(), m.end()):
            continue
        try:
            lat = float(m.group(1)) * (-1.0 if m.group(2).upper() == "S" else 1.0)
            lng = float(m.group(3)) * (-1.0 if m.group(4).upper() == "W" else 1.0)
        except Exception:
            continue
        _add(raw, lat, lng, "decimal")

    return found
