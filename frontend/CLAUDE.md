# Frontend — Analyst UI

Next.js **14** (App Router) · TypeScript · Tailwind · **npm**. The analyst-facing
workbench over the backend API. See the root `CLAUDE.md` for architecture,
branching, and deploy.

## Commands (npm)

```bash
npm install
npm run dev      # http://localhost:3000 (expects backend on :8000)
npm run lint     # eslint (next lint) — part of "done"
npm run build    # production build — part of "done"
npm run start    # serve the production build
```

There is no test runner configured yet; **`lint` + `build` are the gate.**

## Layout (`src/`)

| Path | What |
|------|------|
| `app/` | App Router pages — one folder per view: `page.tsx` (dashboard), `collections`, `collection-plans`, `data-sources`, `network` (graph), `geo`, `timeline`, `search`, `watchlist`, `products`, `cyber`, `llm-hub`, `admin`, `login`. `layout.tsx` is the shell. |
| `components/` | Shared UI: `GraphVisualization`, `GeoMap`, `TopicMindMap`, `TemporalSlider`, `Sidebar`, `StatusBar`, `MobileHeader`/`MobileBottomNav`, `NotificationProvider`, `KeyboardShortcuts`, `HighlightedExcerpt`, `MindMapControls`, `LoadingSpinner`. |
| `stores/` | Zustand state — `graphStore.ts` (uses **zundo** for undo/redo). |
| `lib/` | `api.ts` (axios client → backend), `ProjectContext.tsx`, `graphLayout.ts`, `errorMessages.ts`. |

## Stack conventions

- **App Router:** be deliberate about server vs client components. Anything using
  hooks, zustand, d3, or leaflet is a client component (`"use client"`).
- **State:** cross-view state goes through the zustand store(s) in `stores/`;
  don't scatter global state. Undo/redo is via zundo — preserve it.
- **API:** all backend calls go through `lib/api.ts` (axios). Don't hardcode base
  URLs or an API key in components (a hardcoded fallback key was a past finding).
- **Visualization:** graph = d3 (`GraphVisualization`, `graphLayout.ts`); maps =
  leaflet / react-leaflet (`GeoMap`). Keep heavy viz in client components.
- **Styling:** Tailwind. Current theme tokens (`tailwind.config.ts`): `navy`
  (900–600 dark surfaces), `accent` (blue/cyan), `threat` (critical/high/medium/
  low), fonts Inter + JetBrains Mono. Prefer tokens over ad-hoc hex.

## Sentinel redesign (in progress)

A "paper/ink" redesign of the UI lives on the **`design/sentinel-redesign`**
branch (not merged to `main`; `main` is the navy/dark theme above). When doing
frontend design work, confirm which theme the branch you're on targets before
restyling — don't mix the two systems in one branch.

## Definition of done

`npm run lint` clean **and** `npm run build` succeeds.
