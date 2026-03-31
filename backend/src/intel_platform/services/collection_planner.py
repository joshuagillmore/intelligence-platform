from __future__ import annotations
import re


def _detect_source_type(desc: str) -> str:
    """Detect source type from description keywords."""
    lower = desc.lower()
    if any(kw in lower for kw in ["scrape", "website", "web page", "crawl", "monitor", "news", "forum", "social"]):
        return "web_scrape"
    if any(kw in lower for kw in ["rss", "news feed", "syndication", "feed"]):
        return "rss_feed"
    if any(kw in lower for kw in ["api", "endpoint", "rest", "json", "data service"]):
        return "api_feed"
    if any(kw in lower for kw in ["database", "registry", "whois", "query", "sql"]):
        return "database"
    if any(kw in lower for kw in ["upload", "file", "csv", "excel", "spreadsheet", "pdf", "report", "document"]):
        return "file_upload"
    return "web_scrape"  # default to web_scrape, not file_upload


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

            source_type = _detect_source_type(text)

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
      2. [web_scrape] Description of source
    Falls back to keyword-based source type detection for numbered items only.

    Returns list of {source_type, name}, max 7 items.
    """
    sources = []
    valid_types = {"file_upload", "web_scrape", "api_feed", "database", "rss_feed"}

    for line in plan_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Primary: N. [type] description
        m = re.match(r'^\d+[.)]\s*\[(\w+)\]\s*(.+)', line)
        if m:
            stype = m.group(1).lower().strip()
            desc = m.group(2).strip()
            if stype in valid_types and 10 < len(desc) < 256:
                sources.append({"source_type": stype, "name": desc})
                continue

        # Secondary: N. type_name Description (LLM puts type as prefix without brackets)
        m_prefix = re.match(r'^(\d+)[.)]\s*(file_upload|web_scrape|api_feed|database|rss_feed)[:\s]+(.+)', line, re.IGNORECASE)
        if m_prefix:
            stype = m_prefix.group(2).lower().strip()
            desc = m_prefix.group(3).strip()
            if stype in valid_types and 10 < len(desc) < 256:
                sources.append({"source_type": stype, "name": desc})
                continue

        # Tertiary: N. type_name: Description (with colon separator)
        m_colon = re.match(r'^(\d+)[.)]\s*(\w+_\w+):\s*(.+)', line)
        if m_colon:
            stype = m_colon.group(2).lower().strip()
            desc = m_colon.group(3).strip()
            if stype in valid_types and 10 < len(desc) < 256:
                sources.append({"source_type": stype, "name": desc})
                continue

        # Fallback: only proper numbered items (not bullets/dashes which pick up analysis)
        m2 = re.match(r'^(\d+)[.)]\s+(.+)', line)
        if m2:
            desc = m2.group(2).strip()
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
            sources.append({"source_type": stype, "name": desc[:256]})

    # Hard cap at 7
    return sources[:7]
