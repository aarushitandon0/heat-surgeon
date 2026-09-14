# CLAUDE.md

Working agreement for this repo. Read `SPEC.md` (revision 3) for the full specification — this file is the operating rules.

## What this is

**Heat Surgeon** — takes one real street, pulls its real satellite surface temperature, calibrates a heat model to that street's own neighbourhood, searches thousands of redesign layouts under real space and budget constraints, and returns the best one in 3D with a modelled temperature drop and a cost range.

Hackathon project. 10-day build. NextStep Hacks 2026, theme "Earth Forward."

## Stack

**Python 3.11** (not 3.14 — geospatial wheel availability is not worth gambling on; 3.12 acceptable), FastAPI, pydantic v2, numpy, scipy, DEAP, rasterio, uvicorn, plus `earthengine-api` and/or `pystac-client` + `planetary-computer` depending on active adapter.

Frontend: React 18 + TypeScript + Vite, three.js via @react-three/fiber + drei, MapLibre GL, zustand, recharts.

## Rules that override convenience

### 1. Real data or clearly-labelled nothing
Never fabricate, simulate, mock, or interpolate a temperature, cost, or land-cover value into anything that reaches the UI or a demo. If data is unavailable, surface the failure and say which street's cached data is being used instead. A fake number in a demo is the one unrecoverable failure mode of this project.

Test fixtures in `tests/` may use synthetic arrays. Anything under `backend/fixtures/streets/` must be really pulled data.

### 2. The scope contract is binding
`SPEC.md §1` defines Tier 1 / 2 / 3. Do not start work in a tier until the previous tier runs end to end. If asked to add something from Tier 3 while Tier 1 is incomplete, say so and finish Tier 1 first.

### 3. Satellite access is an interface, not a vendor
All satellite reads go through the `SurfaceTemperatureSource` / `LandCoverSource` protocols in `app/data/sources.py`. Never call `ee` directly from a router, the model layer, or the optimizer. Two implementations exist: `EarthEngineSource` (preferred, needs a registered GCP project and browser auth) and `PlanetaryComputerSource` (public STAC, anonymous signing, no account). Switching between them must be a config change.

### 4. Fixtures first, network second
`USE_LIVE_DATA` defaults to `false`. Every external call goes through `app/data/cache.py`, keyed on `(source_adapter, product, bbox, date_range)`. Re-running the same street must never re-hit the network. `prefetch` caches the full 2 km window — Landsat and Sentinel-2 together, in one run. The demo path is the offline path.

### 5. Contracts are frozen
All request/response shapes live in `backend/app/contracts.py`, mirrored in `frontend/src/types/contracts.ts`. Changing a shape means changing both in the same commit, and saying so explicitly.

### 6. Every physical quantity carries its unit suffix
Every field expressing a physical quantity carries its unit suffix: `temp_delta_c`, `cost_inr_low`, `rmse_holdout_c`, `cell_size_m`, `t_base_c`, `k_canopy_c_per_fraction`. No bare `temp`, `cost`, or `rmse` anywhere in a contract, ever.

Exempt: dimensionless counts, indices and ratios (`scene_count`, `valid_pixels`, `n_pixels_fit`, `generation`, `cells`, `months`, `r2_holdout`), and fields whose type already encodes the unit (`BBoxWGS84`, `PointUTM`, `AffineUTM`). `best_fitness_score` is a dimensionless scalarized objective, not a physical quantity, and is never displayed as one.

This applies to Python fields, TypeScript fields, and variable names in numeric code.

### 7. Constants are cited or marked as assumptions
Every albedo value, cooling coefficient, NDVI threshold, QA cut-off, and cost figure lives in `backend/app/config.py`. Each one is either cited in `docs/sources.md`, or marked in `config.py` with an `# ASSUMPTION:` comment and logged in `docs/methodology.md` with its value, the reasoning, and what changing it would change. No magic numbers inline. Never invent a source to avoid writing an assumption down.

### 8. Calibrate on the neighbourhood, apply to the street
Never fit the four model parameters on a single street segment's handful of pixels — a 150 m street is ~5 delivered pixels and 1–2 independent measurements. Fit on 90 m calibration cells across a 1.5–2 km window, then apply at street resolution. The albedo coefficient is never fitted: it comes from published field measurement, as a low/high band. See `SPEC.md §5.1–5.2`.

### 9. Always report error
Any calibration returns `rmse_holdout_c` alongside `rmse_mean_baseline_c`, and the UI displays both. A prediction shipped without its error bar is not finished.

### 10. Always report baselines
The GA result is meaningless alone. `random_layout()` and `greedy_layout()` run at matched budget, and all three appear in the result payload and on screen.

### 11. Label measured vs modelled, everywhere
Three resolutions coexist: 30 m delivered (100 m native) measured, 90 m calibration cells across a 2 km window, 2 m design. The rendered before/after surface is a **model output at design resolution, not a measurement**. Every view that shows it says so. `OptimizationResult.resolution` carries the fields so the frontend cannot forget. See `SPEC.md §5.3`.

### 12. Surface temperature, mid-morning
Landsat measures land surface temperature at a 10:57 IST overpass (measured median over Pune). Label it as surface temperature in every string, comment, and doc. Never write copy implying a person will feel that delta, and never imply it is afternoon peak heat.

### 13. Composites have provenance, not a date
We composite per-pixel medians across multiple scenes and collections, so there is no single `capture_date` or `source`. Use the `Provenance` object: `date_range`, `capture_dates[]`, `scene_ids[]`, `collections[]`, `platforms[]`, `scene_count`, `compositing`, `cloud_masking`. `collections` holds each adapter's native IDs verbatim, never normalised. Never display a single scene ID as if it were the whole dataset.

### 14. Pune's calendar, not a generic summer
Default date window is 1 March – 31 May across 3 years. June–September is monsoon and cloud filtering leaves nothing usable. Mask per pixel on `QA_PIXEL` (cloud, shadow, cirrus, dilated cloud), drop fill pixels and `ST_QA` outliers. Scene-level cloud filtering alone is not sufficient.

## Design rules

Full spec in `SPEC.md §9`. The short version:

- Read design tokens from `frontend/src/styles/tokens.css`. Never hardcode a hex value in a component.
- The five-stop thermal ramp (`--t-00` … `--t-100`) is for **measured or modelled data only**. If it appears on anything else, it's a bug.
- `--signal` (#7FD1DE) appears exactly once in the whole app: the final temperature delta readout.
- IBM Plex Mono is for numeric values only — temperatures, coordinates, costs, scene counts, generation counters. Never for labels, buttons, or headings.
- The acquisition decode resolves a **provenance stack** (scene count, seasons, collections, compositing method), never a single fabricated scene ID.
- Exactly two motion moments exist: the acquisition decode (stage 01) and the before→after reveal (stage 03). Do not add a third. No section entrance animations, no hover lifts, no scroll reveals.
- `prefers-reduced-motion` skips both and jumps to the final state.
- Cost is always shown as a range, never a midpoint, always labelled an estimate.
- Sentence case everywhere. No all-caps labels, no middle-dot meta strings, no arrows in button text, no emoji, no glassmorphism, no gradient decoration.
- Copy is plain and instrument-like: "Searching layouts. Generation 142 of 400." not "Optimizing your green future."

## Working style

- Before writing code for a new module, state the plan in two or three sentences and the files you'll touch. Then write it.
- Small commits, conventional prefixes (`feat:`, `fix:`, `data:`, `ui:`, `docs:`).
- When you make an assumption (building heights, a missing OSM tag, an unsourced cost), write it into `docs/methodology.md` in the same commit. That doc is a judging asset, not an afterthought.
- Prefer boring, working code over clever code. This ships in 10 days and gets read on a projector.
- Every numeric function gets a test with a hand-checked expected value. Especially the Landsat Kelvin→Celsius scaling — if that is wrong, every number in the product is wrong.
- If something in `SPEC.md` turns out to be wrong or infeasible once real data lands, say so directly and propose the alternative. The spec is a plan, not scripture — revision 2 exists because revision 1 had four contract bugs and the wrong months for Pune, and revision 3 because revision 2 would have resampled measured values onto a lat/lon grid.

## Commands

```bash
# backend
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && pytest -q
cd backend && python -m app.data.prefetch --street pune-fc-road   # caches the 2km window

# frontend
cd frontend && npm run dev
cd frontend && npm run typecheck
```

## Current state

Update this section as tiers complete.

- [ ] Tier 1 — real data → calibrated model → GA → 2D result, offline from fixtures
- [ ] Tier 2 — 3D scene, reveal moment, live WS streaming, street picker
- [ ] Tier 3 — NSGA-II Pareto front, thermal sharpening, ward-scale batch

Active satellite adapter: `planetary_computer`, decided Day 1 (2026-09-14). No Earth Engine project or credentials exist on the build machine. `EarthEngineSource` is written but has not been run against a live account.

Day 4 (2026-09-14):
- **Backend.** Serves the full §7 API from fixtures. Four streets are cached: Bajirao Road (dense commercial), North Main Road (leafy residential), Karve Road (wide arterial), FC Road (mixed). Tier 1 still needs the 2D result view.
- **Footprints.** OSM unioned with Overture non-OSM footprints (duckdb). The Sentinel-2 B11 escalation rule is retired.
- **Costs.** Only trees are priced; coating is unpriced, so costs are nullable and the headline has no cost.
- **Cross-sections.** From PMC USDG templates on right of way measured from footprints, labelled `published_design`.

Day 5 (2026-09-14):
- **Frontend.** Stages 00–03 run against the real backend through the Vite proxy.
  - The provenance stack decodes for as long as the thermal fetch runs.
  - Stage 02 streams the convergence curve over the WebSocket.
  - Stage 03 is a 2D heat grid with the before/after reveal, cost range or "Not priced", model error with its baseline, and all four comparison arms.
- **Checks.** Run `npm test` for hand-checked numeric tests and `npm run check:design` for hex, ramp, `--signal`, motion, emoji, arrow and middle-dot rules.
- **Next.** Tier 1 still needs its §1 checklist confirmed end to end offline.

Day 6 (2026-09-14):
- **3D scene, before state only.** Stage 03 opens on extruded buildings over a shader ground of `before_lst_c`, with the searched layout as instanced markers.
  - 6 draw calls in total.
  - On Bajirao Road (Iris Xe), 97 fps and p95 15.5 ms while orbiting at pixel ratio 2.
  - The reveal is not started; the 2D grid still holds before/after.
- **Heights.** Untagged buildings are estimated from footprint area (`estimated_from_area`), from a table derived from 188 tagged OSM buildings.