# Heat Surgeon — Master Spec

> A physics-grounded optimization engine for cooling real streets.
> NextStep Hacks 2026 · HackAlphaX · Theme: Earth Forward
> Build window: 10 days.

**Revision 4** — the heat model is split into a fitted baseline and an intervention delta. The baseline (canopy, built, bare; paved is the reference) is fitted on 90 m calibration cells, not 30 m pixels. The albedo coefficient is a published field measurement carried as a low/high band, never fitted. Built and paved surfaces come from OSM, canopy from NDVI. Contracts reopened on Day 3 for these fields: `CalibrationResult` gains `k_built`, `k_bare`, `k_albedo_low/high`, `calibration_resolution_m`, `n_cells_*` and loses the fitted albedo and impervious terms; temperature deltas and after-grids become low/high bands; `Resolution` gains `calibration_resolution_m`. Overpass time corrected to the measured 10:57 IST. Invented calibration numbers replaced with real output.

**Revision 3** — measured grids stay on their native UTM grid (no resampling of measured values). `OptimizationResult` gains a street-aligned design grid with before/after surfaces and a single comparison-arm shape. Invalid cells are `null` with no separate mask. Coordinates use typed `BBoxWGS84` / `PointUTM` / `AffineUTM`. Model coefficients are named by unit. `layout_preview` is sent only on improvement. Sentinel-2 masking and offset handling specified. Uncitable thresholds are logged as assumptions. CLAUDE.md rules 6 and 7 amended. §7 examples are illustrative, not normative.

**Revision 2** — contracts revised for composite provenance, cost ranges, unit-suffixed field names, a single intervention shape, and full endpoint coverage. Data layer revised for Pune's monsoon calendar, per-pixel cloud masking, and a source-adapter abstraction.

---

## 0. The one-sentence version

Pick a real street. Heat Surgeon pulls that street's actual satellite surface temperature, fits a heat model to its neighbourhood, searches thousands of possible redesigns under real budget and space constraints, and returns the single best intervention layout — rendered in 3D with a modelled temperature drop and a cost estimate.

**Existing tools stop at "this street is hot." We answer "here is what to do, how much cooler it gets, and what it costs."**

---

## 1. Scope contract (read this before adding anything)

Three tiers. Do not start a tier until the one above it runs end to end.

### Tier 1 — MUST SHIP (if only this ships, the project is still a winner)
- One real street, real Landsat land-surface temperature, real Sentinel-2 land cover, real OSM geometry.
- Heat model calibrated on real pixels, with a **reported hold-out error in °C**.
- Single-objective genetic algorithm producing a layout that measurably beats both random placement and a naive greedy baseline.
- 2D result view: before/after heat grid, intervention overlay, temperature delta, cost range.
- Four pre-cached real streets. Runs fully offline from fixtures.

### Tier 2 — SHOULD SHIP
- 3D scene: extruded OSM buildings, shader ground plane, instanced interventions.
- Before→after shader crossfade synced to the temperature counter.
- Live WebSocket optimizer streaming (generation counter + convergence curve).
- Street search / map picker for arbitrary streets.

### Tier 3 — ONLY IF TIER 1 AND 2 ARE DONE AND REHEARSED
- NSGA-II multi-objective Pareto front ("spend more, cool more").
- Thermal sharpening (TsHARP-style downscaling of 30m LST using 10m NDVI).
- City-wide batch ranking by cost-per-degree.

**Rule: on Day 8, whatever is not working gets cut, not fixed.**

---

## 2. Architecture

```
┌──────────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────┐
│  FRONTEND                │     │  FASTAPI CORE            │     │  DATA LAYER              │
│  React + Vite            │◀───▶│  REST + WebSocket        │◀───▶│  SurfaceTemperatureSource│
│  R3F / three.js          │ REST│  Job orchestration       │cache│   ├ EarthEngineSource    │
│  MapLibre GL (picker)    │ /WS │  Pydantic contracts      │     │   └ PlanetaryComputerSrc │
│  Zustand (state)         │     │                          │     │  OSM Overpass (geometry) │
└───────────┬──────────────┘     └───────────┬──────────────┘     │  Local fixture cache     │
            │                                 │                    └──────────────────────────┘
            │                    ┌────────────▼────────────┐
            │                    │  HEAT MODEL             │
            │                    │  per-neighbourhood fit  │
            │                    │  (numpy + scipy)        │
            │                    └────────────┬────────────┘
            │                                 │
            │                    ┌────────────▼────────────┐
            └───────────────────▶│  OPTIMIZER              │
              stream progress     │  GA (DEAP) + baselines  │
                                  └─────────────────────────┘
```

**Every layer is independently testable and independently mockable.**
- The heat model is validated with zero optimizer and zero frontend code.
- The optimizer runs against a fake heat model before real data exists.
- The frontend builds against fixture JSON before the backend exists.
- **The satellite source is an interface, not a hard dependency on one vendor.**

---

## 3. Repo layout

```
heat-surgeon/
├── CLAUDE.md
├── SPEC.md
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, routers
│   │   ├── contracts.py         # ALL pydantic models — single source of truth
│   │   ├── config.py            # settings, cost table, material constants
│   │   ├── routers/
│   │   │   ├── street.py        # list, geometry, thermal
│   │   │   ├── calibrate.py
│   │   │   └── optimize.py      # REST kickoff + WS stream
│   │   ├── data/
│   │   │   ├── sources.py       # SurfaceTemperatureSource / LandCoverSource protocols
│   │   │   ├── earth_engine.py  # EarthEngineSource
│   │   │   ├── planetary.py     # PlanetaryComputerSource (no-auth fallback)
│   │   │   ├── cache.py         # disk cache wrapper
│   │   │   ├── osm.py           # Overpass queries
│   │   │   ├── fixtures.py      # loads pre-cached streets
│   │   │   ├── landcover.py     # NDVI → canopy/impervious fractions
│   │   │   └── prefetch.py      # CLI: cache a street's window
│   │   ├── model/
│   │   │   ├── heat.py          # the UHI regression + calibration
│   │   │   ├── validate.py      # hold-out error reporting
│   │   │   └── cost.py          # intervention cost ranges
│   │   └── optimizer/
│   │       ├── encoding.py      # grid <-> genome, constraint repair
│   │       ├── ga.py            # single-objective GA
│   │       ├── baselines.py     # random + greedy
│   │       └── nsga2.py         # Tier 3 only
│   ├── fixtures/streets/        # 4 pre-fetched REAL streets, committed
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/App.tsx
│   │   ├── stages/              # Locate / Diagnose / Optimize / Operate
│   │   ├── scene/               # R3F components + shaders
│   │   ├── ui/                  # Numeral, Decode, Readout, ThermalScale
│   │   ├── store/               # zustand
│   │   ├── types/contracts.ts   # mirrors backend contracts.py
│   │   └── styles/tokens.css
│   └── public/fonts/
└── docs/
    ├── methodology.md           # the honest limitations doc — a judging asset
    └── sources.md               # every constant, with a citation
```

**Python 3.11.** Do not use 3.14 — DEAP, rasterio and the geospatial stack are not worth gambling on wheel availability during a 10-day build. 3.12 is an acceptable substitute.

---

## 4. Data layer

| Source | What we take | Access | Native resolution |
|---|---|---|---|
| Landsat 8/9 C2 L2 (`ST_B10`) | Land surface temperature | Earth Engine **or** Planetary Computer STAC | 100m TIRS, delivered at 30m |
| Sentinel-2 L2A | NDVI → canopy & impervious fraction | Same adapters | 10m |
| OSM Overpass | Building footprints, road centerlines, sidewalk tags | Free, no auth | Vector |

### 4.1 Source adapter — not a vendor dependency

Define `SurfaceTemperatureSource` and `LandCoverSource` protocols in `app/data/sources.py`. Routers and the model layer talk to the protocol, never to `ee` directly.

- **`EarthEngineSource`** — preferred. Requires a registered Google Cloud project and a browser-completed `earthengine authenticate`.
- **`PlanetaryComputerSource`** — the no-registration fallback. Microsoft's Planetary Computer serves the same `landsat-c2-l2` and `sentinel-2-l2a` collections through a public STAC API queryable with `pystac-client`, with `eo:cloud_cover` filtering. Asset access uses signed URLs from its Data Authentication API, which works anonymously; an API key only buys higher rate limits and longer-lived tokens. No Google account, no browser sign-in.

Earth Engine auth is the one dependency that can block the build from outside the repo. The adapter exists so that blockage costs a config change, not a rewrite.

### 4.2 Date window — Pune's calendar, not a generic "summer"

**Default: 1 March – 31 May, across 3 years.**

June–September is monsoon. Cloud filtering over those months leaves almost nothing usable, and what survives is unrepresentative. March–May is the pre-monsoon hot season, when the urban heat island signal is strongest and skies are clearest. Three years of it gives the median enough clear scenes to be stable.

### 4.3 Masking and compositing

**Landsat (surface temperature):**

1. Scene-level `eo:cloud_cover` / `CLOUD_COVER` filter as a cheap pre-filter. The limit is an assumption, not a citation, and is logged in `docs/methodology.md`.
2. **Per-pixel masking on `QA_PIXEL`** (fill, dilated cloud, cirrus, cloud, cloud shadow bits). Scene-level filtering alone leaves cloud edges that will wreck a single street.
3. Drop fill pixels (raw value 0) and `ST_QA` outliers. The `ST_QA` cut-off is an assumption, not a citation.
4. **Per-pixel median composite** across the surviving stack. Never a single scene.

**Sentinel-2 (land cover):**

1. Same date window as Landsat.
2. Per-pixel mask on the scene classification layer `SCL`: drop classes 3 (cloud shadow), 8 (cloud, medium probability), 9 (cloud, high probability), 10 (thin cirrus), and no-data.
3. From processing baseline 04.00 (January 2022), L2A digital numbers carry a `BOA_ADD_OFFSET`. Read the offset from each item's metadata rather than hardcoding −1000, apply it, and assert it was applied before NDVI is computed. A silent wrong-sign NDVI would poison the model with no error.
4. Cache the per-pixel median of B4 (red) and B8 (NIR) only.

Measured values are never resampled. Where two grids meet (10 m Sentinel-2 land cover summarised onto 30 m Landsat cells), land-cover *fractions* are aggregated by exact area overlap; temperatures are not touched.

### 4.4 Scaling (get this right or every number is wrong)

```python
# Landsat Collection 2 Level 2 surface temperature, ST_B10:
celsius = raw * 0.00341802 + 149.0 - 273.15
```

Unit-test this against a hand-checked value **before** writing the fetch function.

### 4.5 Overpass time — record it

Landsat's overpass over Pune is **10:57 IST**: the median acquisition time of the 30 scenes in the FC Road composite, about 10:22 local solar time. This is mid-morning surface temperature, not the mid-afternoon peak. State this in `docs/methodology.md` and in the pitch. Do not let a judge assume we are modelling worst-case heat.

### 4.6 Caching rules

1. Every external call goes through `app/data/cache.py`, keyed on `(source_adapter, product, bbox, date_range)`. Arrays as `.npy`, metadata as `.json`.
2. **Fixtures are committed to git.** Four real streets with visibly different heat profiles: dense low-canopy commercial, leafy residential, wide arterial, mixed.
3. `USE_LIVE_DATA` defaults to `false`. The demo path is the offline path.
4. `prefetch` caches the **full 2 km neighbourhood window**, not just the street bbox, and caches Landsat **and** Sentinel-2 for that window **in the same run**. One fully-cached window beats two half-cached ones.
5. Fixture street metadata carries `bbox_street_verified`. Street extents are placeholders until checked against OSM geometry on Day 3.

---

## 5. The heat model

### 5.1 The model

```
Baseline (fitted):
  LST_pred(x) = t_base_c − k_canopy·canopy(x) + k_built·built(x) + k_bare·bare(x)

Intervention delta (applied on top of the baseline):
  tree        crown cells become canopy          uses fitted k_canopy, k_built, k_bare
  permeable   paved footway becomes bare-like    uses fitted k_bare
  reflective  surface albedo rises               ΔLST = −k_albedo · Δalbedo, k_albedo PUBLISHED (low/high band)
```

- `canopy`: area share with Sentinel-2 NDVI at or above 0.5. `built`: OSM building footprints. `paved`: OSM highway ways buffered to tagged or estimated width. `bare`: everything else. The shares sum to one, so paved is the reference class and `t_base_c` is a fully paved cell.
- `k_canopy_c_per_fraction`, `k_built_c_per_fraction`, `k_bare_c_per_fraction`, `t_base_c`: fitted by least squares on 90 m calibration cells.
- `k_albedo_c_per_unit_albedo`: **not fitted.** Fitting it from observation recovered the wrong sign, because albedo tracks surface dryness in the pre-monsoon season. It is taken from published field measurement as a low/high pair (`config.py`, `docs/sources.md`). Any layout with a reflective intervention returns a temperature band.
- `Δalbedo`: coating albedo minus the existing surface's albedo, from the cited material tables.

### 5.2 Calibrate on the neighbourhood, apply to the street

**Do not fit four parameters using only one street segment's pixels.** A 150m street at 30m delivery gives roughly 5 pixels, which are really only 1–2 independent measurements at 100m native resolution. Fitting four free parameters to that overfits, and coefficients will swing wildly between streets.

Instead:

1. Take a **1.5–2 km window centred on the street** → hundreds to thousands of pixels spanning real variation in canopy and pavement.
2. Fit `k_canopy`, `k_built`, `k_bare` and `t_base_c` on that window's 90 m calibration cells (3 × 3 Landsat cells, close to the 100 m native thermal resolution). Fitting 30 m land cover against a 100 m thermal signal attenuates every coefficient; Day 2 measured exactly that.
3. Apply the fitted coefficients at street resolution.

Pitch line: "calibrated against the real measured thermal signature of this street's own neighbourhood, not a generic textbook constant."

### 5.3 The resolution story — say this before a judge asks

This is the sharpest attack surface in the project. The honest framing, which must appear in `docs/methodology.md` **and** in the UI:

| Layer | Resolution | What it is |
|---|---|---|
| Measurement | 30m delivered (100m native) | Real Landsat observation. Neighbouring 30 m pixels are not independent. |
| Calibration | 90 m cells across the 2 km window (484 cells) | Where the fitted coefficients come from. 90 m is close to the real measurement scale. |
| Intervention design | 2m cells | The resolution at which a tree is physically sited |
| Rendered before/after surface | 2m | **A model output at design resolution — not a measurement** |

Interventions placed at 2m change the surface class of the cells they cover, and the linear model turns that into a modelled temperature change; averaged over an area, that equals applying the 90 m coefficients to the changed area shares. Stated that way it is a coherent resolution story. Hidden, it is the question that sinks the demo.

The UI labels the rendered surface as modelled, not measured. The `/result` payload carries `measurement_resolution_m`, `calibration_resolution_m`, `design_resolution_m`, and `output_kind` so the frontend cannot forget.

### 5.4 Report error

Hold out 20% of the window's pixels. Report `rmse_holdout_c` alongside `rmse_mean_baseline_c` (the error from simply predicting the window mean), and display both.

> "Our model predicts held-out 90 m cells in this neighbourhood to within ±1.36 °C, against a 2.03 °C baseline." (real FC Road output)

This is the highest-leverage half-day in the build. Under a criterion literally named *Technology*, almost no hackathon team ships an error bar.

### 5.5 Honest limitations (in `docs/methodology.md` and in the pitch)

- Calibrated statistical regression, not CFD. Deliberate: milliseconds per evaluation is what makes interactive optimization possible. CFD is hours per run.
- Land **surface** temperature, not air temperature at head height. Say "surface temperature" everywhere. Never "it will feel 2.3 °C cooler."
- Mid-morning overpass, not afternoon peak.
- Tree cooling modelled as a canopy-fraction effect, not per-species evapotranspiration.
- Building heights estimated from footprint area where OSM lacks them.
- Median composite over three pre-monsoon seasons — a typical hot-season state, not a specific day.

Stating limits unprompted reads as rigour. Getting caught hiding one reads as fraud.

---

## 6. The optimizer

### 6.1 Encoding
2m × 2m cells. Each cell: `unchanged | tree | reflective_pavement | permeable_pavement | shade_structure`. A 150m × 30m street = 75 × 15 = **1,125 cells**; genome is a flat integer array of that length.

The grid is **street-aligned**: rotated to the street's bearing, because sidewalk and carriageway constraints are meaningless on an axis-aligned grid. It is capped at **4,000 cells**. A street that exceeds the cap raises an error; it is never silently coarsened.

### 6.2 Constraints — repair, not rejection
Random genomes are almost always invalid, so rejection sampling wastes the population. `repair(genome)` projects any genome into the feasible set:
- No intervention inside a building footprint → force `unchanged`.
- Trees only on plantable surface (verge, sidewalk above width threshold), never in the carriageway.
- Minimum tree spacing (roots + canopy) → thin violators.
- Pavement types only on their valid surface class.

Call `repair()` after init, after crossover, after mutation.

### 6.3 Fitness
```
fitness(layout) = temp_drop(layout) − λ · cost(layout)
```
Return `temp_drop` and `cost` as **separate fields** even in the single-objective version, so the Tier-3 NSGA-II upgrade is a selection-operator swap, not a rewrite.

### 6.4 Baselines — same day as the GA
1. `random_layout()` — same number of interventions, placed randomly.
2. `greedy_layout()` — place one at a time at the currently hottest valid cell.

Both at matched budget. Report all three:

> Random −0.9 °C · Greedy −1.6 °C · **Heat Surgeon −2.3 °C** — same budget.

Without baselines, "−2.3 °C" is a number a judge cannot evaluate. With them, it is a demonstrated result.

### 6.5 Streaming
Emit progress each generation over WebSocket, throttled to ~10 msg/sec. The frontend shows a live convergence curve, never a spinner. `layout_preview` is sent only when the best individual improves and is `null` otherwise; the curve needs only the scalars.

---

## 7. API contracts

Frozen on Day 1. Defined in `backend/app/contracts.py`, mirrored in `frontend/src/types/contracts.ts`.

**Examples are illustrative, not normative.** The shapes are binding; the numbers are not. Examples marked *from real prefetch output* were regenerated from cached data. The rest are placeholders until the stage that produces them exists.

### Conventions

- Every field expressing a physical quantity carries its unit suffix (CLAUDE.md rule 6). Dimensionless counts, indices and ratios are exempt, as are fields whose type encodes the unit.
- Geometry lives in the street's UTM zone (Pune: `EPSG:32643`), in metres. WGS84 appears only in `bbox_*` fields, for display, never as geometry.
- Invalid or unmeasured grid cells are `null`. There is no separate validity mask.
- Grids are row-major. On measured grids row 0 is the north edge.

### Coordinate types

| Type | Shape | Meaning |
|---|---|---|
| `BBoxWGS84` | `[min_lon, min_lat, max_lon, max_lat]` | Degrees, EPSG:4326. Display only. |
| `PointUTM` | `[easting, northing]` | Metres, in the object's `crs`. |
| `AffineUTM` | `[a, b, c, d, e, f]` | rasterio/GDAL affine order in metres: `[cell_size, 0, origin_e, 0, -cell_size, origin_n]`. |
| `CellIndex` | `[row, col]` | Index into a grid. |

```
GET  /api/streets                        → StreetSummary[]
GET  /api/street/{id}/geometry           → StreetGeometry
GET  /api/street/{id}/thermal?scope=...  → ThermalGrid
POST /api/street/{id}/calibrate          → CalibrationResult
POST /api/street/{id}/optimize           → OptimizeJobHandle
WS   /ws/optimize/{job_id}               → OptimizeProgress | OptimizeDone | OptimizeError
GET  /api/job/{job_id}/result            → OptimizationResult
```

### Provenance (embedded wherever satellite data is reported)

A median composite has no single date or scene ID. This object replaces the old `capture_date` / `source` fields entirely.

*From real prefetch output* (FC Road window, 2026-09-14). `scene_ids` and `capture_dates` are truncated here to the first two of 30.

```json
{
  "product": "surface_temperature",
  "date_range": ["2024-03-01", "2026-05-31"],
  "months": [3, 4, 5],
  "scene_count": 30,
  "capture_dates": ["2024-03-07", "2024-03-15"],
  "scene_ids": ["LC09_L2SP_147047_20240307_02_T1", "LC08_L2SP_147047_20240315_02_T1"],
  "collections": ["landsat-c2-l2"],
  "platforms": ["landsat-8", "landsat-9"],
  "compositing": "per-pixel median",
  "cloud_masking": "scene eo:cloud_cover < 40.0%; QA_PIXEL fill, dilated cloud, cirrus, cloud and cloud shadow dropped; ST_QA uncertainty above 5.0 K dropped; pixels need at least 5 clear observations",
  "overpass_local_time": "10:57",
  "native_resolution_m": 100.0,
  "delivered_resolution_m": 30.0,
  "source_adapter": "planetary_computer"
}
```
- `product` is `surface_temperature | land_cover`.
- `collections` holds each adapter's native IDs verbatim, never normalised. Earth Engine reports `LANDSAT/LC09/C02/T1_L2`; Planetary Computer reports `landsat-c2-l2`. `source_adapter` disambiguates.
- `platforms` is filled where the adapter reports platform separately from the collection, and is empty otherwise.

### StreetSummary
*From real prefetch output.* `bbox_street` is still the unverified placeholder.
```json
{
  "id": "pune-fc-road",
  "name": "FC Road, Pune",
  "city": "Pune",
  "profile": "dense_commercial",
  "bbox_street": [73.8401, 18.5181, 73.8437, 18.5228],
  "bbox_street_verified": false,
  "bbox_window": [73.83233, 18.51131, 73.85149, 18.52959],
  "cached": true
}
```
`profile` is one of `dense_commercial | leafy_residential | wide_arterial | mixed`. `bbox_street_verified` stays `false` until the extent is checked against OSM geometry.

### StreetGeometry
```json
{
  "street_id": "pune-fc-road",
  "crs": "EPSG:32643",
  "bbox_street": [73.8401, 18.5181, 73.8437, 18.5228],
  "buildings": [
    { "id": "osm:way/123456",
      "footprint": [[374215.2, 2050884.9], [374230.8, 2050884.9], [374230.8, 2050901.3]],
      "height_m": 12.0, "height_source": "osm_tag" }
  ],
  "road": { "centerline": [[374212.0, 2050882.0], [374890.5, 2051410.2]],
            "width_m": 18.0, "width_source": "osm_tag" },
  "sidewalks": [ { "polygon": [[374205.1, 2050880.3], [374260.4, 2050921.7]],
                   "width_m": 3.2, "width_source": "estimated_from_area" } ]
}
```
All geometry is `PointUTM` in `crs`. `height_source` and `width_source` are one of `osm_tag | estimated_from_area | default_assumption`. Anything not `osm_tag` is an assumption and gets logged to `docs/methodology.md`.

### ThermalGrid
*From real prefetch output.* `lst_c` is truncated here to the first four cells of row 0; the real grid is 67 × 67 with no nulls.
```json
{
  "street_id": "pune-fc-road",
  "scope": "window",
  "crs": "EPSG:32643",
  "transform": [30.0, 0.0, 376755.0, 0.0, -30.0, 2049165.0],
  "shape": [67, 67],
  "cell_size_m": 30.0,
  "bbox_wgs84": [73.83233, 18.51131, 73.85149, 18.52959],
  "lst_c": [[42.67, 42.47, 42.23, 41.99]],
  "stats": { "min_c": 36.23, "max_c": 48.18, "mean_c": 41.0, "valid_pixels": 4489 },
  "provenance": {}
}
```
- `scope` is `street | window`.
- The grid is Landsat's native grid, unresampled. `transform` places row 0 at the north edge.
- `lst_c` is `null` wherever no valid observation survived masking. The loader rebuilds a masked array from the nulls.
- `bbox_wgs84` is for display only and is never used as geometry.

### CalibrationRequest / CalibrationResult
```json
// request
{ "holdout_fraction": 0.2, "seed": 42 }

// result
{
  "street_id": "pune-fc-road",
  "bbox_window": [73.83233, 18.51131, 73.85149, 18.52959],
  "calibration_resolution_m": 90.0,
  "t_base_c": 41.92,
  "k_canopy_c_per_fraction": 5.49,
  "k_built_c_per_fraction": -2.97,
  "k_bare_c_per_fraction": 2.33,
  "k_albedo_low_c_per_unit_albedo": 5.0,
  "k_albedo_high_c_per_unit_albedo": 27.0,
  "rmse_holdout_c": 1.36,
  "rmse_mean_baseline_c": 2.03,
  "r2_holdout": 0.55,
  "n_cells_fit": 387,
  "n_cells_holdout": 97,
  "provenance": [{}, {}]
}
```
*From real calibration output* (FC Road, revision 4 model). `provenance` lists one entry per product used (surface temperature and land cover). `k_albedo_low/high` are published constants reported for transparency, not fitted values.

### OptimizeRequest / OptimizeJobHandle
```json
// request
{
  "budget_inr_max": 300000,
  "generations": 400,
  "population": 120,
  "cost_weight_c_per_inr": 0.00001,
  "run_baselines": true,
  "seed": 42
}

// handle
{
  "job_id": "b1f2c3",
  "ws_url": "/ws/optimize/b1f2c3",
  "grid_shape": [75, 15],
  "cells": 1125,
  "states_per_cell": 5
}
```

### WebSocket messages
```json
{ "type": "progress", "job_id": "b1f2c3", "generation": 142, "generations_total": 400,
  "best_fitness_score": 1.87, "best_temp_delta_c_low": -2.40, "best_temp_delta_c_high": -2.11,
  "best_cost_inr_low": 180000, "best_cost_inr_high": 260000,
  "layout_preview": [ { "type": "tree", "cells": [[12, 4]] },
                      { "type": "permeable_pavement", "cells": [[20, 7]] } ] }

{ "type": "done", "job_id": "b1f2c3", "result_url": "/api/job/b1f2c3/result" }

{ "type": "error", "job_id": "b1f2c3", "code": "optimizer_failed", "message": "..." }
```
- `layout_preview` uses the intervention shape. It is sent only on generations where the best individual improves, and is `null` otherwise.
- `best_fitness_score` is the dimensionless scalarized objective from §6.3. It is not a physical quantity and is never displayed as one.

### OptimizationResult
```json
{
  "job_id": "b1f2c3",
  "street": { "id": "pune-fc-road", "name": "FC Road, Pune" },
  "baseline_temp_c": 36.4,
  "optimized_temp_c_low": 33.8,
  "optimized_temp_c_high": 34.1,
  "temp_delta_c_low": -2.6,
  "temp_delta_c_high": -2.3,
  "cost_inr_low": 180000,
  "cost_inr_high": 260000,
  "model": { "rmse_holdout_c": 1.36, "rmse_mean_baseline_c": 2.03 },
  "comparison": {
    "random": { "temp_delta_c_low": -1.1, "temp_delta_c_high": -0.9, "cost_inr_low": 175000, "cost_inr_high": 255000 },
    "greedy": { "temp_delta_c_low": -1.8, "temp_delta_c_high": -1.6, "cost_inr_low": 178000, "cost_inr_high": 258000 },
    "ga":     { "temp_delta_c_low": -2.6, "temp_delta_c_high": -2.3, "cost_inr_low": 180000, "cost_inr_high": 260000 }
  },
  "interventions": [
    { "type": "tree", "cells": [[12, 4], [15, 4], [18, 5]] },
    { "type": "permeable_pavement", "cells": [[20, 7], [21, 7]] }
  ],
  "design_grid": {
    "crs": "EPSG:32643",
    "origin_e_m": 374210.0,
    "origin_n_m": 2050880.0,
    "bearing_deg": 37.4,
    "cell_size_m": 2.0,
    "shape": [75, 15]
  },
  "before_lst_c": [[36.1, 36.3, null]],
  "after_lst_c_low": [[33.7, 36.3, null]],
  "after_lst_c_high": [[34.0, 36.3, null]],
  "resolution": {
    "measurement_resolution_m": 30,
    "calibration_resolution_m": 90,
    "design_resolution_m": 2,
    "output_kind": "model_output_at_design_resolution"
  },
  "provenance": [{}, {}]
}
```

- One intervention shape only: `{type, cells}`. Count is `len(cells)`, never stored separately. `type` is one of `tree | reflective_pavement | permeable_pavement | shade_structure`.
- All three `comparison` arms share one shape, so the matched-budget claim is checkable from the payload.
- `design_grid` is street-aligned. (`origin_e_m`, `origin_n_m`) is the outer corner of cell `[0, 0]`. Rows advance along `bearing_deg` (degrees clockwise from UTM grid north) and columns advance to the right of that direction, so `shape` is `[cells along street, cells across street]`. Capped at 4,000 cells; exceeding the cap raises.
- `before_lst_c`, `after_lst_c_low` and `after_lst_c_high` lie on `design_grid` and are `null` where the model has no value. All are model output, as `resolution.output_kind` states.
- Temperature deltas are bands. `_low` is the more-cooling end and `_high` the less-cooling end, from the published albedo coefficient range. With no reflective intervention the two are equal. The optimizer ranks layouts on the `_high` (conservative) end.
- Apart from `model`, the numbers in this example are illustrative until the Day 4 API produces a real result.

---

## 8. Cost model

All costs in `config.py`, every figure cited in `docs/sources.md`. Never invent a number at demo time.

Per unit, as **low/high ranges**:
- Street tree: sapling + pit + 3-year establishment care.
- Reflective / high-albedo coating: per m².
- Permeable concrete: per m² (materially pricier than coating).
- Shade structure: per unit.

The UI shows the range and labels it an order-of-magnitude estimate. It never shows a midpoint. Precision you don't have is a liability.

---

## 9. Design spec

### 9.1 The concept
A **scientific instrument for looking at heat**, not a climate-awareness site. The thermal imaging scale is the interface's actual colour system — functional, not decorative.

### 9.2 The structure
The app is a four-stage instrument, and the stage numbers are the real pipeline sequence:

```
00 / LOCATE      pick the street
01 / DIAGNOSE    pull real data, fit the model, show what's driving the heat
02 / OPTIMIZE    run the GA, live
03 / OPERATE     the result: 3D before/after, delta, cost range, baselines
```

Numbering is earned because it genuinely is a sequence. Decode-from-scramble is earned because data really is being acquired. The count-up numeral is earned because the delta is the payoff. No device is theatre laid on top.

### 9.3 The acquisition decode — provenance stack, not a fake scene ID
Because we composite, there is no single scene ID to show. The decode moment resolves a **stack** instead. As the real fetch completes, these readouts resolve from scrambled characters in sequence:

```
scenes          27
seasons         Mar–May, 2024–2026
collections     landsat-8-c2-l2
                landsat-9-c2-l2
composite       per-pixel median
overpass        10:57 IST
```

More honest than a single ID, and it reads more like an instrument. Duration tied to the real fetch, not a fixed timer.

### 9.4 Colour tokens
Dark base is justified — thermal imagery is illegible on light. The base carries real blue hue rather than tinted black, and the accent system is a **continuous five-stop thermal ramp**, not one brand accent.

```css
--base:        #131A22;  /* deep blue-slate console */
--panel:       #1B242E;  /* raised surfaces */
--rule:        #2C3945;  /* hairlines, graticule */
--paper:       #E9E4D9;  /* body text, warm off-white */
--paper-dim:   #8C96A1;  /* secondary text */

/* thermal ramp — data only */
--t-00:        #1B4B57;
--t-25:        #3E7C8C;
--t-50:        #C9B58A;
--t-75:        #C56A35;
--t-100:       #A3341F;

--signal:      #7FD1DE;  /* the ONE bright colour: final delta readout only */
```

If a ramp colour appears on something that is not measured or modelled data, it is a bug.

### 9.5 Type
- **Display:** General Sans (Fontshare, free) or Geist. Engineered, no serif warmth. Tight tracking at large sizes.
- **Body:** IBM Plex Sans.
- **Data:** IBM Plex Mono — strictly for measured and modelled values, coordinates, temperatures, costs, scene counts, generation counters. Mono on non-data turns an instrument into a costume.

Scale (1.25 ratio): `12 / 14 / 16 / 20 / 25 / 31 / 39 / 49 / 61`. Body line length under 70 characters. Sentence case throughout.

### 9.6 Layout
Left-aligned, generous margins, persistent faint graticule behind map and 3D views — earned by the real geodata underneath. Asymmetric: data panel left, viewport right, readout column never centred.

```
┌──────────────────────────────────────────────────────────────┐
│ Heat Surgeon                        02 / Optimize    ●  live │
├───────────────────────┬──────────────────────────────────────┤
│  18.5204° N           │                                      │
│  73.8567° E           │            3D viewport               │
│                       │      (map, heat grid, or scene       │
│  scenes          27   │       depending on stage)            │
│  Mar–May 2024–2026    │                                      │
│  per-pixel median     │                                      │
│  overpass 10:57 IST   │                                      │
│                       │                                      │
│  Surface temperature  │                                      │
│  36.4 °C              │                                      │
│  measured, 30 m       │                                      │
│                       │                                      │
│  Model error ±1.36 °C │                                      │
│  baseline    2.03 °C  │                                      │
│  ───────────────────  │                                      │
│  generation 142 / 400 │                                      │
│  ▁▂▃▅▆▇█ convergence  │                                      │
├───────────────────────┴──────────────────────────────────────┤
│  −2.3 °C      ₹1.8–2.6L est.    random −0.9 · greedy −1.6    │
│  modelled at 2 m design resolution                           │
└──────────────────────────────────────────────────────────────┘
```

The "measured, 30 m" and "modelled at 2 m design resolution" labels are not optional. They are the resolution story, in the interface.

### 9.7 Motion — exactly two moments
1. **Acquisition decode** (stage 01): the provenance stack resolves from scrambled characters as the real tile loads. Duration tied to the actual fetch.
2. **The reveal** (stage 03): the ground shader interpolates its heat-grid data texture from before → after over ~1.5s while the delta numeral counts down. One easing curve shared so they land together.

Everything else is instant. `prefers-reduced-motion` skips both and jumps to final state.

### 9.8 Banned in this repo
Tracked-out all-caps eyebrow labels · middle-dot meta strings · uniform rounded SaaS cards with identical radii and soft grey shadows · decorative gradient washes · arrows appended to button text · emoji · glassmorphism · a second bright accent colour.

### 9.9 Copy voice
Plain, measured, instrument-like.
- Not "AI-powered climate intelligence." → "Surface temperature 36.4 °C, measured at 30 m."
- Not "Optimizing your green future!" → "Searching layouts. Generation 142 of 400."
- Empty: "Select a street to begin."
- Error: "Earth Engine did not respond. Running on cached data for FC Road, Pune."

---

## 10. Ten-day plan (risk-ordered)

| Day | Target | Done means |
|---|---|---|
| **0** (pre) | Python 3.11 installed; GEE project registered **or** Planetary Computer path confirmed | One real Landsat pull succeeded through either adapter |
| **1** | Contracts frozen + one real thermal window | `contracts.py` + `contracts.ts` agreed; real LST array for one 2 km window on disk |
| **2** | Land cover + neighbourhood calibration | baseline `k_canopy`, `k_built`, `k_bare` fitted on 90 m cells; hold-out RMSE printed; coefficient signs sanity-checked |
| **3** | Grid encoding + repair + GA | GA beats random *and* greedy on a matplotlib render |
| **4** | Baselines + cost ranges + full REST API | `/result` returns the complete payload; full offline run |
| **5** | Frontend shell, stages 00–02, live WS | Convergence curve streams in the browser |
| **6** | 3D scene: OSM buildings + shader ground | Real geometry renders, before state only; frame rate measured |
| **7** | After state + the reveal moment | Crossfade + counter synced |
| **8** | **Freeze. Cut what doesn't work.** | 4 fixture streets verified offline; dead code deleted |
| **9** | Methodology, sources, README, pitch deck | A stranger can run the repo from README alone |
| **10** | Record demo video, rehearse ×5 | Video under 5:00, fallback path rehearsed |

Tier 3 only gets touched on Day 7 if Day 6 finished early.

---

## 11. Demo video structure (5:00 hard cap)

- **0:00–0:30** The gap. Two streets, 1 km apart, several degrees different. Existing tools tell you that. Nothing tells you what to do.
- **0:30–1:00** Pick a real street. Name it. Real coordinates.
- **1:00–2:00** Real data lands. Provenance stack resolves on screen — scene count, seasons, compositing method. Model calibrates. **State the hold-out error.**
- **2:00–3:00** Optimizer runs live. Convergence curve moving. Say the search space size out loud.
- **3:00–4:00** The reveal. 3D before → after. Delta counts down. Cost range appears. **Then the baseline comparison** — same budget, random −0.9, greedy −1.6, ours −2.3.
- **4:00–4:30** Limitations, plainly: surface not air, mid-morning not peak, regression not CFD, 30 m measured / 2 m modelled.
- **4:30–5:00** Where it goes: batch across a ward, rank by cost-per-degree.

Record twice, keep the shorter take.

---

## 12. Judge pushback — rehearse these

| Question | Answer |
|---|---|
| "Is this real physics?" | A calibrated statistical model, not CFD. Deliberate: CFD is hours per run, which makes interactive optimization impossible. We report our error bar rather than claiming precision we don't have. |
| "How do you know it's accurate?" | Hold-out validation on this neighbourhood's own 90 m cells: ±1.36 °C, against a 2.03 °C mean-prediction baseline. It explains about 55% of the variation. The albedo effect is taken from published field measurement, because it cannot be fitted from pre-monsoon observation. |
| **"Landsat is 100 m. How can you claim 2 m precision?"** | We don't. 30 m is the measurement, the 2 km window is where coefficients are fitted, and 2 m is the design resolution at which a tree is physically sited. The rendered surface is labelled a model output, not a measurement — on screen, not just in the docs. |
| "Which day is this?" | None. A per-pixel median across three pre-monsoon seasons, March–May. A typical hot-season state, not one scene. Monsoon months are excluded because cloud cover makes them unusable. |
| "Is this peak heat?" | No. Landsat's overpass here is 10:57 IST, so this is late-morning surface temperature. Afternoon peak would be hotter. |
| "Surface or air temperature?" | Surface. They correlate but are distinct, and we label it as surface everywhere. |
| "Has this been done before?" | Spatial optimisation of tree planting exists in the climate literature — Boston University's *Right Place, Right Tree*, CSIRO's spatial planting work, recent GA-based tree-siting papers. None of it is an interactive, street-specific, cost-aware tool a ward office could run this week. We took a published research approach and made it operable. |
| "Would a city actually use this?" | First-pass triage and prioritisation across many streets, not a replacement for an engineering study. |
| "How does it scale?" | Same pipeline per street segment, batched across a ward, ranked by cost-per-degree. |

Naming the prior research makes you more credible, not less. Claiming nobody has thought of this, to a judge who knows the literature, ends the conversation.