"""Agentic collection orchestrator.

Three-phase execution:
1. RESOLVE — LLM translates source names into concrete configs (URLs, feed URLs)
2. ACQUIRE — Real connectors fetch content, ingestion pipeline processes it
3. EVALUATE — LLM reviews results vs PIR, can add follow-up URLs (bounded)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from intel_platform.connectors.base import get_connector
from intel_platform.db.models import (
    AcquisitionLog,
    CollectionActivity,
    CollectionPlan,
    PlanStatus,
)
from intel_platform.models.entities import Document
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.ingestion import ingest_text
from intel_platform.services.plan_executor import over_source_budget

logger = logging.getLogger(__name__)

# Max follow-up rounds per source in the evaluate phase
MAX_FOLLOWUP_ROUNDS = 2

# ---------------------------------------------------------------------------
# LLM Prompts
# ---------------------------------------------------------------------------

RESOLVE_SYSTEM = """You are a collection source resolver for intelligence analysis.
Given a source description and type, generate the concrete configuration
needed to collect data from this source.

For web_scrape sources, generate: {"urls": ["url1", "url2", ...]}
  - Generate 3-8 specific, real URLs that would contain relevant information
  - Include news sites, government sources, think tanks, or domain-specific sites
  - URLs must be real, publicly accessible homepage or section URLs (NOT fabricated article URLs)
  - Prefer root/section URLs like https://reuters.com/world/middle-east/ over specific article URLs
  - NEVER invent article slugs or dates in URLs — use only URLs you are confident exist

For rss_feed sources, generate: {"feed_url": "url", "max_items": 20, "fetch_full_content": true}
  - Use well-known, real RSS/Atom feed URLs (e.g., https://feeds.bbci.co.uk/news/world/rss.xml)
  - Common patterns: /rss, /feed, /atom.xml, /feeds/

For api_feed sources, generate: {"base_url": "url", "endpoint": "path", "response_path": "data.results"}
  - Use real, publicly accessible JSON APIs

For database sources, generate: {"urls": ["url1", ...]}
  - Use real public registry URLs (NVD, CVE, WHOIS, UNHCR, WHO, etc.)
  - Prefer search/listing pages over specific record URLs

Respond with ONLY valid JSON. No explanation, no markdown."""

RESOLVE_USER = """PIR: {pir}
Source: {source_name}
Type: {source_type}
Generate the acquisition config."""

SELECT_SYSTEM = """You select the most relevant sources for an intelligence PIR from REAL web-search results.
You are given a numbered list of actual URLs with titles and snippets. Choose the ones most likely to contain
information answering the PIR for this source's role. Respond with ONLY valid JSON, no markdown.

For web_scrape / database / api_feed: {"urls": ["url", ...]} — up to 5 URLs, chosen ONLY from the list below.
For rss_feed: {"feed_url": "url"} — the single best news/feed URL from the list.

Rules:
- Use ONLY URLs that appear verbatim in the provided results. NEVER invent, complete, or modify a URL.
- Prefer authoritative, on-topic sources; skip social media, search engines, and generic portals.
- If none are relevant, return an empty list."""

EVALUATE_SYSTEM = """You are evaluating intelligence collection results against a PIR.
Respond with ONLY valid JSON:
{
  "satisfied": true/false,
  "follow_up_urls": ["url1", ...],
  "notes": "brief reasoning"
}

Rules:
- Set satisfied=true if the collected content adequately addresses the source's role in the PIR
- Only suggest follow_up_urls if you found specific leads in the content (max 3 URLs)
- Do not suggest URLs that are search engines or generic portals
- If the content is thin or irrelevant, set satisfied=false but only suggest follow-ups if you have specific URLs"""

EVALUATE_USER = """PIR: {pir}
Source: {source_name}
Collected {record_count} documents totaling {total_chars} characters.

Content summaries:
{summaries}

Should we follow up on any specific leads found in this content?"""


# ---------------------------------------------------------------------------
# Helper: Extract entities from text content
# ---------------------------------------------------------------------------

def _clean_scraped_content(text: str) -> str:
    """Remove navigation, boilerplate, and noise from scraped web content."""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip very short lines (nav items, menu labels)
        if len(line) < 15:
            continue
        # Skip lines that look like navigation/UI elements
        lower = line.lower()
        skip_patterns = [
            'all newsletters', 'subscribe', 'sign up', 'log in', 'sign in',
            'cookie', 'privacy policy', 'terms of', 'advertis', 'follow us',
            'share this', 'read more', 'load more', 'show more', 'see all',
            'add to cart', 'buy now', 'download app', 'get the app',
            'back to top', 'skip to', 'jump to', 'table of contents',
            'copyright ©', 'all rights reserved', '© 20',
        ]
        if any(p in lower for p in skip_patterns):
            continue
        # Skip lines that are mostly special characters or look like menus
        alpha_ratio = sum(1 for c in line if c.isalpha()) / max(len(line), 1)
        if alpha_ratio < 0.4:
            continue
        # Skip lines with excessive pipes/bullets (nav menus)
        if line.count('|') > 2 or line.count('•') > 2:
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


async def _extract_entities(text: str, doc_id: str, mode: str):
    """Run entity extraction in the configured mode."""
    from intel_platform.services.extraction import extract_entities_nlp
    if mode == "llm":
        from intel_platform.services.extraction import extract_entities_llm
        return await extract_entities_llm(text, doc_id)
    elif mode == "hybrid":
        from intel_platform.services.extraction import extract_entities_hybrid
        return await extract_entities_hybrid(text, doc_id)
    return extract_entities_nlp(text, doc_id)


def _parse_llm_json(text: str) -> dict | None:
    """Parse JSON from LLM response, with multiple fallback strategies."""
    if not text or not text.strip():
        return None

    text = text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Find the first complete JSON object using brace counting
    start = text.find('{')
    if start >= 0:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\' and in_string:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    # Strategy 3: Try to fix common LLM JSON issues
    # Remove trailing commas before } or ]
    cleaned = re.sub(r',\s*([}\]])', r'\1', text)
    # Remove single-line comments
    cleaned = re.sub(r'//[^\n]*', '', cleaned)
    start = cleaned.find('{')
    if start >= 0:
        end = cleaned.rfind('}')
        if end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass

    return None


async def _get_agentic_provider(get_provider):
    """Get the best available provider for agentic steps (prefers cloud for JSON reliability).

    If the configured provider is Ollama, checks if a cloud provider key
    is available in the DB and uses that instead. Falls back to Ollama if no cloud key.
    """
    from intel_platform.config import settings

    provider = await get_provider()
    provider_name = provider.name() if provider else ""

    # If a dedicated collection provider is explicitly configured, honor it
    # as-is (do NOT override Ollama→cloud) — this is how the hybrid routing
    # keeps high-volume collection off a rate-limited cloud key.
    if (getattr(settings, "collection_llm_provider", "") or "").strip():
        logger.info("Agentic provider (collection-configured): %s", provider_name)
        return provider

    # If already a cloud provider, use it
    if not provider_name.startswith("ollama"):
        logger.info("Agentic provider: %s", provider_name)
        return provider

    # Ollama is configured — check for cloud keys
    try:
        from intel_platform.llm.providers import _resolve_api_key
        for cloud_provider in ["cohere", "anthropic", "openai"]:
            key = await _resolve_api_key(cloud_provider)
            if key:
                if cloud_provider == "cohere":
                    from intel_platform.llm.cohere_provider import CohereProvider
                    logger.info("Agentic provider: cohere (preferred over Ollama for structured output)")
                    return CohereProvider(api_key=key)
                elif cloud_provider == "anthropic":
                    from intel_platform.llm.anthropic import AnthropicProvider
                    logger.info("Agentic provider: anthropic (preferred over Ollama for structured output)")
                    return AnthropicProvider(api_key=key)
                elif cloud_provider == "openai":
                    from intel_platform.llm.openai_provider import OpenAIProvider
                    logger.info("Agentic provider: openai (preferred over Ollama for structured output)")
                    return OpenAIProvider(api_key=key)
    except Exception as e:
        logger.debug("Cloud provider lookup failed, using Ollama: %s", e)

    logger.info("Agentic provider: %s (no cloud keys available)", provider_name)
    return provider


async def _structured_generate(provider, messages, system, expected_keys=None, max_retries=3):
    """Generate a structured JSON response with retry logic for unreliable models.

    Args:
        provider: LLM provider instance
        messages: List of message dicts
        system: System prompt
        expected_keys: Optional list of keys the JSON must contain (e.g., ["urls"])
        max_retries: Max attempts (default 3)

    Returns:
        Parsed dict or None if all attempts fail.
    """
    temps = [0.2, 0.3, 0.4]

    for attempt in range(max_retries):
        try:
            msgs = list(messages)  # copy
            if attempt > 0:
                # Add a stronger reminder on retries
                last_msg = msgs[-1].copy()
                last_msg["content"] += "\n\nIMPORTANT: Respond with ONLY valid JSON. No explanation, no markdown, no preamble."
                msgs[-1] = last_msg

            result = await provider.generate(
                messages=msgs,
                system=system,
                temperature=temps[min(attempt, len(temps) - 1)],
                max_tokens=1024,
            )

            parsed = _parse_llm_json(result.content)
            if parsed is None:
                logger.warning("Structured generate attempt %d: JSON parse failed", attempt + 1)
                continue

            # Validate expected keys
            if expected_keys:
                missing = [k for k in expected_keys if k not in parsed]
                if missing:
                    logger.warning("Structured generate attempt %d: missing keys %s", attempt + 1, missing)
                    continue

            return parsed

        except Exception as e:
            logger.warning("Structured generate attempt %d failed: %s", attempt + 1, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(1)

    return None


def _validate_urls(urls: list) -> list[str]:
    """Filter URLs to only valid, public HTTP(S) URLs."""
    import ipaddress
    from urllib.parse import urlparse
    valid = []
    for url in urls:
        if not isinstance(url, str):
            continue
        url = url.strip()
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                continue
            if not parsed.netloc or '.' not in parsed.netloc:
                continue
            hostname = (parsed.hostname or "").lower()
            # Reject internal/private/reserved. IP-literal hosts are checked
            # robustly via ipaddress (covers 10/8, 172.16/12, 192.168/16,
            # 169.254/16, loopback, ::1, etc.). This is a fast pre-filter; the
            # authoritative DNS-resolving guard runs inside crawl_urls (via
            # collection/url_guard) and covers every fetch path.
            if hostname in ("localhost", "0.0.0.0"):
                continue
            try:
                if not ipaddress.ip_address(hostname).is_global:
                    continue
            except ValueError:
                pass  # not an IP literal — a domain
            valid.append(url)
        except Exception:
            continue
    return valid


# ---------------------------------------------------------------------------
# Phase 1: RESOLVE — LLM generates concrete configs for each source
# ---------------------------------------------------------------------------

async def _resolve_via_search(provider, pir: str, source, max_results: int = 10) -> dict | None:
    """Ground source resolution in REAL web-search results.

    Instead of asking the LLM to recall (hallucinate) URLs, run a live
    DuckDuckGo search built from the PIR + source, then let the LLM SELECT the
    most relevant results. A hard allow-list filter guarantees the returned
    URLs actually came from the search — the model cannot invent one. Returns
    None when the search yields nothing (caller falls back to LLM generation).
    """
    import asyncio

    from intel_platform.collection.proxy import get_active_proxy_config
    from intel_platform.collection.search import web_search

    # Route the search egress through the active collection proxy (if any).
    proxy = (await get_active_proxy_config()).get_proxy_url()
    query = f"{source.name} {pir}".strip()[:300]
    results = await asyncio.to_thread(web_search, query, max(10, max_results), proxy)
    if not results:
        return None

    listing = "\n".join(
        f"{i + 1}. {r['url']} — {r.get('title', '')}: {r.get('snippet', '')[:140]}"
        for i, r in enumerate(results)
    )
    is_feed = source.source_type == "rss_feed"
    key = "feed_url" if is_feed else "urls"
    user = (
        f"PIR: {pir}\nSource: {source.name} (type: {source.source_type})\n\n"
        f"Real search results:\n{listing}\n\n"
        f'Select up to {max_results} most relevant. Return JSON with key "{key}".'
    )
    config = await _structured_generate(
        provider,
        messages=[{"role": "user", "content": user}],
        system=SELECT_SYSTEM,
        expected_keys=[key],
    )
    if not config:
        return None

    allowed = {r["url"] for r in results}
    if is_feed:
        feed_url = config.get("feed_url", "")
        if feed_url not in allowed:
            feed_url = results[0]["url"]
        return {"feed_url": feed_url, "max_items": max_results, "fetch_full_content": True}

    urls = [u for u in (config.get("urls") or []) if u in allowed]
    if not urls:  # LLM picked nothing valid — fall back to the top real hits
        urls = [r["url"] for r in results[:max_results]]
    return {"urls": urls[:max_results]}


async def resolve_sources(plan, sources, db, provider, max_results: int = 10):
    """Resolve concrete acquisition configs for each source.

    Prefers grounding in live web search (`_resolve_via_search`); falls back to
    LLM URL generation only when search returns nothing.
    """
    pir = plan.refined_pir or plan.pir or plan.requirement

    for source in sources:
        if source.source_type == "file_upload":
            continue

        source.collection_status = "resolving"
        db.add(CollectionActivity(
            plan_id=plan.id, source_id=source.id,
            event="source_resolving",
            message=f"Resolving config for: {source.name}",
        ))
        await db.commit()

        try:
            # Determine expected keys based on source type
            expected = ["urls"] if source.source_type in ("web_scrape", "database", "api_feed") else ["feed_url"]

            # Ground resolution in real web search first; fall back to LLM URL
            # generation only when search returns nothing.
            config = await _resolve_via_search(provider, pir, source, max_results)
            grounded = config is not None
            if not config:
                config = await _structured_generate(
                    provider,
                    messages=[{"role": "user", "content": RESOLVE_USER.format(
                        pir=pir, source_name=source.name, source_type=source.source_type,
                    )}],
                    system=RESOLVE_SYSTEM,
                    expected_keys=expected,
                )
            if not config:
                raise ValueError("All JSON parse attempts failed for source resolution")

            # Validate URLs — filter out obviously bad ones
            if "urls" in config and isinstance(config["urls"], list):
                config["urls"] = _validate_urls(config["urls"])
            if "feed_url" in config:
                valid = _validate_urls([config["feed_url"]])
                if not valid:
                    config["feed_url"] = ""

            # Merge into existing config (preserve any user-set values)
            source.config = {**(source.config or {}), **config}
            source.collection_status = "queued"

            db.add(CollectionActivity(
                plan_id=plan.id, source_id=source.id,
                event="source_resolved",
                message=f"Resolved ({'search-grounded' if grounded else 'llm-generated'}): {json.dumps(config)[:170]}",
            ))
        except Exception as e:
            logger.warning("Failed to resolve source %s: %s", source.name, e)
            source.collection_status = "failed"
            source.last_error = f"Resolution failed: {str(e)[:300]}"
            db.add(CollectionActivity(
                plan_id=plan.id, source_id=source.id,
                event="source_failed",
                message=f"Resolution failed: {str(e)[:200]}",
            ))

        await db.commit()


# ---------------------------------------------------------------------------
# Phase 2: ACQUIRE — fetch content and run through ingestion pipeline
# ---------------------------------------------------------------------------

async def _acquire_urls_concurrent(connector, config, urls, *, db, plan, source, concurrency, max_results=10):
    """Fetch multiple URLs through a connector with bounded concurrency.

    Network fetches run concurrently (Semaphore-gated); the shared AsyncSession is
    guarded by a lock because it is not safe for concurrent use. Emits per-URL
    telemetry (url_fetching / url_fetched / url_failed) for the Trace view.
    Returns (all_records, errors).
    """
    sem = asyncio.Semaphore(max(1, concurrency))
    db_lock = asyncio.Lock()
    all_records: list = []
    errors: list[str] = []

    async def fetch_one(url: str):
        async with db_lock:
            db.add(CollectionActivity(
                plan_id=plan.id, source_id=source.id,
                event="url_fetching", message=url[:480],
            ))
            await db.commit()
        async with sem:
            single_config = {**config, "url": url}
            try:
                r = await connector.acquire(single_config)
                recs = r.records or []
                words = sum(len((rec.get("content", "") or "").split()) for rec in recs)
                async with db_lock:
                    all_records.extend(recs)
                    db.add(CollectionActivity(
                        plan_id=plan.id, source_id=source.id,
                        event="url_fetched",
                        message=f"{url} · {len(recs)} rec · {words}w"[:480],
                    ))
                    await db.commit()
            except Exception as e:
                async with db_lock:
                    errors.append(f"{url}: {e}")
                    db.add(CollectionActivity(
                        plan_id=plan.id, source_id=source.id,
                        event="url_failed",
                        message=f"{url}: {str(e)[:200]}"[:480],
                    ))
                    await db.commit()

    await asyncio.gather(*[fetch_one(u) for u in urls[:max_results]], return_exceptions=True)
    return all_records, errors


async def acquire_source(source, plan, db, store, extraction_mode="nlp", provider=None, max_results=10):
    """Fetch content from a source and run it through the ingestion pipeline.

    Returns dict with record_count, entities_created, relationships_created.
    """
    from intel_platform.config import settings

    connector = get_connector(source.source_type)
    config = source.config or {}

    # Handle multi-URL for web_scrape/database: upstream connector takes single "url",
    # but agentic resolve generates "urls" list. Fetch them with bounded concurrency.
    if source.source_type in ("web_scrape", "database") and "urls" in config and isinstance(config["urls"], list):
        from intel_platform.connectors.base import AcquireResult as AR
        concurrency = getattr(settings, "collection_crawl_concurrency", 4)
        all_records, errors = await _acquire_urls_concurrent(
            connector, config, config["urls"],
            db=db, plan=plan, source=source, concurrency=concurrency, max_results=max_results,
        )
        result = AR(
            success=len(all_records) > 0,
            record_count=len(all_records),
            records=all_records,
            error="; ".join(errors) if errors else "",
        )
    else:
        result = await connector.acquire(config)

    if not result.success and result.record_count == 0:
        raise RuntimeError(result.error or "Acquisition returned no data")

    total_entities = 0
    total_rels = 0
    total_chars = 0

    for record in result.records:
        content = record.get("content", "")
        if not content or len(content) < 50:
            continue

        # Clean scraped content to remove navigation, boilerplate, ads
        content = _clean_scraped_content(content)
        if not content or len(content) < 50:
            continue

        total_chars += len(content)
        title = record.get("title", "")
        url = record.get("url", "")

        # Per-document structured summary (non-fatal): summary/key_facts/sentiment/topics.
        summary_json = ""
        if provider is not None:
            try:
                from intel_platform.services.summarization import summarize_document
                summary = await summarize_document(content, provider)
                if summary:
                    summary_json = json.dumps(summary)
            except Exception as e:
                logger.debug("Summarization failed for %s: %s", url or title, e)

        # Store as Document in Neo4j
        doc = Document(
            name=f"[Collection] {title or url or source.name}"[:256],
            content=content[:50000],  # Cap at 50k chars per doc
            reliability_rating="C3",
            project_id=plan.project_id,
            summary_json=summary_json,
        )
        store.create_entity(doc)

        # Chunk and extract
        chunk_size = getattr(settings, 'chunk_size', 1200)
        chunk_overlap = getattr(settings, 'chunk_overlap', 200)
        chunks = ingest_text(content, chunk_size, chunk_overlap)

        all_entities = []
        all_rels = []
        for chunk in chunks:
            try:
                ents, rels = await _extract_entities(chunk["content"], doc.id, extraction_mode)
                all_entities.extend(ents)
                all_rels.extend(rels)
            except Exception as e:
                logger.debug("Extraction failed for chunk: %s", e)

        if all_entities or all_rels:
            build_result = build_graph_from_extractions(
                store, all_entities, all_rels, plan.project_id,
                source_doc_id=doc.id,
            )
            total_entities += build_result.get("entities_created", 0)
            total_rels += build_result.get("relationships_created", 0)

    # Log acquisition
    acq_log = AcquisitionLog(
        source_id=source.id,
        plan_id=plan.id,
        result="SUCCESS" if result.record_count > 0 else "PARTIAL",
        record_count=result.record_count,
        source_type=source.source_type,
        source_config_snapshot=source.config or {},
        entities_created=total_entities,
        relationships_created=total_rels,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(acq_log)

    return {
        "record_count": result.record_count,
        "total_chars": total_chars,
        "entities_created": total_entities,
        "relationships_created": total_rels,
        "records": result.records,  # For evaluate phase
    }


# ---------------------------------------------------------------------------
# Phase 3: EVALUATE — LLM reviews results and may suggest follow-ups
# ---------------------------------------------------------------------------

async def evaluate_results(source, plan, acquire_result, provider):
    """Ask the LLM to evaluate collected content and suggest follow-ups."""
    pir = plan.refined_pir or plan.pir or plan.requirement
    records = acquire_result.get("records", [])

    # Build content summaries (first 500 chars of each, max 5)
    summaries = []
    for r in records[:5]:
        title = r.get("title", "")
        content = r.get("content", "")[:500]
        summaries.append(f"- {title}: {content}...")

    evaluation = await _structured_generate(
        provider,
        messages=[{"role": "user", "content": EVALUATE_USER.format(
            pir=pir,
            source_name=source.name,
            record_count=acquire_result.get("record_count", 0),
            total_chars=acquire_result.get("total_chars", 0),
            summaries="\n".join(summaries) if summaries else "(no content collected)",
        )}],
        system=EVALUATE_SYSTEM,
        expected_keys=["satisfied"],
    )
    if evaluation:
        # Ensure defaults
        evaluation.setdefault("follow_up_urls", [])
        evaluation.setdefault("notes", "")
        return evaluation
    # Parse failure must NOT be reported as satisfied — that would silently
    # mark an unassessed collection as complete and bias the loop toward false
    # success. Treat an unparseable evaluation as not-yet-satisfied.
    return {"satisfied": False, "follow_up_urls": [], "notes": "Could not parse evaluation after retries"}


# ---------------------------------------------------------------------------
# Main entry point: run_agentic_loop
# ---------------------------------------------------------------------------

async def run_agentic_loop(
    plan_id, db_factory, get_store, get_provider,
    max_results_per_source: int = 10, source_limit: int | None = None,
):
    """Background task: resolve, acquire, and evaluate all sources in a plan.

    Args:
        plan_id: UUID of the collection plan
        db_factory: async_sessionmaker (not request-scoped)
        get_store: callable returning GraphStore
        get_provider: async callable returning LLM provider
        source_limit: cap on how many sources are actually collected. A
            requirement should be answerable *or* stop against a stated
            collection budget; without this the planner's proposed source count
            is the only bound, so a plan given a budget of 3 ran all 5.
    """
    try:
        provider = await _get_agentic_provider(get_provider)
    except Exception as e:
        logger.error("Failed to get LLM provider for agentic loop: %s", e)
        # Mark plan failed
        async with db_factory() as db:
            plan = await db.get(CollectionPlan, plan_id)
            if plan:
                plan.status = PlanStatus.COMPLETED
                db.add(CollectionActivity(
                    plan_id=plan_id, event="plan_failed",
                    message=f"No LLM provider available: {e}",
                ))
                await db.commit()
        return

    store = get_store()

    # Phase 1: Resolve all source configs
    async with db_factory() as db:
        plan = await db.get(CollectionPlan, plan_id)
        if not plan:
            logger.error("Plan %s not found", plan_id)
            return

        sources = [s for s in (plan.sources or []) if s.enabled and s.source_type != "file_upload"]

        db.add(CollectionActivity(
            plan_id=plan.id, event="plan_resolving",
            message=f"Resolving configs for {len(sources)} sources",
        ))
        await db.commit()

        await resolve_sources(plan, sources, db, provider, max_results_per_source)

    # Phase 2 & 3: Acquire and evaluate each source
    completed = 0
    failed = 0

    async with db_factory() as db:
        plan = await db.get(CollectionPlan, plan_id)
        sources = [s for s in (plan.sources or []) if s.enabled and s.source_type != "file_upload"]

        from intel_platform.config import settings
        extraction_mode = (plan.routing_rules or {}).get("extraction_mode") or settings.extraction_mode

        attempted = 0
        for source in sources:
            if source.collection_status == "failed":
                failed += 1
                continue

            # Stop against the collection budget, and say so explicitly — the
            # analyst needs to distinguish "the plan was this small" from "the
            # budget ran out with sources still queued".
            if over_source_budget(attempted, source_limit):
                db.add(CollectionActivity(
                    plan_id=plan.id, source_id=source.id,
                    event="source_skipped",
                    message=f"Source budget of {source_limit} reached — not collected",
                ))
                await db.commit()
                continue
            attempted += 1

            # Mark collecting
            source.collection_status = "collecting"
            db.add(CollectionActivity(
                plan_id=plan.id, source_id=source.id,
                event="source_collecting",
                message=f"Acquiring: {source.name}",
            ))
            await db.commit()

            try:
                acquire_result = await acquire_source(source, plan, db, store, extraction_mode, provider=provider, max_results=max_results_per_source)

                ent_count = acquire_result.get("entities_created", 0)
                rel_count = acquire_result.get("relationships_created", 0)
                rec_count = acquire_result.get("record_count", 0)

                db.add(CollectionActivity(
                    plan_id=plan.id, source_id=source.id,
                    event="source_acquired",
                    message=f"Acquired {rec_count} docs, {ent_count} entities, {rel_count} relationships",
                ))
                await db.commit()

                # Phase 3: Evaluate and follow up
                for round_num in range(MAX_FOLLOWUP_ROUNDS):
                    evaluation = await evaluate_results(source, plan, acquire_result, provider)

                    follow_ups = evaluation.get("follow_up_urls", [])
                    notes = evaluation.get("notes", "")

                    if not follow_ups or evaluation.get("satisfied", True):
                        db.add(CollectionActivity(
                            plan_id=plan.id, source_id=source.id,
                            event="source_evaluated",
                            message=f"Evaluation: satisfied. {notes}",
                        ))
                        await db.commit()
                        break

                    # Follow up on suggested URLs
                    db.add(CollectionActivity(
                        plan_id=plan.id, source_id=source.id,
                        event="source_followup",
                        message=f"Follow-up round {round_num + 1}: {len(follow_ups)} URLs. {notes}",
                    ))
                    await db.commit()

                    # Add follow-up URLs to config and re-acquire
                    existing_urls = source.config.get("urls", [])
                    new_urls = [u for u in follow_ups[:3] if u not in existing_urls]
                    if new_urls:
                        source.config = {**source.config, "urls": new_urls, "max_pages": len(new_urls)}
                        await db.commit()

                        followup_result = await acquire_source(source, plan, db, store, extraction_mode, provider=provider, max_results=max_results_per_source)
                        fu_ent = followup_result.get("entities_created", 0)
                        fu_rel = followup_result.get("relationships_created", 0)

                        db.add(CollectionActivity(
                            plan_id=plan.id, source_id=source.id,
                            event="source_followup_done",
                            message=f"Follow-up: {followup_result.get('record_count', 0)} docs, {fu_ent} entities, {fu_rel} rels",
                        ))
                        await db.commit()

                        # Merge results for next evaluation round
                        acquire_result["records"] = acquire_result.get("records", []) + followup_result.get("records", [])
                        acquire_result["record_count"] = acquire_result.get("record_count", 0) + followup_result.get("record_count", 0)

                source.collection_status = "succeeded"
                source.last_success_at = datetime.now(timezone.utc)
                source.total_records_acquired += acquire_result.get("record_count", 0)

                db.add(CollectionActivity(
                    plan_id=plan.id, source_id=source.id,
                    event="source_succeeded",
                    message=f"Completed: {source.name} ({acquire_result.get('record_count', 0)} total records)",
                ))
                completed += 1

            except Exception as e:
                source.collection_status = "failed"
                source.last_failure_at = datetime.now(timezone.utc)
                source.last_error = str(e)[:500]

                db.add(CollectionActivity(
                    plan_id=plan.id, source_id=source.id,
                    event="source_failed",
                    message=f"Failed: {str(e)[:300]}",
                ))
                failed += 1
                logger.warning("Source %s failed: %s", source.name, e)

            await db.commit()

        # Final status
        upload_sources = [s for s in (plan.sources or []) if s.source_type == "file_upload" and s.enabled]
        if not upload_sources:
            plan.status = PlanStatus.COMPLETED

        db.add(CollectionActivity(
            plan_id=plan.id, event="plan_completed",
            message=f"Collection complete: {completed} succeeded, {failed} failed" + (
                f", {len(upload_sources)} file uploads pending" if upload_sources else ""),
        ))
        plan.updated_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info("Agentic loop completed for plan %s: %d ok, %d failed", plan_id, completed, failed)
