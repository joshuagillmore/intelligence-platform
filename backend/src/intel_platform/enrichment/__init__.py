"""Cyber enrichment subsystem.

Pulls related cyber data (WHOIS/RDAP, DNS, GeoIP, cert transparency, CISA KEV,
NVD) for observables the platform already models, and normalizes defanged
threat-intel notation.

Phase 1 ships only ``observables`` (refang/defang/classify) — a dependency-free
helper reused by extraction. Later phases add the provider registry, cache, and
service; when they land, this ``__init__`` imports the providers package so the
registry populates on import (mirroring ``collection/connectors``). Keep this
module import-light until then so ``services.extraction`` can import
``observables`` without pulling in httpx/db.
"""
