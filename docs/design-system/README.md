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
claude mcp list                       # claude-design should be ✓ Connected
```

Then ask Claude Code to sync; it uses `DesignSync` (`finalize_plan` →
`write_files`), one component at a time rather than a wholesale replace.
Remote project: **SENTINEL Design System**.

## Contents — 14 cards

| Group | Card | Covers |
|-------|------|--------|
| Foundations | `colors` | navy surfaces, accent, threat severity scale |
| Foundations | `typography` | Inter / JetBrains Mono, the real type scale |
| Foundations | `entity-colours` | per-type colour SSOT shared by graph, map, badges |
| Foundations | `token-adherence` | the rule, the consolidation, the open decision |
| Workflow | `pir-panel` | requirements spine, OPEN→SATISFIED lifecycle |
| Workflow | `collection-plan` | plan lifecycle + per-source health |
| Workflow | `attack-coverage` | ATT&CK cell states, sub-technique nesting |
| Components | `severity-stat-card` | triage strip, count / percent / progress variants |
| Components | `badges-and-confidence` | type badges, relationship evidence, probability + admiralty |
| Components | `empty-and-error-states` | no-project CTA, failure alert |
| Components | `intelligence-product` | rendered INTSUM with classification + export |
| Components | `enrichment-panel` | provider results with provenance and cache status |
| Components | `assistant-panel` | Aegis with derived citations |
| Components | `feedback` | the four toast states, and the anti-pattern |

## Token consolidation — done 2026-07-26

240 sites converted, verified visually neutral (lint, build, 96 vitest,
14 smoke + 5 mobile + 4 seeded E2E, and pixel-equivalent rendered views):

| Was | Sites | Now |
|-----|-------|-----|
| `#2f3444` — undeclared twin of `navy-600` | 43 | `navy-600` |
| `bg-[#1a1f2e]` / `border-[#1a1f2e]` arbitrary values | 51 | `bg-navy-800` / `border-navy-800` |
| `[#adc6ff]` — the most-used colour, not a token | 146 | `accent-periwinkle` |

`accent.periwinkle` was added to `tailwind.config.ts`. Opacity modifiers
(`/15`, `/20`, `/30`) survive the conversion because Tailwind applies alpha to
config colours — 42 were in play.

## Still undeclared — a decision, not a sweep

| Value | Role | Sites |
|-------|------|-------|
| `#0e1321` | sidebar / nav ground | 21 |
| `#090e1c` | deep panel ground | 14 |
| `#0d1220` | third near-black | 8 |
| `#252a39` | twin of `navy-700` | 29 |

Four near-blacks against one declared `navy-900`. Unlike the twins above, these
may be intentional depth layering — flattening them would collapse real visual
hierarchy, so they are reported rather than swept. Decide how many ground levels
the interface actually needs, then declare exactly that many.

Also remaining: 33 `style={{ backgroundColor: '#1a1f2e' }}` inline objects,
several behind conditionals. Converting them needs per-site JSX judgement rather
than a find/replace.

## Generated cards

`components/evidence-chain.html` is **not hand-authored**. It is produced by
`frontend/tests/e2e/generate-ds-card.spec.ts`, which renders the live
`EvidenceChain` component against real API data and lifts the resulting markup:

```bash
CAPTURE_PROJECT_ID=<uuid> CAPTURE_ENTITY=<entity-id> \
  npx playwright test generate-ds-card.spec.ts
```

The card therefore cannot describe a component that no longer exists, or values
the app does not produce. Regenerate it after changing the component. Other cards
remain hand-authored against the real tokens; this is the pattern to follow as
more components stabilise.
