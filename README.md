# Heat Surgeon

Heat Surgeon takes one real street and does following things:

1. Pulls the street's measured satellite land surface temperature.
2. Calibrates a surface temperature model on the street's own 2 km neighbourhood.
3. Searches thousands of tree and reflective-coating layouts that fit the street's real cross-section and a fixed budget.
4. Returns the best layout in 3D, with:
   - a modelled temperature change, given as a low/high band
   - the model's hold-out error
   - three baseline layouts at the same budget for comparison
   - a cost range wherever a sourced rate exists

It runs fully offline from committed fixtures for four streets in Pune, India.

Every number in the product comes from pulled data or a cited constant. Anything that could not be cited is written down as an assumption. See [docs/methodology.md](docs/methodology.md) and [docs/sources.md](docs/sources.md).

---

## Contents

- [What is measured and what is modelled](#what-is-measured-and-what-is-modelled)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Quick start (offline)](#quick-start-offline)
- [Configuration](#configuration)
- [Fixture streets](#fixture-streets)
- [Data pipeline](#data-pipeline)
- [Heat model](#heat-model)
- [Interventions](#interventions)
- [Street design grid and cross-section](#street-design-grid-and-cross-section)
- [Optimizer and baselines](#optimizer-and-baselines)
- [Costs](#costs)
- [API reference](#api-reference)
- [Frontend](#frontend)
- [Command-line tools](#command-line-tools)
- [Adding a street](#adding-a-street)
- [Testing](#testing)
- [Results on the fixture streets](#results-on-the-fixture-streets)
- [Limitations](#limitations)
- [Data licences and attribution](#data-licences-and-attribution)

---

## What is measured and what is modelled

Three resolutions coexist. The interface labels each one wherever it appears.

| Layer | Resolution | What it is |
|---|---|---|
| Measurement | 30 m delivered, 100 m native | Landsat 8/9 land surface temperature: a per-pixel median over roughly 30 scenes. |
| Calibration | 90 m cells (3 × 3 Landsat cells), 484 per 2 km window | Where the model coefficients are fitted. |
| Design | 2 m cells | The resolution at which a tree or a coating is placed. |
| Rendered before/after surface | 2 m | **A model output at design resolution, not a measurement.** |

Two further points hold throughout:
- **Surface, not air.** The quantity is land surface temperature, not the air temperature a person feels.
- **Mid-morning, not peak.** It is taken at Landsat's 10:57 IST overpass, the median acquisition time over Pune, not at the afternoon peak.

---

## Architecture

```
┌──────────────────────────┐      ┌──────────────────────────┐      ┌────────────────────────────┐
│ Frontend                 │      │ FastAPI backend          │      │ Data layer                 │
│ React 18 + TypeScript    │ REST │ pydantic v2 contracts    │      │ SurfaceTemperatureSource   │
│ Vite, zustand            │◀────▶│ job threads + WebSocket  │◀────▶│ LandCoverSource            │
│ three.js via R3F + drei  │  WS  │                          │      │  ├ PlanetaryComputerSource │
│ recharts                 │      │                          │      │  └ EarthEngineSource       │
└──────────────────────────┘      └────────────┬─────────────┘      │ OSM Overpass, Overture     │
                                               │                    │ Disk cache (fixtures/)     │
                                  ┌────────────▼─────────────┐      └────────────────────────────┘
                                  │ Heat model (numpy)       │
                                  │ OLS on 90 m cells        │
                                  │ + intervention delta     │
                                  └────────────┬─────────────┘
                                  ┌────────────▼─────────────┐
                                  │ Optimizer (DEAP)         │
                                  │ GA + random, greedy,     │
                                  │ design-guideline arms    │
                                  └──────────────────────────┘
```

- **Satellite access is behind two protocols** (`app/data/sources.py`). Routers, the model and the optimizer never call a vendor SDK, so switching adapters is a config change.
- **Every external call goes through one disk cache** (`app/data/cache.py`), keyed on `(source_adapter, product, bbox, date_range)`. With `USE_LIVE_DATA=false`, the default, a cache miss raises an error; nothing is fetched and nothing is substituted.
- **Request and response shapes are pydantic models** in `backend/app/contracts.py`, mirrored field for field in `frontend/src/types/contracts.ts`. Every physical quantity carries a unit suffix (`temp_delta_c_low`, `cost_inr_high`, `rmse_holdout_c`, `cell_size_m`).

---

## Repository layout

```
backend/
  app/
    main.py               FastAPI app, CORS, router wiring
    contracts.py          every request/response model
    config.py             settings and every constant (cited or marked ASSUMPTION)
    pipeline.py           street services: summaries, geometry, thermal, calibration, result assembly
    jobs.py               optimizer jobs on worker threads, message log for the WebSocket
    routers/              street.py, calibrate.py, optimize.py, errors.py
    data/
      sources.py          source protocols, Landsat/S2 scaling, masking, median compositing
      planetary.py        PlanetaryComputerSource (public STAC, anonymous signing)
      earth_engine.py     EarthEngineSource (needs a GCP project)
      cache.py            keyed .npy + meta.json disk cache
      osm.py              Overpass buildings and highways
      footprints.py       Overture non-OSM footprints via DuckDB, merged with OSM
      landcover.py        1 m surface classification, exact area shares per block
      cross_section.py    right of way from footprints, PMC USDG templates
      heights.py          building heights for the 3D scene
      fixtures.py         loads a cached street window, never touches the network
      prefetch.py         CLI: cache a street's 2 km window
    model/
      heat.py             baseline model, OLS fit, pairwise contrasts
      validate.py         calibration cells, hold-out split, error reporting, CLI
      delta.py            per-cell intervention effects
      cost.py             cost ranges, unpriced interventions
    optimizer/
      encoding.py         street-aligned design grid, genome, repair, evaluation
      ga.py               single-objective GA (DEAP), comparison CLI
      baselines.py        random, greedy, design-guideline layouts
      nsga2.py            multi-objective variant (not wired to the API)
      render.py           matplotlib layout figures
  fixtures/
    streets/*.json        street manifests
    cache/                cached Landsat, Sentinel-2, OSM and Overture pulls
  tests/
frontend/
  src/
    app/                  shell and header
    stages/               Locate, Diagnose, Optimize, Operate
    scene/                R3F scene: shader ground, extruded buildings, instanced markers
    ui/                   Numeral, Decode, Readout, ThermalScale, HeatCanvas
    lib/                  api client, formatting, geometry, motion, thermal ramp
    store/                zustand state machine
    types/contracts.ts    mirror of backend contracts
    styles/tokens.css     design tokens
  scripts/check-design.mjs
  tests/
docs/
  methodology.md          every assumption, its value, reasoning and effect
  sources.md              every cited constant with its source
  figures/                calibration scatters and layout comparisons per street
```

---

## Requirements

| Component | Version |
|---|---|
| Python | 3.11 (3.12 works). Avoid newer releases: geospatial wheels lag behind them. |
| Node.js | 22.18 or newer; built and tested on 24. The frontend tests run `.ts` files directly with `node --test`. |
| OS | Windows, macOS or Linux |

Network access is needed only to install dependencies and to prefetch new streets. The four fixture streets run without it.

---

## Quick start (offline)

### Backend

```bash
cd backend
python3.11 -m venv .venv            # Windows: py -3.11 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The interactive API docs are at http://127.0.0.1:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` and `/ws` to `127.0.0.1:8000`, so the browser stays on one origin.

### Running the pipeline

1. **Pick a street** (stage 00, Locate).
2. **Diagnose it** (stage 01). The window thermal grid loads, the provenance readout resolves, and calibration returns its hold-out error.
3. **Start the search** (stage 02, Optimize). The convergence curve streams over the WebSocket. With the defaults (trees only, population 120, 400 generations) the search took 116 s through the job runner on an Intel Iris Xe laptop, and up to 174 s when the machine was busy. "Short search" runs 150 generations in about 25 s and, at the default budget, reached the same layout value on all four fixture streets.
4. **Read the result** (stage 03, Operate). It has:
   - the 3D scene, and a 2D before/after grid
   - the modelled change as a band, with the model error beside it
   - all four comparison arms

---

## Configuration

All settings live in `backend/app/config.py`. Three are read from the environment:

| Variable | Default | Effect |
|---|---|---|
| `USE_LIVE_DATA` | `false` | When `true`, a cache miss may reach the network. When `false`, it raises `CacheMiss`. |
| `SOURCE_ADAPTER` | `planetary_computer` | `planetary_computer` or `earth_engine`. |
| `EARTH_ENGINE_PROJECT` | unset | Google Cloud project ID. Required only for the `earth_engine` adapter, after `earthengine authenticate`. |

The Planetary Computer adapter needs no account: its STAC API is public, and asset URLs are signed anonymously.

**Earth Engine status.** The Earth Engine adapter is implemented but has not been run against a live account. All fixtures were pulled with `planetary_computer`.

---

## Fixture streets

Four streets in Pune, chosen for different heat profiles. Each has a manifest in `backend/fixtures/streets/` and a fully cached 2 km window: Landsat, Sentinel-2, OSM and Overture.

| ID | Street | Profile |
|---|---|---|
| `pune-bajirao-road` | Bajirao Road | dense commercial |
| `pune-north-main-road` | North Main Road | leafy residential |
| `pune-karve-road` | Karve Road | wide arterial |
| `pune-fc-road` | FC Road (Gopal Krushna Gokhale Path) | mixed |

---

## Data pipeline

### Landsat 8/9 Collection 2 Level 2: surface temperature

- **Date window.** 1 March to 31 May in 2024, 2025 and 2026. June to September is monsoon, and cloud masking leaves almost nothing usable.
- **Grid.** Each window is 67 × 67 Landsat cells (2,010 m square), snapped to Landsat's native UTM grid (EPSG:32643 for Pune). A window that is not on that grid raises an error; measured values are never resampled.
- **Scene pre-filter.** Scenes with `eo:cloud_cover` of 40% or more are skipped.
- **Per-pixel masking.** An observation is dropped when any of the following holds:
  - a `QA_PIXEL` bit for fill, dilated cloud, cirrus, cloud or cloud shadow is set
  - its `ST_B10` or surface-reflectance value is fill
  - its `ST_QA` uncertainty is above 5 K
- **Scaling.** Tested against the USGS worked example, DN 44,947 → 302.6 K:
  ```python
  celsius = raw * 0.00341802 + 149.0 - 273.15
  ```
- **Compositing.** A per-pixel median over the observations that survive masking. A pixel with fewer than 5 clear observations is null.
- **Broadband albedo.** Computed from OLI surface reflectance with the Liang (2001) coefficients. It is used only as a diagnostic, never in the model.

### Sentinel-2 L2A: land cover

- **Date window.** The same as Landsat.
- **Masking.** Per pixel on the scene classification layer: SCL classes 0, 3, 8, 9 and 10 (no data, cloud shadow, medium and high cloud, cirrus) are dropped.
- **Offset.** `BOA_ADD_OFFSET` is read from each product's own `MTD_MSIL2A.xml` and applied. Planetary Computer serves digital numbers without it; this was checked against scenes before and after processing baseline 04.00. NDVI computation refuses to run unless the offset was applied.
- **Compositing.** Only the per-pixel median of B4 (red) and B8 (NIR) is cached.

### Geometry

- **OpenStreetMap via Overpass.** Building footprints and highway ways.
- **Overture Maps buildings, release 2026-08-19.0.** Its Microsoft ML Buildings and Google Open Buildings footprints are read from GeoParquet on S3 with DuckDB, and unioned with the OSM footprints.
  - A non-OSM footprint is dropped as a duplicate when its centroid lies inside an OSM footprint, or within 5 m of an OSM footprint's centroid.
  - Every building keeps its `footprint_source`.

### Provenance

A composite has no single date or scene. Every satellite product therefore carries a `Provenance` object with these fields:

- `date_range`, `months`
- `scene_count`, `capture_dates[]`, `scene_ids[]`
- `collections[]` (verbatim adapter IDs) and `platforms[]`
- `compositing` and `cloud_masking` descriptions
- `overpass_local_time`
- native and delivered resolution
- `source_adapter`

---

## Heat model

### Surface classes

Each 1 m sub-cell of the window gets exactly one class, in this priority order:

| Class | Rule |
|---|---|
| canopy | Sentinel-2 NDVI ≥ 0.5 |
| built | merged building footprint |
| paved | OSM highway way, buffered to its tagged width, else its lane count × 3.5 m, else a default for its road class |
| water | NDVI < 0 |
| bare | everything else |

Area shares are then summed exactly over each 90 m calibration cell.

### Baseline model

```
lst_pred_c = t_base_c
             − k_canopy_c_per_fraction · canopy_fraction
             + k_built_c_per_fraction  · built_fraction
             + k_bare_c_per_fraction   · bare_fraction
```

- **Reference class.** The shares sum to one, so paved is the reference class: `t_base_c` is a fully paved cell, and each k is a difference from paved.
- **Reparameterisation.** Choosing a different reference changes no prediction and no error. `contrasts` in the calibration response reports every class pair with a standard error.
- **Reported reference.** `fit_reference_class` names the best-supported class, the one with the largest mean share.

### Calibration

- **Cells.** 3 × 3 Landsat blocks (90 m), close to the 100 m native thermal resolution. Fitting 30 m land cover against a 100 m thermal signal attenuates every coefficient, so the model is never fitted on single pixels or on one street's pixels.
- **Usable cells.** A cell is used when it has a Landsat value, full Sentinel-2 coverage, and no more than 25% water.
- **Split.** A seeded random 20% of cells is held out. Ordinary least squares is fitted on the rest.
- **Error reporting.** Every calibration reports:
  - `rmse_holdout_c`: error on the held-out cells
  - `rmse_mean_baseline_c`: error from predicting every held-out cell as the mean of the fitting cells
  - `r2_holdout`
- **Standard errors.** They assume independent residuals, and neighbouring 90 m cells are not fully independent. Treat them as a diagnostic, not as confidence intervals.

### Why albedo is not fitted

Fitted from observation, the albedo coefficient came out with the wrong sign. In the pre-monsoon season the brightest ground is also the driest and hottest, so a fitted coefficient measures dryness.

The effect of raising albedo is taken instead from field measurement (Ko et al. 2022), carried as a band:
- **Low end:** 5.0 °C per unit albedo, measured at 09:00.
- **High end:** 27.0 °C per unit albedo, measured at 15:00.

The 10:57 overpass lies between the two.

---

## Interventions

Each intervention changes the modelled surface temperature of the design cells it covers.

| Intervention | Effect | Status |
|---|---|---|
| `tree` | Cells within 4 m of the pit (an 8 m crown) become canopy. Gain per crown cell is −k_canopy over paving, −k_canopy − k_bare over bare ground, −k_canopy − k_built over a roof, and zero over existing canopy. Overlapping crowns count once. | enabled |
| `reflective_pavement` | ΔLST = −k_albedo · Δalbedo. Coating albedo 0.50; carriageway assumed aged asphalt (0.10–0.20), footway aged concrete (0.20–0.35). The more-cooling end pairs the largest albedo gain with the high coefficient; the less-cooling end pairs the smallest gain with the low coefficient. A coated cell under a new crown gains nothing. | enabled |
| `permeable_pavement` | Paved footway becomes bare-like ground (k_bare). That is a warming change in the pre-monsoon fit, and pervious concrete is also less reflective. | excluded from the action set |
| `shade_structure` | No cited effect and no fitted coefficient. | excluded from the action set |

A layout's temperature change is the mean change over all design cells. Because the model is linear, this equals applying the 90 m coefficients to the changed area shares.

`temp_delta_c_low` is the more-cooling end of the band and `temp_delta_c_high` the less-cooling end. They are equal when no coating is used.

The optimizer ranks layouts on the conservative end, `temp_delta_c_high`.

### Before surface

The "before" surface is modelled, not measured. For each 2 m design cell it is:
- the baseline model's value for the cell's surface class,
- plus the measured-minus-modelled residual of the 90 m calibration cell the design cell sits in.

The residual keeps local heat that the model does not explain.

---

## Street design grid and cross-section

### Design grid

- **Segment.** 200 m centred on the longest straight OSM way carrying the street's `osm_name`.
- **Size.** 40 m across in 2 m cells, which gives 100 × 20 = 2,000 cells.
- **Orientation.** The grid is rotated to the segment's bearing. Rows advance along the street; columns advance to its right.
- **Cap.** 4,000 cells. A larger grid raises an error rather than being coarsened.

### Cross-section

The cross-section decides where each intervention may go. It is chosen in this order, and each result is labelled with its `CrossSection.source`:

1. **`osm_tag`.** Used when the way tags a carriageway width and both sidewalk widths.
2. **`published_design`.** Two steps:
   - The right of way is measured from merged building footprints: at 2 m stations along the segment, the distance to the first building edge within 30 m on each side, median over stations.
   - That width is divided using the widest Pune Municipal Corporation *Urban Street Design Guidelines* (2016) template no wider than it: 9A, 12A, 15A, 18A, 21A, 24A or 30A. Spare width goes to the outer footways.
   - This applies the city's design standard to the measured width. It is not an as-built survey.
3. **`default_assumption`.** Carriageway from lane count or road class, footways at the IRC:103 minimum, and no tree pits.

### Placement rules

- Trees go only in `tree_pit` bands, never on a building or on existing canopy, and at least 8 m apart (IRC:SP:21).
- Coatings go only on carriageway, bus stop, footway or cycle track inside the right of way.
- Nothing is placed on private property outside the right of way.

---

## Optimizer and baselines

### Encoding and repair

- **Genome.** A flat `int8` array with one gene per design cell. States: `0` unchanged, `1` tree, `2` reflective pavement, `3` permeable pavement, `4` shade structure.
- **`repair()`.** Projects any genome into the feasible set instead of rejecting it:
  - a state not allowed on its cell becomes unchanged
  - trees closer than the minimum spacing are thinned, in random order
  - interventions beyond the budget are removed at random
- **When repair runs.** After initialisation, after crossover and after mutation.

### Genetic algorithm (`app/optimizer/ga.py`)

| Parameter | Default |
|---|---|
| Population | 120 |
| Generations | 400 |
| Selection | tournament, size 3 |
| Crossover | two-point, p = 0.7 |
| Mutation | p = 0.3; a Poisson(2) number of actionable genes set to a random allowed state |
| Elitism | 4 |

The fitness score is a dimensionless scalarized objective. It is never displayed as a physical quantity.

```
fitness_score = temp_drop_c − cost_weight_c_per_inr · cost_inr_high
```

- `temp_drop_c` is the conservative cooling, −`temp_delta_c_high`.
- The cost term is zero whenever the layout's cost is null.
- The temperature and cost objectives are kept separate on every individual, so a multi-objective selector can use them directly.

### Comparison arms

Every arm gets the same budget: the same number of trees and the same number of coated cells. The tree count is capped at the most trees the plantable bands hold at 8 m spacing.

| Arm | Layout |
|---|---|
| `random` | The budget on uniformly random valid cells. The reported value is the mean over 30 seeds. |
| `greedy` | One intervention at a time on the currently hottest valid cell. This baseline is weak by design: in a linear model an intervention's gain does not depend on how hot the cell is. |
| `design_guideline` | What a competent designer would do without optimisation: trees split between the two sides and evenly spaced along each plantable strip, with coating on a contiguous run of the widest paved rows. |
| `ga` | The searched layout. It is **not** seeded with the guideline layout, so matching or beating the guideline is not guaranteed by construction. |

---

## Costs

Only street trees are priced: **₹3,720 to ₹5,902 per tree**. The source is the Government of Rajasthan's RUIDP *Integrated Schedule of Rates 2023*:
- item 39.30: planting, sapling and one year of maintenance
- items 39.31 to 39.39: tree guard, cheapest to dearest

The scope is planting, guard and first-year care only.

Reflective coating, pervious concrete and shade structures have no sourced Indian rate. Their handling follows from that:
- A layout using any unpriced intervention returns `cost_inr_low` and `cost_inr_high` as `null`, and lists what is missing in `unpriced_interventions`. It never returns an estimated or partial sum.
- `budget_inr_max` is accepted only when every allowed intervention is priced, which means `reflective_cells_max = 0`. It then caps the tree count at the budget divided by the high end of the per-tree range.
- The UI always shows cost as a range labelled an estimate, never as a midpoint.

---

## API reference

Base URL: `http://127.0.0.1:8000`. Every shape is defined in `backend/app/contracts.py`.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/streets` | `StreetSummary[]` |
| `GET` | `/api/ranking` | `StreetRanking`: streets in the calibrated windows ranked by modelled cooling per ₹1 lakh; `404` until `python -m app.ranking` has run |
| `GET` | `/api/street/{id}/geometry` | `StreetGeometry`: buildings with height and footprint source, road, sidewalks, cross-section |
| `GET` | `/api/street/{id}/thermal?scope=window\|street` | `ThermalGrid`: measured LST on Landsat's native grid, `null` where no valid observation survived |
| `POST` | `/api/street/{id}/calibrate` | `CalibrationResult` |
| `POST` | `/api/street/{id}/optimize` | `OptimizeJobHandle` |
| `WS` | `/ws/optimize/{job_id}` | stream of `progress`, then `done` or `error` |
| `GET` | `/api/job/{job_id}/result` | `OptimizationResult`; `409` while still searching |

### Conventions

- **Geometry.** In the street's UTM zone (`EPSG:32643`), in metres. WGS84 appears only in `bbox_*` fields, for display.
- **Grids.** Row-major. On measured grids, row 0 is the north edge. Invalid cells are `null`; there is no separate mask.
- **`AffineUTM`.** Follows rasterio order: `[cell_size, 0, origin_e, 0, -cell_size, origin_n]`.

### Calibrate

```bash
curl -X POST http://127.0.0.1:8000/api/street/pune-fc-road/calibrate \
  -H 'content-type: application/json' \
  -d '{"holdout_fraction": 0.2, "seed": 42}'
```

The response includes:
- `t_base_c` and the three `k_*_c_per_fraction` coefficients
- `k_albedo_low/high_c_per_unit_albedo`, which are published values, not fitted
- `rmse_holdout_c`, `rmse_mean_baseline_c` and `r2_holdout`
- `n_cells_fit` and `n_cells_holdout`
- `fit_reference_class` and `contrasts[]`
- `building_footprint_sources[]`
- `provenance[]`, with one entry for surface temperature and one for land cover

### Optimize

```bash
curl -X POST http://127.0.0.1:8000/api/street/pune-fc-road/optimize \
  -H 'content-type: application/json' \
  -d '{"trees_max": 20, "reflective_cells_max": 150, "budget_inr_max": null,
       "generations": 400, "population": 120, "cost_weight_c_per_inr": 0,
       "run_baselines": true, "seed": 42}'
```

```json
{ "job_id": "3f9c1a7b2d04", "ws_url": "/ws/optimize/3f9c1a7b2d04",
  "grid_shape": [100, 20], "cells": 2000, "states_per_cell": 5 }
```

The job runs on a worker thread.

### WebSocket messages

- **Replay.** Messages are recorded on the job, and a WebSocket replays them from the start. A late subscriber sees the whole run.
- **Throttling.** Progress is sent at most every 0.1 s, plus once for the final generation.
- **Layout preview.** `layout_preview` is set only when the best layout improved since the last message, and is `null` otherwise.

```json
{ "type": "progress", "job_id": "…", "generation": 142, "generations_total": 400,
  "best_fitness_score": 0.79, "best_temp_delta_c_low": -1.52, "best_temp_delta_c_high": -0.79,
  "best_cost_inr_low": null, "best_cost_inr_high": null,
  "layout_preview": [{ "type": "tree", "cells": [[12, 4], [18, 4]] }] }

{ "type": "done", "job_id": "…", "result_url": "/api/job/…/result" }

{ "type": "error", "job_id": "…", "code": "CacheMiss", "message": "…" }
```

### OptimizationResult

- **`baseline_temp_c`, `optimized_temp_c_low/high`, `temp_delta_c_low/high`.** Mean modelled surface temperature over the design area, as a band.
- **`cost_inr_low/high`** (nullable) and `unpriced_interventions`.
- **`model`.** `rmse_holdout_c` and `rmse_mean_baseline_c`.
- **`comparison`.** Four arms, `random`, `greedy`, `design_guideline` and `ga`, sharing one shape. Each carries its band, cost, `trees` and `reflective_cells`, so the budget match can be checked from the payload.
- **`interventions`.** A list of `{type, cells: [[row, col], …]}`.
- **Design grid.** `design_grid` (origin, bearing, cell size, shape), `cross_section` and `plantable_mask`.
- **Surfaces.** `before_lst_c`, `after_lst_c_low` and `after_lst_c_high` lie on the design grid.
- **`resolution`.** Measurement, calibration and design resolution, and `output_kind: "model_output_at_design_resolution"`.
- **`provenance[]`.**

---

## Frontend

React 18 + TypeScript + Vite; zustand for state; three.js through `@react-three/fiber` and `drei`; recharts for the convergence curve.

### Stages

The stage numbers are the pipeline order.

| Stage | Panel | Viewport |
|---|---|---|
| 00 Locate | Street list with profile and cache status. | Street picker. |
| 01 Diagnose | Provenance readout: scene count, seasons, collections, compositing, overpass time. Then calibration coefficients, hold-out error and mean baseline. | Measured window thermal grid, north-up, labelled "measured, 30 m". |
| 02 Optimize | Budget and search settings, and a generation counter. | Live convergence curve of both band ends, and the current best layout. |
| 03 Operate | Result, error bar, cost range or "Not priced", and all four arms. | 3D scene, or the 2D before/after grid drawn along the street. |

### 3D scene (`src/scene/`)

- **Ground.** A shader plane textured with `before_lst_c`, one texel per 2 m cell, mapped through the five-stop thermal ramp. Null cells are discarded.
- **Buildings.** Every footprint from the geometry endpoint, extruded to `height_m` and merged into one geometry. Height comes from, in order:
  - the OSM `height` tag
  - `building:levels` × 3 m
  - a storey count looked up from footprint area, derived from 188 tagged OSM buildings in the four windows
- **Interventions.** Instanced markers: one draw call for trees, drawn as a stake plus an 8 m crown ring, and one for coated cells.
- **Origin.** The scene is centred on the design grid, so large UTM northings do not jitter in GPU floats.
- **Performance.** 6 draw calls and about 7,200 triangles on the largest street. Measured on an Intel Iris Xe at pixel ratio 2 while orbiting: 97 fps, 95th-percentile frame time 15.5 ms.

### Motion

Two animations exist:
- **Acquisition decode.** The provenance readout resolves from scrambled characters. It runs for exactly as long as the thermal request, and scrambled characters never include digits.
- **Before-to-after reveal.** A 1.5 s ease-in-out cubic. The grid interpolation and the delta numeral read the same progress value, so they finish on the same frame.

`prefers-reduced-motion` skips both.

### Design tokens and checks

Colours come from `src/styles/tokens.css`:
- **Thermal ramp** (`--t-00` … `--t-100`): used only for measured or modelled data.
- **`--signal`**: used once, for the final temperature delta.
- **IBM Plex Mono**: numeric values only.

`npm run check:design` scans the source for violations of these rules:
- hardcoded hex values
- ramp colours used on non-data elements
- more than one use of `--signal`
- extra motion
- emoji, arrows in button text, and middle-dot strings

### Scripts

```bash
npm run dev            # Vite dev server on :5173
npm run build          # typecheck + production build
npm run typecheck      # tsc -b
npm run lint           # oxlint
npm test               # node --test on tests/**/*.test.ts
npm run check:design   # design rule scan
npm run build:replay   # static build that replays frontend/public/snapshot/ and never calls a backend
                       # (add -- --base=/your-path/ when hosting under a subpath)
```

---

## Command-line tools

Run these from `backend/` with the virtual environment active.

```bash
# Cache (or re-read) a street's full 2 km window: Landsat, Sentinel-2, OSM and Overture in one run.
python -m app.data.prefetch --street pune-fc-road

# Calibrate on the cached window. Prints coefficients, contrasts and errors,
# and writes docs/figures/<street>-calibration.png.
python -m app.model.validate --street pune-fc-road [--holdout-fraction 0.2] [--seed 42]

# GA against the random, greedy and design-guideline arms at matched budget.
# Writes docs/figures/<street>-layouts.png.
python -m app.optimizer.ga --street pune-fc-road [--trees 20] [--reflective-cells 150] \
    [--generations 400] [--population 120] [--ga-seeds 3] [--random-seeds 30]

# Do coefficients transfer between windows? Hold-out error of borrowed, offset and pooled models.
python -m app.model.transfer

# Rank every eligible street in the cached windows by modelled cooling per ₹1 lakh (about 35 min, 4 workers).
# Writes backend/fixtures/ranking/four-windows.json.
python -m app.ranking [--workers 4]

# Record every API response the app uses, per street, for the offline replay (frontend/public/snapshot/).
python -m app.snapshot

# Re-derive the footprint-area → storeys table from tagged OSM buildings.
python -m app.data.heights
```

`prefetch` always allows cache misses to reach the network, since filling the cache is its job. A second run is served entirely from disk.

---

## Adding a street

1. **Prefetch the window.** Give the street's approximate WGS84 extent:
   ```bash
   python -m app.data.prefetch --street pune-new-street --name "New Street, Pune" --city Pune \
       --profile mixed --bbox-street MIN_LON MIN_LAT MAX_LON MAX_LAT
   ```
   This writes `backend/fixtures/streets/pune-new-street.json` and caches:
   - a 67 × 67-cell Landsat window centred on the extent
   - the matching Sentinel-2 window
   - OSM data from Overpass
   - Overture buildings
2. **Add `osm_name` to the manifest.** Use the exact OSM `name` tag of the street's ways. The design segment is built on the longest way with that name, which must be at least 200 m long.
3. **Verify the extent.** Check it against the OSM geometry, then set `bbox_street_verified` to `true`.
4. **Restart the backend.** The street then appears in `/api/streets`.

A street outside UTM zone 43N works: the zone is derived from the extent. However, the overpass readout assumes IST (`LOCAL_UTC_OFFSET_MINUTES = 330`), and the cost table is Indian.

---

## Testing

### Backend

```bash
cd backend && pytest -q
```

| Area | Tests |
|---|---|
| Satellite numerics | `test_landsat_scaling.py` (USGS worked example), `test_source_numerics.py` (QA bits, ST_QA, S2 offset, median compositing) |
| Architecture | `test_source_boundary.py`: no vendor SDK imported outside the adapters |
| Cache | `test_cache.py`: key stability, `CacheMiss` when live data is off |
| Contracts | `test_contracts.py`: validators, unit-suffix rules, null-cost consistency |
| Model | `test_heat.py`, `test_validate.py`, `test_landcover.py`, `test_cost.py`, `test_heights.py`, `test_cross_section.py` |
| Optimizer | `test_optimizer.py`: repair, spacing, budgets, baselines |
| Integration | `test_pipeline.py`, `test_smoke.py`, and `test_integration_offline.py` |

`test_integration_offline.py` blocks every non-loopback socket and DNS lookup. For each fixture street it then drives the whole API: list, thermal, geometry, calibrate, optimize, the WebSocket, and the result.

Test fixtures under `tests/` use synthetic arrays. Everything under `backend/fixtures/` is really pulled data.

### Frontend

```bash
cd frontend && npm test && npm run typecheck && npm run check:design
```

The frontend tests are hand-checked numeric tests for:
- formatting (cost ranges rounded outward, delta precision)
- geometry and street-frame affine transforms
- the reveal clock and model helpers
- the thermal ramp
- scene construction

---

## Results on the fixture streets

### Calibration, FC Road window

| Quantity | Value |
|---|---|
| Cells | 387 fitted, 97 held out |
| `rmse_holdout_c` | 1.40 °C |
| `rmse_mean_baseline_c` | 2.03 °C |
| `r2_holdout` | 0.53 |
| canopy − bare | −7.98 °C (se 0.40) |
| built − bare | −4.45 °C (se 0.58) |
| paved − bare | −2.29 °C (se 1.17) |

Across the four windows, hold-out RMSE is 1.2–1.7 °C per 90 m cell.

### Default run: trees only

This is what the app opens on. Every arm gets 20 trees and no coating; GA population 120, 400 generations, seed 42. Change is in mean modelled surface temperature over the 200 m × 40 m design area.

| Street | Random (mean of 30) | Greedy | Design guideline | Searched layout | Search over strongest baseline | Cost, estimate |
|---|---|---|---|---|---|---|
| FC Road | −0.626 °C | −0.547 °C | −0.597 °C | −0.696 °C | 11% (random) | ₹74,400–1,18,040 |
| Karve Road | −0.851 °C | −0.771 °C | −0.844 °C | −0.936 °C | 10% (random) | ₹74,400–1,18,040 |
| North Main Road | −0.667 °C | −0.650 °C | −0.641 °C | −0.698 °C | 5% (random) | ₹74,400–1,18,040 |
| Bajirao Road | −0.636 °C | −0.592 °C | −0.607 °C | −0.674 °C | 6% (random) | ₹74,400–1,18,040 |

- **The strongest baseline is random, not the guideline.** On all four streets the mean random layout cools slightly more than the evenly spaced guideline layout, and greedy (hottest cell first) cools least. In a linear model a tree's gain does not depend on how hot a cell is, and even spacing ignores which pits sit under existing crowns.
- Three GA seeds agree within 0.008 °C on every street, several times smaller than the margin over the strongest baseline (0.03–0.09 °C).
- The margin comes from choosing which pits to plant. At full tree capacity (30 on FC Road) every pit is planted and the margin falls to 0.2% (`docs/figures/capacity-curve.png`).

### Matched-budget comparison, trees and coating

- **Budget.** 20 trees and 150 coated cells (600 m²) for every arm.
- **Search.** GA with population 120 and 400 generations over 3 seeds; the table shows the worst seed. Random is the mean of 30 seeds.
- **Metric.** Conservative cooling: the smallest modelled drop in mean surface temperature over the 200 m × 40 m design area.

| Street (profile) | Random | Greedy | Design guideline | GA (worst seed) |
|---|---|---|---|---|
| FC Road (mixed) | 0.706 °C | 0.629 °C | 0.683 °C | 0.801 °C |
| Karve Road (wide arterial) | 0.933 °C | 0.832 °C | 0.933 °C | 1.045 °C |
| North Main Road (leafy residential) | 0.757 °C | 0.747 °C | 0.728 °C | 0.810 °C |
| Bajirao Road (dense commercial) | 0.725 °C | 0.682 °C | 0.699 °C | 0.781 °C |

- **Size of the GA's advantage.** The GA beats the design guideline on every street and every seed, by 0.08–0.12 °C, which is 11–17% more modelled cooling from the same trees and coating.
- **Why it wins.** It picks tree pits clear of existing crowns, and coats the paving the new crowns do not cover.
- **What the gap is worth.** The gap is smaller than the model's per-cell error. All arms share the same coefficients, so the ranking is more robust than the absolute values, but none of these differences is measured.

Figures for every street are in `docs/figures/`.

---

## Limitations

- **Statistical model, not CFD.** A calibrated linear regression, chosen because evaluating it takes milliseconds, which is what makes search over thousands of layouts interactive.
- **Surface temperature, not air temperature.** No output describes what a person would feel.
- **Mid-morning, not peak.** The 10:57 IST overpass is not the afternoon peak, which would be hotter.
- **A typical state, not a day.** The composite is a per-pixel median over three pre-monsoon seasons.
- **Canopy from NDVI.** Canopy is any vigorous green vegetation. A watered lawn counts the same as a tree, and cooling is modelled as a canopy-fraction effect, not per species.
- **Incomplete footprints and road widths.** Unmapped roofs and paving fall into "bare". Few OSM ways carry width tags, so paved area is underestimated, and the paved coefficient has the widest uncertainty.
- **Cross-sections are assumed.** They apply Pune's published design templates to a right of way measured from building edges. Setbacks behind compound walls make the measured width wider than the public street.
- **Borrowed albedo effect.** The coefficient comes from Los Angeles pavement measurements, hence the wide band.
- **Mature trees.** Tree cooling assumes an 8 m mature crown. Saplings are far smaller for years.
- **Partial costs.** Only trees are priced, with Jaipur 2023 rates and first-year care only.
- **Display-only heights.** Building heights beyond OSM tags are estimates from footprint area, and the heat model does not use them.

Every assumption, its value, its reasoning and what changing it would change is in [docs/methodology.md](docs/methodology.md).

---

## Data licences and attribution

- **Landsat 8/9 Collection 2.** U.S. Geological Survey; public domain. Accessed through Microsoft Planetary Computer.
- **Sentinel-2 L2A.** Copernicus Sentinel data, European Space Agency. Accessed through Microsoft Planetary Computer.
- **OpenStreetMap.** © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright).
- **Overture Maps Foundation, buildings theme.** Conflates OpenStreetMap (ODbL), Microsoft Global ML Building Footprints (ODbL) and Google Open Buildings (CC BY 4.0 / ODbL).
- **Pune Municipal Corporation, *Urban Street Design Guidelines* (2016)**, with ITDP India. Used for the cross-section templates.
- **Indian Roads Congress IRC:SP:21-2009 and IRC:103-2012.** Used for tree spacing and footway minimums.
- **RUIDP *Integrated Schedule of Rates 2023*, Government of Rajasthan.** Used for tree costs.

Full citations for every constant are in [docs/sources.md](docs/sources.md).
