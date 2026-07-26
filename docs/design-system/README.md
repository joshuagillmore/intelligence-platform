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

## Added in the second pass

| Group | Card | Covers |
|-------|------|--------|
| Foundations | `token-adherence` | the rule, plus measured drift (see below) |
| Workflow | `pir-panel` | requirements spine, OPEN→SATISFIED lifecycle |
| Workflow | `collection-plan` | plan lifecycle + per-source health |
| Workflow | `attack-coverage` | ATT&CK cell states, sub-technique nesting |
| Components | `assistant-panel` | Aegis with derived citations |
| Components | `feedback` | the four toast states, and the anti-pattern |

## Token consolidation — done 2026-07-26

240 sites converted, verified visually neutral (14 smoke + 5 mobile + 4 seeded E2E green):

| Was | Sites | Now |
|-----|-------|-----|
|  — undeclared twin of  | 43 |  |
|  /  arbitrary values | 51 |  |
|  — the most-used colour, not a token | 146 |  (new token) |

 was added to . Opacity modifiers
(, , ) survive the conversion because Tailwind handles alpha on
config colours — 42 of them were in play.

## Still undeclared — deliberate decision needed

| Value | Role | Sites |
|-------|------|-------|
|  | sidebar / nav ground | 21 |
|  | deep panel ground | 14 |
|  | third near-black | 8 |
|  | twin of  | 29 |

Four near-blacks against one declared . Unlike the twins above these
may be intentional depth layering, so they are **not** swept — flattening them
would collapse real hierarchy. Decide how many ground levels the interface needs,
then declare exactly that many.

Remaining: 33  inline objects, several
behind conditionals. Converting them needs per-site JSX judgement rather than a
find/replace.
