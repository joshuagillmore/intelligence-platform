# Screenshots

The root `README.md` renders the six images in this directory. They are captured
from a running instance with a **reproducible Playwright spec** rather than by
hand, so they can be refreshed after a UI change:

```bash
# stack up, then:
cd backend  && uv run python scripts/seed_demo.py        # deterministic demo project
cd frontend && CAPTURE_PROJECT_ID=demo-sentinel \
               CAPTURE_FOCUS_ENTITY=d-ta1 \
               CAPTURE_IOC=45.83.12.7 \
               npx playwright test capture-docs.spec.ts
```

`tests/e2e/capture-docs.spec.ts` drives the interaction each shot needs (select
an entity, expand and investigate an observable, open a saved product) instead
of grabbing an empty view. Env knobs:

| Variable | Purpose |
|----------|---------|
| `CAPTURE_PROJECT_ID` | Project to capture against (`demo-sentinel` for the seeded fixture) |
| `CAPTURE_FOCUS_ENTITY` | Entity id to select in the graph shot (`d-ta1` = APT-Demo) |
| `CAPTURE_IOC` | Indicator to expand in the cyber shot |
| `CAPTURE_ISLAND_DEGREE` | Degree filter for the graph; raise it to drop low-degree noise |

## Current set

| Filename | View | What it shows |
|----------|------|---------------|
| `network-graph.png` | `/network` | Force graph with APT-Demo selected — ego highlight, 5 relationships at 90% confidence, evidence links, AI actions |
| `geo-aoi.png` | `/geo` | Locations + connection lines, layer control, temporal window, area query |
| `cyber-enrichment.png` | `/cyber` | IOC dashboard, connected entities with confidence, enrichment panel, cyber relationship graph |
| `products-intsum.png` | `/products` | Generated INTSUM with Bottom Line, calibrated probability language, and Markdown/PDF export |
| `topic-mindmap.png` | Data Sources | Radial mind-map with LLM-named topic clusters |
| `collection-plan.png` | `/collection-plans` | PIR-derived plan: refined requirement with EEIs → assigned sources → per-source run status |

**Two shots are honest about current limitations** rather than staged around
them: the geo popup shows a relationship rather than a marker profile with
MGRS/geo-confidence, and the cyber enrichment panel lists its providers but not
their values (enrichment is cached server-side but is not written back to the
entity properties the detail view reads — see the backlog).

Use representative, non-sensitive data. The seeded `demo-sentinel` project is
the safest source and is reproducible by anyone cloning the repo.
