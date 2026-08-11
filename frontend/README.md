# SENTINEL — Frontend

The analyst-facing UI for SENTINEL: a Next.js 14 (App Router) single-page
workbench over the FastAPI backend. TypeScript, Tailwind, React context + local
state, d3 for the knowledge graph, and leaflet for the map.

Views include the network graph, geo/GEOINT map, timeline, topic mind-map,
collections and collection plans, cyber-observable enrichment, intelligence
products, and admin.

## Develop

```bash
npm install
npm run dev      # http://localhost:3000 (expects the backend on :8000)
npm run lint     # eslint (next lint)
npm run build    # production build
npm run start    # serve the production build
npm run test     # vitest — unit + component tests (tests/unit/)
npm run e2e      # playwright — authenticated smoke across the views (tests/e2e/)
```

**`npm run lint` and `npm run build` are the gate** for "done". `npm run test`
runs standalone; `npm run e2e` needs the full stack up and the demo project
seeded (`backend/scripts/seed_demo.py`).

For the full stack (backend, Neo4j, Postgres, Redis, Ollama) run
`docker compose up` from the repo root instead. See the root
[`README.md`](../README.md) for the product overview and
[`CLAUDE.md`](./CLAUDE.md) for frontend architecture and conventions.
