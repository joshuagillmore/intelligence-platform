# Screenshots

The root `README.md` renders the six images in this directory. They are captured
from a running instance with a **reproducible Playwright spec** rather than by
hand, so they can be refreshed after a UI change.

## Two sources, on purpose

No single project produces the best six shots, and pretending otherwise is how
the collection shot ended up being a photograph of an empty dashboard.

- **`demo-sentinel`** — the seeded fixture (`backend/scripts/seed_demo.py`).
  Small, curated and reproducible by anyone cloning the repo. It is the better
  source wherever a shot needs a *coherent* story: a critical IOC that resolves
  to a real ASN, a saved INTSUM with citations.
- **A real collection project** — hundreds of crawled documents. The better
  source wherever a shot needs *volume*: a graph with visible structure, a map
  with real spread, a collection plan with sources that actually ran and failed.

```bash
# stack up, then — curated shots:
cd backend  && uv run python scripts/seed_demo.py
cd frontend && CAPTURE_PROJECT_ID=demo-sentinel CAPTURE_IOC=45.83.12.7 \
               npx playwright test capture-docs.spec.ts -g "cyber-enrichment|products-intsum"

# volume shots, against a project that has really collected:
cd frontend && CAPTURE_PROJECT_ID=<uuid> CAPTURE_FOCUS_ENTITY=<entity-uuid> \
               CAPTURE_PLAN="<text in the plan title>" \
               npx playwright test capture-docs.spec.ts -g "network-graph|geo-aoi|collection-plan|topic-mindmap"
```

## Env knobs

| Variable | Purpose |
|----------|---------|
| `CAPTURE_PROJECT_ID` | Project to capture against (`demo-sentinel` for the seeded fixture) |
| `CAPTURE_FOCUS_ENTITY` | Entity id to select in the graph shot — pick a high-degree one |
| `CAPTURE_IOC` | Indicator to expand in the cyber shot |
| `CAPTURE_ISLAND_DEGREE` | Degree floor for the graph (default 1). At 0 an isolated-heavy project renders as a starfield |
| `CAPTURE_EGO_HOPS` | Ego-highlight radius (default 4). Low values dim everything outside the selected entity's neighbourhood, **edges included** — a fully connected graph then photographs as a grey field |
| `CAPTURE_PLAN` | Text matching the collection plan to open, so the shot is not whichever plan sorts first |

## Current set

| Filename | View | Source | What it shows |
|----------|------|--------|---------------|
| `network-graph.png` | `/network` | collection | 389 nodes / 500 edges of a connected core, entity selected with its 30 relationships and evidence links |
| `geo-aoi.png` | `/geo` | collection | 398 locations, 53 geocoded, 279 connection lines; layer control, temporal window, area query |
| `cyber-enrichment.png` | `/cyber` | `demo-sentinel` | IOC dashboard, connected entities with confidence, GeoIP/RDAP enrichment, cyber relationship graph |
| `products-intsum.png` | `/products` | `demo-sentinel` | Generated INTSUM with Bottom Line, calibrated probability language, Markdown/PDF export |
| `topic-mindmap.png` | Data Sources | collection | Radial mind-map over 5,258 entities in 612 thematic clusters |
| `collection-plan.png` | `/collection-plans` | collection | PIR-derived plan: refined requirement with EEIs → assigned sources → per-source run status |

## What these shots do not hide

Staging around a defect makes the screenshots lie about the product, so two are
left showing it:

- **Topic names in `topic-mindmap.png` are raw TF-IDF keywords** ("wikipedia /
  wiki / org"), not model-written labels. Refinement is falling back because the
  configured provider is rate-limited — the tree reports `label_source` so this
  is visible rather than silent (see `tests/test_topic_label_provenance.py`).
- **`collection-plan.png` shows failed sources** alongside successful ones, and
  a refined PIR rendered as raw markdown.

The cyber shot is deliberately taken against `demo-sentinel` rather than a crawl
project, and that is a limitation worth naming: on real collected data the IOC
table is currently dominated by ordinary web domains lifted from page furniture,
including hostnames corrupted by percent-encoding (`2fen.wikipedia.org` from an
encoded `/`). Until URL/Domain extraction distinguishes an observable from a
document's own provenance, that view is not representative.

Use representative, non-sensitive data. The seeded `demo-sentinel` project is
the safest source and is reproducible by anyone cloning the repo.
