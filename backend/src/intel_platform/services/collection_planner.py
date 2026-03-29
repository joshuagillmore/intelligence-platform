from __future__ import annotations
import re


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

            # Try to extract source type and search terms
            # Check social_media before news since "media" would match news
            source_type = "web_search"
            lower_text = text.lower()
            if any(kw in lower_text for kw in ["social media", "twitter", "telegram", "social network"]):
                source_type = "social_media"
            elif any(kw in lower_text for kw in ["news", "article", "media", "press"]):
                source_type = "news"
            elif any(kw in lower_text for kw in ["report", "pdf", "document", "paper"]):
                source_type = "document"
            elif any(kw in lower_text for kw in ["database", "registry", "whois"]):
                source_type = "database"

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
    Falls back to keyword-based source type detection.

    Returns list of {source_type, name}.
    """
    sources = []
    lines = plan_text.strip().split("\n")

    valid_types = {"file_upload", "web_scrape", "api_feed", "database", "rss_feed"}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try structured format: N. [type] description
        m = re.match(r'^\d+[.)]\s*\[(\w+)\]\s*(.*)', line)
        if m:
            stype = m.group(1).lower().strip()
            desc = m.group(2).strip()
            if stype in valid_types and desc:
                sources.append({"source_type": stype, "name": desc[:256]})
                continue

        # Try numbered/bulleted items with keyword detection
        m2 = re.match(r'^[\d+.)•\-*]\s*(.*)', line)
        if m2:
            desc = m2.group(1).strip()
            if len(desc) < 10:
                continue
            lower = desc.lower()
            if any(kw in lower for kw in ["upload", "file", "csv", "excel", "spreadsheet", "pdf"]):
                stype = "file_upload"
            elif any(kw in lower for kw in ["scrape", "website", "web page", "crawl"]):
                stype = "web_scrape"
            elif any(kw in lower for kw in ["rss", "news feed", "syndication"]):
                stype = "rss_feed"
            elif any(kw in lower for kw in ["api", "endpoint"]):
                stype = "api_feed"
            elif any(kw in lower for kw in ["database", "registry", "whois", "query"]):
                stype = "database"
            else:
                stype = "file_upload"  # default
            sources.append({"source_type": stype, "name": desc[:256]})

    return sources
