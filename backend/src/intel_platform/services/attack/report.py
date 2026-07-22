"""ATT&CK-structured intelligence product (Phase 3c).

Assembles a project's ATT&CK picture from the graph into one product:

  * ``observed_by_tactic`` — observed techniques grouped by tactic (count > 0),
  * ``attribution``        — top candidate threat-actor groups by shared-technique
                             overlap (**suggestive, not confirmed**),
  * ``key_mitigations``    — ATT&CK Mitigations addressing the observed techniques,
  * ``cve_enabled``        — observed techniques an in-scope project CVE could enable,
  * ``narrative``          — a SHORT LLM exec summary (``null`` if no LLM reachable),
  * ``markdown``           — a full report rendered deterministically from the above.

The structured sections and the markdown are built purely from the graph, so the
product is complete even with no LLM available; the narrative is the only
LLM-dependent piece and degrades to ``null`` on any provider error (never 500).

Graph reads use the sync Neo4j ``Driver`` and are offloaded with
``asyncio.to_thread`` from the async entrypoint.
"""
from __future__ import annotations

import asyncio
import json
import logging

from neo4j import Driver

from intel_platform.llm.providers import _get_provider
from intel_platform.llm.skills.loader import SkillsLoader

from . import graph_ops

logger = logging.getLogger(__name__)


# --- Structured assembly (sync; graph reads) -------------------------------

def _observed_by_tactic(matrix: dict) -> list[dict]:
    """Reduce the full matrix to observed techniques (count > 0) per tactic."""
    out: list[dict] = []
    for tactic in matrix.get("tactics", []):
        techniques = [
            {
                "id": t["id"],
                "name": t["name"],
                "observed_count": t["observed_count"],
                "methods": t.get("methods", []),
            }
            for t in tactic.get("techniques", [])
            if t.get("observed_count", 0) > 0
        ]
        if techniques:
            out.append({
                "tactic_id": tactic["id"],
                "tactic_name": tactic["name"],
                "techniques": techniques,
            })
    return out


def _attribution_top(attribution: dict, limit: int = 5) -> list[dict]:
    """Top-N candidate groups from ``get_attribution`` (fields trimmed for the product)."""
    return [
        {
            "id": g["id"],
            "name": g["name"],
            "shared_count": g["shared_count"],
            "coverage": g["coverage"],
        }
        for g in attribution.get("groups", [])[:limit]
    ]


def assemble_structured(driver: Driver, project_id: str) -> dict:
    """Build the structured sections from the graph (no LLM, no markdown)."""
    matrix = graph_ops.get_matrix(driver, project_id)
    attribution = graph_ops.get_attribution(driver, project_id)
    key_mitigations = graph_ops.get_key_mitigations(driver, project_id)
    cve_enabled = graph_ops.get_cve_enabled(driver, project_id)
    return {
        "project_id": project_id,
        "observed_by_tactic": _observed_by_tactic(matrix),
        "attribution": _attribution_top(attribution),
        "key_mitigations": key_mitigations,
        "cve_enabled": cve_enabled,
    }


# --- Markdown rendering (pure; deterministic) ------------------------------

def _methods_label(methods: list[str]) -> str:
    return ", ".join(methods) if methods else "—"


def _md_cell(value: object) -> str:
    """Escape a value for a GFM table cell — a raw ``|`` or newline garbles the row."""
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown(structured: dict, narrative: str | None) -> str:
    """Render the full markdown report deterministically from the structured data.

    Works with empty sections (each degrades to an explicit note) and never
    depends on the LLM narrative being present.
    """
    pid = structured.get("project_id", "")
    lines: list[str] = [f"# ATT&CK Intelligence Product — {pid}", ""]

    if narrative:
        lines += ["## Executive Summary", "", narrative.strip(), ""]

    # Observed techniques by tactic ----------------------------------------
    lines += ["## Observed Techniques by Tactic", ""]
    observed = structured.get("observed_by_tactic", [])
    if not observed:
        lines += ["_No techniques have been observed or mapped for this project yet._", ""]
    else:
        for tactic in observed:
            lines.append(f"### {tactic['tactic_name']} ({tactic['tactic_id']})")
            lines.append("")
            lines.append("| Technique | ID | Observed | Methods |")
            lines.append("| --- | --- | ---: | --- |")
            for t in tactic["techniques"]:
                lines.append(
                    f"| {_md_cell(t['name'])} | {t['id']} | {t['observed_count']} | {_methods_label(t.get('methods', []))} |"
                )
            lines.append("")

    # Candidate attribution ------------------------------------------------
    lines += ["## Candidate Attribution", ""]
    attribution = structured.get("attribution", [])
    lines += [
        "Candidate threat-actor groups by shared-technique overlap. This is "
        "**suggestive, not confirmed** attribution — shared TTPs are a weak signal, "
        "never proof.",
        "",
    ]
    if not attribution:
        lines += ["_No candidate groups overlap the observed techniques._", ""]
    else:
        lines.append("| Group | ID | Shared Techniques | Coverage |")
        lines.append("| --- | --- | ---: | ---: |")
        for g in attribution:
            lines.append(
                f"| {_md_cell(g['name'])} | {g['id']} | {g['shared_count']} | {g['coverage']:.0%} |"
            )
        lines.append("")

    # Key mitigations ------------------------------------------------------
    lines += ["## Key Mitigations", ""]
    mitigations = structured.get("key_mitigations", [])
    if not mitigations:
        lines += ["_No ATT&CK mitigations map to the observed techniques._", ""]
    else:
        lines.append("| Mitigation | ID | Techniques Covered |")
        lines.append("| --- | --- | ---: |")
        for m in mitigations:
            lines.append(f"| {_md_cell(m['name'])} | {m['id']} | {m['technique_count']} |")
        lines.append("")

    # CVE-enabled techniques ----------------------------------------------
    lines += ["## CVE-Enabled Techniques", ""]
    cve_enabled = structured.get("cve_enabled", [])
    lines += [
        "Observed techniques that an in-scope CVE could also enable "
        "(candidate exposure via CWE→CAPEC→ATT&CK, not observed behavior).",
        "",
    ]
    if not cve_enabled:
        lines += ["_No in-scope CVE enables an observed technique._", ""]
    else:
        for row in cve_enabled:
            cve_labels = ", ".join(
                (c.get("name") or c.get("id") or "") for c in row.get("cves", [])
            ) or "—"
            lines.append(f"- **{row['technique_name']}** ({row['technique_id']}): {cve_labels}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --- Narrative (LLM; degrades to None) -------------------------------------

def _narrative_prompt(structured: dict) -> str:
    return (
        "Write a SHORT executive summary (3–5 sentences) for an ATT&CK-structured "
        "intelligence product, based ONLY on the structured findings below. "
        "Lead with the bottom line. Frame any attribution as CANDIDATE / SUGGESTIVE "
        "overlap, never as confirmed attribution. Do not invent techniques, groups, "
        "mitigations, or CVEs that are not present in the data.\n\n"
        "Structured findings (JSON):\n"
        f"{json.dumps(structured, indent=2, default=str)}"
    )


async def generate_narrative(structured: dict) -> str | None:
    """A short LLM exec summary via the standard provider + ``report_writing`` skill.

    Degrades to ``None`` on any provider/LLM error — the structured product and
    the deterministic markdown stand on their own.
    """
    try:
        provider = await _get_provider()
    except Exception:
        logger.warning("No LLM provider for ATT&CK report narrative", exc_info=True)
        return None

    skill_system = SkillsLoader().get_system_prompt("report_writing", include_foundation=True) or ""
    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": _narrative_prompt(structured)}],
            system=skill_system,
            temperature=0.3,
            max_tokens=600,
        )
    except Exception:
        logger.warning("ATT&CK report narrative LLM call failed", exc_info=True)
        return None

    text = (getattr(result, "content", "") or "").strip()
    return text or None


# --- Public entrypoint -----------------------------------------------------

async def build_report(driver: Driver, project_id: str) -> dict:
    """Assemble the full ATT&CK-structured product for a project."""
    structured = await asyncio.to_thread(assemble_structured, driver, project_id)
    narrative = await generate_narrative(structured)
    markdown = render_markdown(structured, narrative)
    return {**structured, "narrative": narrative, "markdown": markdown}
