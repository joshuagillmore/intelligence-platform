# Frontend — Analyst UI

Next.js **15** (App Router) · React **19** · TypeScript · Tailwind · **npm** · Node **22** (CI and
every Docker image). The analyst-facing workbench over the backend API. The product name is **SENTINEL** — keep it
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
npm run gen:api  # regenerate src/lib/api.generated.ts from ../backend/openapi.json
```

Tests: **`npm run test`** (Vitest + RTL component/logic tests in `tests/unit/`) and
**`npm run e2e`** (Playwright authenticated smoke across all views + seeded
assertions, in `tests/e2e/`; needs the stack up + `backend/scripts/seed_demo.py`).
`lint` + `build` remain part of the gate.

## Layout (`src/`)

| Path | What |
|------|------|
| `app/` | App Router pages — one folder per view: `page.tsx` (dashboard), `collections`, `collection-plans`, `data-sources`, `network` (graph), `geo`, `timeline`, `search`, `watchlist`, `analysis` (structured analytic techniques), `products`, `cyber`, `llm-hub`, `admin`, `login`, plus the dynamic routes `documents/[id]` and `project/[id]`. `layout.tsx` is the shell. |
| `components/` | Shared UI: `GraphVisualization`, `GeoMap`, `TopicMindMap`, `TemporalSlider`/`TemporalHistogram`, `Sidebar`, `StatusBar`, `MobileHeader`/`MobileBottomNav`, `NotificationProvider`, `KeyboardShortcuts`, `HighlightedExcerpt`, `MindMapControls`, `LoadingSpinner`, `Markdown`, `SelectProjectPrompt`. Feature panels: `AssistantPanel`/`AssistantCitations`, `AttackMatrix`/`AttackAttribution`, `EnrichmentPanel`, `EvidenceChain`, `PirPanel`, `PrintableProduct`. |
| `lib/` | `api.ts` (axios client → backend), `api.generated.ts` + `apiTypes.ts` (the backend contract, generated; see below), `SessionContext.tsx`, `ProjectContext.tsx` and `AssistantContext.tsx` (the three React contexts), `assistantGrounding.ts`, `branding.ts` (app name/version), `entityStyles.ts` (entity-color SSOT), `graphLayout.ts`, `projectOrder.ts` (dashboard ordering), `reportExport.ts`, `format.ts`, `errorMessages.ts`. |

## Stack conventions

- **App Router:** be deliberate about server vs client components. Anything using
  hooks, d3, or leaflet is a client component (`"use client"`). Every page is a
  client component today and reads route state through `useParams` /
  `useSearchParams` (synchronous); a new *server* page receives `params` and
  `searchParams` as Promises under Next 15 and must `await` them.
- **State:** cross-view state flows through React context — `lib/SessionContext.tsx`
  for the signed-in analyst, `lib/ProjectContext.tsx` for the active project,
  `lib/AssistantContext.tsx` for the assistant — plus
  local component state; don't scatter global state. There is no global store
  library and no `src/stores/` directory: the old zundo-based `graphStore` and
  both `zustand`/`zundo` deps were removed, and the network page hand-rolls its
  own local undo/redo, so leave that as-is.
- **API:** all backend calls go through `lib/api.ts` (axios). Don't hardcode base
  URLs or an API key in components (a hardcoded fallback key was a past finding).
- **Session:** an httpOnly `sentinel_session` cookie that `POST /api/auth/login`
  sets; no token is stored in the browser (a legacy `auth_token` is deleted on
  load). `api.ts` sends `withCredentials` and `X-Requested-With: sentinel` on
  every request, because the backend refuses a cookie-authenticated
  state-changing request without that header (the CSRF guard); a `fetch` outside
  axios must do both (see `topicsApi.streamSummary`). `SessionProvider` asks
  `GET /api/auth/me` on every load (a 401 is the sign-in gate for all views);
  `auth_user`/`auth_role` in storage are a display cache of that answer, never a
  credential. Sign-out calls `POST /api/auth/logout`, the only way to clear an
  httpOnly cookie.
- **Generated types:** `lib/api.generated.ts` is generated from
  `backend/openapi.json` (`backend/scripts/export_openapi.py` writes it) by
  `npm run gen:api`; never edit it by hand. `lib/apiTypes.ts` derives
  `ClientPath`, `BodyOf`, `QueryOf`, `ResponseOf` and `Model` from it, and
  `api.ts` uses them so every URL, request body and query string, and every
  response the backend declares, is checked against the schema. Most routes
  declare no response model yet; those keep a hand-written interface (or the
  loose `Undeclared`) until the backend adds one. After a backend route change,
  re-export the schema, run `npm run gen:api` and commit both;
  `tests/unit/apiGenerated.test.ts` fails until you do.
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

`npm run lint` clean **and** `npm run build` succeeds **and** `npm run test` passes.
