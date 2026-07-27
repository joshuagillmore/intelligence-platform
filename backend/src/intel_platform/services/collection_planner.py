from __future__ import annotations

import re

from intel_platform.services.llm_output import labelled_json

# Recognises a CONFIG line whose JSON does not parse, so the line is still
# consumed rather than being read as the next source in the plan.
_CONFIG_LINE = re.compile(r"^[\s*_`]*CONFIG[\s*_`]*:", re.IGNORECASE)


def _detect_legacy_source_type(desc: str) -> str:
    """Detect a legacy free-form category for `parse_collection_plan`.

    This is the categorization used by the deprecated Neo4j-era
    `/collections/parse-plan` endpoint (see `api/routes/collections.py`), which
    predates and is independent of the `SourceType` enum (`db/models.py`) used
    by the PIR->Plan->Execute connector pipeline. Keep these two taxonomies
    separate: this one is display-only and was never wired to
    `CONNECTOR_REGISTRY`/`SourceType`.
    """
    lower = desc.lower()
    # Check social_media before news since "media" would match news
    if any(kw in lower for kw in ["social media", "twitter", "telegram", "social network"]):
        return "social_media"
    if any(kw in lower for kw in ["news", "article", "media", "press"]):
        return "news"
    if any(kw in lower for kw in ["report", "pdf", "document", "paper"]):
        return "document"
    if any(kw in lower for kw in ["database", "registry", "whois"]):
        return "database"
    return "web_search"


def _detect_source_type(desc: str) -> str:
    """Detect a `SourceType` enum value from description keywords.

    Used by `parse_plan_sources` for the PIR->Plan->Execute pipeline; the
    returned value must be one of the `SourceType` values (`db/models.py`) so
    it can be routed through `CONNECTOR_REGISTRY`.

    Order matters: more specific categories (rss_feed, file_upload) are
    checked before broader ones (web_scrape, database) so that e.g. "RSS news
    feed" doesn't get swallowed by web_scrape's bare "news" keyword, and
    "Upload CSV files from ... databases" doesn't get swallowed by database's
    "database" keyword.
    """
    lower = desc.lower()
    if any(kw in lower for kw in ["rss", "news feed", "syndication", "feed"]):
        return "rss_feed"
    if any(kw in lower for kw in ["upload", "file", "csv", "excel", "spreadsheet", "pdf", "report", "document"]):
        return "file_upload"
    if any(kw in lower for kw in ["scrape", "website", "web page", "crawl", "monitor", "news", "forum", "social"]):
        return "web_scrape"
    if any(kw in lower for kw in ["api", "endpoint", "rest", "json", "data service"]):
        return "api_feed"
    if any(kw in lower for kw in ["database", "registry", "whois", "query", "sql"]):
        return "database"
    return "file_upload"  # default


def parse_collection_plan(llm_response: str) -> list[dict]:
    """Parse an LLM-generated collection plan into structured items."""
    items = []
    lines = llm_response.split('\n')

    current_item = None
    item_id = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect numbered items or bullet points
        numbered = re.match(r'^(\d+)[.)]\s*(.*)', line)
        bulleted = re.match(r'^[-*\u2022]\s*(.*)', line)

        if numbered or bulleted:
            if current_item:
                items.append(current_item)

            item_id += 1
            text = numbered.group(2) if numbered else bulleted.group(1)

            source_type = _detect_legacy_source_type(text)

            current_item = {
                "id": item_id,
                "description": text,
                "source_type": source_type,
                "status": "pending",
                "approved": False,
            }
        elif current_item:
            # Append continuation lines to current item
            current_item["description"] += " " + line

    if current_item:
        items.append(current_item)

    # If no structured items found, create a single item from the whole response
    if not items:
        items.append({
            "id": 1,
            "description": llm_response[:500],
            "source_type": "general",
            "status": "pending",
            "approved": False,
        })

    return items


def parse_plan_sources(plan_text: str) -> list[dict]:
    """Parse LLM-generated plan text into source definitions for collection plans.

    Looks for patterns like:
      1. [file_upload] Description of source
         CONFIG: {"url": "https://..."}
      2. [web_scrape] Description of source
    Falls back to keyword-based source type detection for numbered items and
    bullet points (rejecting anything that reads like prose/analysis).

    Returns list of {source_type, name, config}, max 7 items.
    """

    sources = []
    valid_types = {"file_upload", "web_scrape", "api_feed", "database", "rss_feed"}

    lines = plan_text.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        # Primary: N. [type] description
        m = re.match(r'^\d+[.)]\s*\[(\w+)\]\s*(.+)', line)
        if m:
            stype = m.group(1).lower().strip()
            desc = m.group(2).strip()
            if stype in valid_types and desc:
                # Check if next line has CONFIG
                config = {}
                if i < len(lines):
                    config_line = lines[i].strip()
                    # Emphasis-tolerant: "**CONFIG:** {...}" is as common as the
                    # requested form, and a miss here leaves the source with an
                    # empty config. The agentic RESOLVE phase fills those in at
                    # execution, so this is latent rather than breaking today —
                    # but 28 of 162 stored sources carry an empty config.
                    parsed_config = labelled_json(config_line, "CONFIG")
                    if parsed_config or _CONFIG_LINE.match(config_line):
                        config = parsed_config
                        i += 1
                sources.append({"source_type": stype, "name": desc[:256], "config": config})
                continue

        # Secondary: N. type_name Description (LLM puts type as prefix without brackets)
        m_prefix = re.match(r'^(\d+)[.)]\s*(file_upload|web_scrape|api_feed|database|rss_feed)[:\s]+(.+)', line, re.IGNORECASE)
        if m_prefix:
            stype = m_prefix.group(2).lower().strip()
            desc = m_prefix.group(3).strip()
            if stype in valid_types and 10 < len(desc) < 256:
                sources.append({"source_type": stype, "name": desc, "config": {}})
                continue

        # Tertiary: N. type_name: Description (with colon separator)
        m_colon = re.match(r'^(\d+)[.)]\s*(\w+_\w+):\s*(.+)', line)
        if m_colon:
            stype = m_colon.group(2).lower().strip()
            desc = m_colon.group(3).strip()
            if stype in valid_types and 10 < len(desc) < 256:
                sources.append({"source_type": stype, "name": desc, "config": {}})
                continue

        # Fallback: numbered items or bullet points (prose/analysis text is still
        # rejected below by the length/sentence/markdown checks, not by format)
        m2 = re.match(r'^(?:\d+[.)]|[-*•])\s+(.+)', line)
        if m2:
            desc = m2.group(1).strip()
            # Skip analysis text: too short, too long, or sentence-like
            if len(desc) > 200 or len(desc) < 15:
                continue
            # Skip lines with multiple sentences (prose)
            if desc.count('.') > 2:
                continue
            # Skip lines that start with markdown headers or bold markers
            if desc.startswith('#') or desc.startswith('**'):
                continue

            stype = _detect_source_type(desc)

            # Try to extract a URL from the description for auto-config
            config = {}
            url_m = re.search(r'https?://[^\s\'"<>]+', desc)
            if url_m:
                url = url_m.group(0).rstrip(".,;)")
                if stype == "web_scrape":
                    config = {"url": url}
                elif stype == "rss_feed":
                    config = {"feed_url": url}
                elif stype == "api_feed":
                    config = {"base_url": url}

            # Check next line for CONFIG
            if i < len(lines):
                config_line = lines[i].strip()
                parsed_config = labelled_json(config_line, "CONFIG")
                if parsed_config or _CONFIG_LINE.match(config_line):
                    # An unparseable CONFIG line is still a CONFIG line: consume
                    # it so it is not mistaken for the next source.
                    config = parsed_config or config
                    i += 1

            sources.append({"source_type": stype, "name": desc[:256], "config": config})

    # Hard cap at 7
    return sources[:7]
