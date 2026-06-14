# Intelligence Platform — Sentinel

AI analyst workbench. **Backend:** Python (FastAPI, `uv`) in `backend/`. **Frontend:** Next.js 14 App Router + React 18 + TypeScript (strict) in `frontend/`. Graph store is Neo4j; also Postgres + Redis.

Active branch: `design/sentinel-redesign` (the "Sentinel" paper/ink editorial redesign). Heavy uncommitted local state lives on this branch — do not assume `git status` is clean.

## Deploy (Railway, project `humble-light`)

Services: `frontend`, `backend`, `neo4j`, `Postgres`, `Redis`.

```bash
cd <repo root>           # NOT the frontend/ subdir
railway up --ci -s frontend
```

- **Always run `cd frontend && npx --no-install next build` locally before deploying.** Railway's build runs `next lint` as a gate and fails the deploy on ESLint *errors* (unused imports/vars, raw text in JSX comment positions). The CI log truncates the actual error — the local build surfaces it. `tsc --noEmit` alone is not enough; it won't catch lint-rule violations.
- Live URLs: frontend `https://frontend-production-768f.up.railway.app`, backend `https://backend-production-0e02.up.railway.app`.
- `railway logs -s <service>` for runtime logs. `railway status --json` lists services (no clean name-only flag; pipe through `tr ',' '\n' | grep serviceName`).
- Deploys take a few minutes — run them with `run_in_background: true` and wait for the completion notification rather than polling.

## Backend API conventions

- Auth: `POST /api/auth/login` with `{username, password}` (dev creds `admin`/`admin`) → `{access_token}`. Send as `Authorization: Bearer <token>`.
- Most data is **project-scoped** via a `project_id` query param. A known populated project for manual testing: `58dfeb08-666f-482a-83c0-b506e8a0a150`.
- Frontend API client: `frontend/src/lib/api.ts`. `API_BASE` = `NEXT_PUBLIC_API_URL` (empty in prod — same origin via Railway). Namespaces: `projectsApi`, `watchlistApi`, `collectionsApi`, `collectionPlansApi`, `ingestApi`, `documentsApi`, `graphApi`, `queryApi`, `entitiesApi`, `geoApi`, `topicsApi`, `reportsApi`, `personasApi`, `llmApi`, `adminApi`, `healthApi`, `notebookApi`, `timelineApi`.

### ⚠️ Response-shape gotcha (caused real crashes)

Some list endpoints return a **wrapped object**, not a bare array. Always normalize before calling `.map`/`.slice`/`.length`:

```ts
const raw = res.data;
const list = Array.isArray(raw) ? raw : raw?.<key> ?? [];
```

Known wrapped endpoints and their keys:
- `documentsApi.list` → `{documents: [...]}`
- `watchlistApi.list` → `{watched_entities: [...], count}` (NOT `items`)
- `geoApi.locations` → `{locations: [...]}`
- `projectsApi.activity` → `{activity: [...]}`
- `personasApi.list` → `{personas: [...]}`, `topics` cluster → `{children: [...]}`

Bare arrays: `projectsApi.list`, `collectionPlansApi.list`, `entitiesApi.search`, `reportsApi.list`, `graphApi.centrality/communities/structuralHoles`.

Backend NLP extracts these entity types only: `Person, Organization, Location, Domain, Date, Financial, Quantity, Document`. No cyber types (INDICATOR/TTP/THREAT_ACTOR) exist yet.

## Frontend architecture (Sentinel)

- Component library: `frontend/src/components/sentinel/`. `Primitives.tsx` (Tag, Btn, EntityChip, CiteChip, PulseDot, ConfidenceRing, ENTITY_META), `Icon.tsx`, `Shell.tsx` (Header/Rail/FooterBar/CommandPalette), `SentinelShell.tsx` (wraps everything; auth + health + badge polling), `HeaderActions.tsx`, `mockData.ts`.
- One view per Rail route in `views/` (Hub, Acquire, Graph, Documents, Watchlist, Review, Products, Topics, Geo, Ach, Pinboard, Cyber, Admin). Each route `page.tsx` is a thin wrapper.
- **Mobile:** `MobileShell.tsx` (chrome) + `MobileViews.tsx` (MHub/MAcquire/MAsk/MProducts/MReview). `<MobileSwap desktop={...} mobile={...} />` renders both; CSS classes `.sentinel-desktop-only` / `.sentinel-mobile-only` swap at the **767px** breakpoint (defined in `app/globals.css`). Mobile views render at <768px.
- Design tokens are CSS custom properties in `app/globals.css`: `--ink, --paper, --paper-2, --line, --line-soft, --fg, --fg-2..4, --signal, --signal-soft, --signal-ink, --live, --warn, --cite, --violet, --mono, --serif, --sans`. Use these, never hardcoded colors. Fonts: IBM Plex Sans/Serif + JetBrains Mono.
- Toasts: `useNotifications()` from `components/NotificationProvider`. A `type: 'processing'` toast persists until you flip it via `updateNotification(id, {type: 'success'|'error', ...})` — capture the returned id or it spins forever. Non-processing toasts auto-dismiss after 10s.

## Conventions

- Keep demo/mock content out of project-scoped views. When a backend endpoint doesn't exist yet, render an honest "pending backend" empty-state panel — do NOT fall back to `mockData` literals (they make project-switching look broken). Endpoints still missing: `reviewApi`, `achApi`, `graphApi.shortestPath`, a cyber namespace. Those views (`ReviewView`, `AchView`, `CyberView`, GraphView Path mode, `MReview`) currently show pending states by design.
- Pre-existing TS errors in `src/stores/graphStore.ts` (missing zustand/zundo deps) are unrelated to the Sentinel view layer — ignore them; filter with `grep -vE "graphStore|stores/"` when reading `tsc` output.
- Commit/push only when asked.
