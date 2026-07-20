"""Enrichment providers.

Importing this package registers every provider (each module calls
``@register_provider`` at import time). Anything that needs the providers
available — the enrichment router, the auto-enrich hook — imports this package
so the registry is populated.
"""
from intel_platform.enrichment.providers import (  # noqa: F401
    certs,
    dns,
    geoip,
    kev,
    nvd,
    rdap,
)
