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
