# Screenshots

The root `README.md` renders the six images in this directory. They come from
two places, and it matters which:

| Filename | View | Captured | What it shows |
|----------|------|----------|---------------|
| `hero.png` | — | generated | README banner, 2400x840. Built from `hero.html` over the geo map; regenerate with `node docs/screenshots/make-hero.js` |
| `network-graph.png` | `/network` | by hand | Shortest path between two entities, the evidence behind one edge — claim, confidence, corroboration, source grade, method, basis — and the Graph-RAG assistant answering *why* a vessel behaved as it did |
| `geo-aoi.png` | `/geo` | by hand | 398 locations / 53 geocoded / 279 connections, layer and temporal controls, and a Graph-RAG answer about an incident on the map |
| `collection-plan.png` | `/collection-plans` | by hand | PIR-derived plan: refined requirement → assigned sources → per-source run status, successes and failures both |
| `cyber-enrichment.png` | `/cyber` | Playwright | IOC dashboard, connected entities with confidence, GeoIP/RDAP enrichment, cyber relationship graph |
| `products-intsum.png` | `/products` | Playwright | Generated INTSUM with Bottom Line, calibrated probability language, Markdown/PDF export |
| `topic-mindmap.png` | Data Sources | Playwright | Radial mind-map over 5,258 entities in 612 thematic clusters |

## The hero banner

`hero.png` is generated, not photographed:

```bash
node docs/screenshots/make-hero.js                 # uses geo-aoi.png as backdrop
HERO_SHOT=docs/screenshots/network-graph.png \
HERO_POS="62% 78%" node docs/screenshots/make-hero.js   # swap the backdrop
```

It composes `hero.html` — wordmark, the collect→extract→graph→analyze cycle, a
graded evidence claim, and the local-first line — over a darkened screenshot.
Editing the copy means editing `hero.html` and re-running; the copy is not
duplicated anywhere else. Colours come from the app's own Tailwind tokens
(`navy-900`, `accent-periwinkle`) so the banner cannot drift from the product.

The backdrop defaults to the geo map for a compositional reason worth keeping:
the banner is 2.9:1 and an app window is portrait, so any crop that removes the
sidebar makes it *more* portrait. A world map is landscape already. The right
edge carries a hard scrim because `object-fit: cover` always fits the full
1714px window width into 2400px — no `object-position` can frame the side panels
out, and without the scrim the brightest text on the banner reads "No clusters
found. No relationships found."

**Of the six view screenshots, the first three are hand-captured and are not
reproducible from a clean clone.** They show live Graph-RAG answers and an interactively-found path, which
depend on a project that has really collected and on a working LLM provider.
Nothing in this repo regenerates them; treat them as artefacts, and recapture by
hand if the UI changes enough to make them wrong.

The last three come from `tests/e2e/capture-docs.spec.ts`, which drives the
interaction each shot needs rather than grabbing an empty view:

```bash
# stack up, then:
cd backend  && uv run python scripts/seed_demo.py
cd frontend && CAPTURE_PROJECT_ID=demo-sentinel CAPTURE_IOC=45.83.12.7 \
               npx playwright test capture-docs.spec.ts \
               -g "cyber-enrichment|products-intsum|topic-mindmap"
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

## What these shots do not hide

Staging around a defect makes the screenshots lie about the product, so these
are left showing it:

- **`collection-plan.png` shows failed sources** next to successful ones, and
  the refinement analysis as raw markdown. That rendering is fixed in the app —
  it now goes through the `Markdown` component behind a collapsed disclosure —
  but this image predates the fix and has not been retaken.
- **Topic names in `topic-mindmap.png` are raw TF-IDF keywords** ("wikipedia /
  wiki / org"), not model-written labels. Refinement falls back when the
  configured provider is rate-limited; the tree reports `label_source` so this
  is visible rather than silent (see `tests/test_topic_label_provenance.py`).

The cyber shot is deliberately taken against `demo-sentinel` rather than a crawl
project, and that is a limitation worth naming: on real collected data the IOC
table is currently dominated by ordinary web domains lifted from page furniture,
including hostnames corrupted by percent-encoding (`2fen.wikipedia.org` from an
encoded `/`). Until URL/Domain extraction distinguishes an observable from a
document's own provenance, that view is not representative.

Use representative, non-sensitive data. The seeded `demo-sentinel` project is
the safest source and is reproducible by anyone cloning the repo.
