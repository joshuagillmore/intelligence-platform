# SENTINEL Design System

Component library for the analyst UI, kept as self-contained HTML previews and
synced to a Claude Design project (claude.ai/design) via the `claude-design` MCP
server.

## Why it exists

The UI had drifted: three hand-rolled markups for the same empty state, a
`key:value` dump where every other surface rendered Markdown, an eighth stat
card that broke a flex row. There was no canonical reference. This is it.

## Rules

- **Values, not classes.** Each preview inlines the real hex/px values from
  `frontend/tailwind.config.ts` and `frontend/src/lib/entityStyles.ts`, so a card
  cannot silently drift from the app.
- **Self-contained.** No external CSS, fonts or images — each file renders alone.
- **First line is the card marker:** `<!-- @dsCard group="…" -->`. The Design
  System pane groups by that value.
- Each card states the *reasoning*, not just the pixels — why unrated is its own
  bucket, why errors never become content, why mono means machine-truth.

## Sync

```bash
# one component at a time — never a wholesale replace
claude mcp list                       # claude-design should be ✓ Connected
```
Then ask Claude Code to sync; it uses `DesignSync` (`finalize_plan` → `write_files`).
Remote project: **SENTINEL Design System**.

## Contents

| Group | Card | Covers |
|-------|------|--------|
| Foundations | `colors` | navy surfaces, accent, threat severity scale |
| Foundations | `typography` | Inter / JetBrains Mono, the real type scale |
| Foundations | `entity-colours` | per-type colour SSOT shared by graph, map, badges |
| Components | `severity-stat-card` | triage strip, count / percent / progress variants |
| Components | `badges-and-confidence` | type badges, relationship evidence, probability + admiralty |
| Components | `empty-and-error-states` | no-project CTA, failure alert |
| Components | `intelligence-product` | rendered INTSUM with classification + export |
| Components | `enrichment-panel` | provider results with provenance and cache status |
