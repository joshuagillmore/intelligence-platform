# Frontend — Analyst UI

Next.js **14** (App Router) · TypeScript · Tailwind · **npm**. The analyst-facing
workbench over the backend API. The product name is **SENTINEL** — keep it
consistent in UI copy; shared name/version/tagline constants live in
`src/lib/branding.ts`. See the root `CLAUDE.md` for architecture, branching, and
deploy.

## Commands (npm)

```bash
npm install
npm run dev      # http://localhost:3000 (expects backend on :8000)
npm run lint     # eslint (next lint) — part of "done"
npm run build    # production build — part of "done"
npm run start    # serve the production build
```

Tests: **`npm run test`** (Vitest + RTL component/logic tests in `tests/unit/`) and
**`npm run e2e`** (Playwright authenticated smoke across all views + seeded
assertions, in `tests/e2e/`; needs the stack up + `backend/scripts/seed_demo.py`).
`lint` + `build` remain part of the gate.

## Layout (`src/`)

| Path | What |
|------|------|
| `app/` | App Router pages — one folder per view: `page.tsx` (dashboard), `collections`, `collection-plans`, `data-sources`, `network` (graph), `geo`, `timeline`, `search`, `watchlist`, `products`, `cyber`, `llm-hub`, `admin`, `login`. `layout.tsx` is the shell. |
| `components/` | Shared UI: `GraphVisualization`, `GeoMap`, `TopicMindMap`, `TemporalSlider`, `Sidebar`, `StatusBar`, `MobileHeader`/`MobileBottomNav`, `NotificationProvider`, `KeyboardShortcuts`, `HighlightedExcerpt`, `MindMapControls`, `LoadingSpinner`. |
| `stores/` | **Currently empty** — no global store library (the dead `graphStore.ts` and the `zustand`/`zundo` deps were removed; the network page hand-rolls its own local undo). |
| `lib/` | `api.ts` (axios client → backend), `ProjectContext.tsx`, `branding.ts` (app name/version), `entityStyles.ts` (entity-color SSOT), `graphLayout.ts`, `errorMessages.ts`. |

## Stack conventions

- **App Router:** be deliberate about server vs client components. Anything using
  hooks, d3, or leaflet is a client component (`"use client"`).
- **State:** cross-view state flows through React context (`lib/ProjectContext.tsx`)
  and local component state; don't scatter global state. There is no global store
  library (the old zundo-based `graphStore` and both `zustand`/`zundo` deps were
  removed) — the network page hand-rolls its own local undo/redo, so leave that
  as-is.
- **API:** all backend calls go through `lib/api.ts` (axios). Don't hardcode base
  URLs or an API key in components (a hardcoded fallback key was a past finding).
- **Visualization:** graph = d3 (`GraphVisualization`, `graphLayout.ts`); maps =
  raw **leaflet** via dynamic import (`GeoMap`; no react-leaflet). Keep heavy viz
  in client components.
- **Styling:** Tailwind. Current theme tokens (`tailwind.config.ts`): `navy`
  (900–600 dark surfaces), `accent` (blue/cyan), `threat` (critical/high/medium/
  low). Fonts (Inter + JetBrains Mono) are self-hosted via `next/font`; the
  Material Symbols icon font loads via a `<link>` in `app/layout.tsx`. Prefer
  tokens over ad-hoc hex, and entity colors from `lib/entityStyles.ts` (SSOT).

## Sentinel redesign (in progress)

A "paper/ink" redesign of the UI lives on the **`design/sentinel-redesign`**
branch (not merged to `main`; `main` is the navy/dark theme above). When doing
frontend design work, confirm which theme the branch you're on targets before
restyling — don't mix the two systems in one branch.

## Definition of done

`npm run lint` clean **and** `npm run build` succeeds.
