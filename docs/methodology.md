# Methodology and limitations

Every assumption made in the build is recorded here, in the same commit that introduces it. Cited constants are in [sources.md](sources.md).

## Data acquisition

**Adapter.** Satellite data is pulled through Microsoft Planetary Computer's public STAC API (`planetary_computer` adapter). Earth Engine was the preferred adapter, but no Earth Engine project was registered on the build machine on Day 1. `EarthEngineSource` exists but has not yet been run against a live account. Building and road geometry comes from OpenStreetMap through the Overpass API. Everything goes through the same disk cache.

**No resampling of measured values.** Landsat surface temperature is read on its native UTM grid (EPSG:32643 for Pune), and a window that does not land exactly on that grid raises an error. Sentinel-2 reflectance is read on its own 10 m grid. Where grids meet:
- 10 m NDVI is replicated onto a 1 m sub-grid, which it tiles exactly.
- Surface cover is summarised as exact area shares.
- Measured surface temperature is averaged over 3 × 3 cells for calibration. That is aggregation, never interpolation.

**Compositing.** Each satellite product is a per-pixel median across all clear observations in the date window, never a single scene. For the FC Road window that is 30 Landsat scenes and 46 Sentinel-2 scenes across March–May of 2024, 2025 and 2026. Every Landsat pixel has at least 29 clear observations.

**Overpass time.** The median acquisition time of the Landsat scenes used is 10:57 IST (about 05:27 UTC); Sentinel-2's is 10:56 IST. In local solar time at Pune (73.84° E, 4 h 55 min ahead of UTC) that is about 10:22. Earlier drafts of the spec said "10:30 local", which was a guess and has been corrected. This is late-morning land surface temperature, not the mid-afternoon peak. The interface states the measured time from `provenance.overpass_local_time`.

**Sentinel-2 offset.** From processing baseline 04.00 (January 2022), Sentinel-2 L2A digital numbers carry an additive offset. Planetary Computer serves them without it applied; this was checked against real scenes (see sources.md). The adapter reads the offset from each product's own metadata and applies it. NDVI refuses to run unless that happened.

## What is measured and what is modelled

| Layer | Resolution | What it is |
|---|---|---|
| Measurement | 30 m delivered, 100 m native | Real Landsat land surface temperature: a per-pixel median of 30 scenes. Neighbouring 30 m pixels are not independent. |
| Calibration | 90 m cells (3 × 3 Landsat cells), 484 across the 2 km window | Where the fitted coefficients come from. 90 m is close to the real measurement scale. |
| Intervention design | 2 m cells | The resolution at which a tree or a coating is physically placed. |
| Rendered before/after surface | 2 m | **A model output at design resolution, not a measurement.** |

A 150 m street contains one or two independent thermal measurements, which is why the model is never fitted on a street's own pixels.

## Surface temperature, not air temperature

Landsat measures land surface temperature: the radiometric temperature of roofs, roads, bare ground and canopy tops, seen from above at about 11:00 IST. It is not the air temperature a person feels at head height, and the two can differ substantially on hot, dry, sunlit surfaces. Every string in the product says "surface temperature". No copy says a person will feel a change.

## Surface cover

Each 1 m sub-cell of the window gets one class, in this priority order:

| Class | Rule | Share of FC Road window (mean over 90 m cells) |
|---|---|---|
| Canopy | Sentinel-2 NDVI at or above 0.5 (what the thermal sensor sees from above, so it wins) | 26.4% |
| Built | OSM building footprint | 19.4% |
| Paved | OSM highway way, buffered to its tagged or estimated width | 7.8% |
| Water | NDVI below 0 | under 0.1% |
| Bare | everything else | 46.4% |

Limitations, stated plainly:
- **OSM building footprints are incomplete here.** FC Road is dense commercial, yet only 6 of 484 calibration cells are at least half built. Unmapped roofs fall into "bare".
- **Paved surface is underestimated.** Only 1 of 1,124 ways has a width tag; the rest use lane counts or class defaults (see assumptions), which are narrow for a busy commercial street.
- **"Bare" is a catch-all.** It holds dry soil, sparse and dry vegetation (NDVI 0.2–0.5), unmapped roofs and unmapped paving.
- **"Canopy" is any vigorous green vegetation.** In March–May that is mostly trees and irrigated lawns; a watered lawn counts the same as a tree.

## Calibration method

- Calibration cells are 90 m blocks of 3 × 3 Landsat cells. Surface temperature is the mean of the block's measured cells; surface cover shares are exact. The window is 67 cells across, so the last 30 m row and column are left out, giving 22 × 22 = 484 cells.
- Cells are usable when they have a Landsat value and full Sentinel-2 coverage, and are not more than 25% water. All 484 are usable.
- 20% of cells are held out at random (seed 42). The baseline model is fitted by ordinary least squares on the rest.
- `rmse_holdout_c` is the error on held-out cells. `rmse_mean_baseline_c` is the error from predicting every held-out cell as the mean of the fitting cells. `r2_holdout` uses held-out cells only.
- Canopy, built, paved, bare and water shares sum to one, so paved surface is the reference class. `t_base_c` is the modelled surface temperature of a fully paved cell, and each fitted k is a difference from paved.

What the hold-out error does and does not show:
- **It measures misfit within this neighbourhood.** Hold-out and in-sample error are close (1.36 vs 1.38 °C).
- **It does not show transfer to other neighbourhoods.** Neighbouring 90 m cells still share some thermal signal.
- **Coefficient standard errors are a diagnostic, not confidence intervals.**

## Calibration result, FC Road (revision 4 model)

| Quantity | Value |
|---|---|
| `t_base_c` (fully paved cell) | 41.92 °C (se 1.02) |
| `k_canopy_c_per_fraction` | +5.49 (se 1.05): canopy is cooler than paving |
| `k_built_c_per_fraction` | −2.97 (se 1.28): **built cells come out cooler than paving** |
| `k_bare_c_per_fraction` | +2.33 (se 1.12): bare ground is hotter than paving |
| `k_albedo_c_per_unit_albedo` | 5.0 to 27.0, published, not fitted |
| `rmse_holdout_c` | 1.36 °C |
| `rmse_mean_baseline_c` | 2.03 °C |
| `r2_holdout` | 0.55 |
| Cells | 387 fitted, 97 held out |

Scatter: [figures/pune-fc-road-calibration.png](figures/pune-fc-road-calibration.png).

**Against the Day 2 fit.** Moving from 30 m pixels to 90 m cells and splitting built, paved and bare with OSM raised hold-out R² from 0.30 to 0.55 and cut RMSE from 1.83 to 1.36 °C. The compression of the hottest pixels is largely gone.

**The built coefficient's sign.** Built cells coming out cooler than paved ones is not physically impossible at 11:00: roofs are shaded by neighbours and heat more slowly than asphalt in the morning. But it should not be trusted as a finding, for three reasons:
- **The reference class is thin.** Paved surface averages 7.8% of a cell, and no cell is majority paved. Every coefficient is a difference from a surface the data barely contains, so `t_base_c` and all three k values are extrapolations.
- **OSM misses buildings.** Many roofs are counted as bare, which moves heat from "built" into "bare".
- **It is uncertain.** −2.97 with a standard error of 1.28 is about 2.3 standard errors from zero, before accounting for spatial correlation.

**Albedo escalation test (project decision rule).** Within calibration cells at least 50% of one class, albedo against surface temperature:

| Class | Cells | r |
|---|---|---|
| Built | 6 | +0.21 |
| Bare | 157 | +0.55 |
| Canopy | 65 | −0.31 |
| Paved | 0 | not computable |

The rule says escalate to Sentinel-2 B11 if the built-class correlation exceeds +0.2, and it does, narrowly. A correlation from 6 cells is close to noise. The stronger evidence is the count itself: only 6 majority-built cells in a dense commercial window shows OSM footprint coverage is too sparse, which is exactly what the rule is designed to detect. The albedo–temperature confounding sits in the bare class.

## The albedo coefficient is published, not fitted

We attempted to fit the albedo coefficient from observation, recovered the wrong sign, diagnosed it as confounding between albedo and surface moisture in the pre-monsoon season, and therefore take this one coefficient from published measurement while fitting the rest.

The evidence:
- In the Day 2 fit on 30 m pixels, albedo and surface temperature correlated at **+0.45 within impervious-dominant cells** and **−0.05 within canopy-dominant cells**.
- Brighter non-vegetated ground was hotter, because in March–May the brightest ground is also the driest.
- On 90 m cells the pattern persists where it should: +0.55 within bare-dominant cells.

A brightness coefficient fitted on that data measures dryness, not what a reflective coating does.

The published coefficient comes from Ko et al. (2022). Raising pavement albedo from 0.08 to 0.26 on real Los Angeles streets reduced surface temperature by 0.9 °C at 09:00 and 5 °C at 15:00 (2.7 °C per 0.1 albedo). Our overpass is 10:57, between the two, so both ends are carried: 5.0 and 27.0 °C per unit albedo. Santamouris (2013) summarises a comparable "close to 2.5 K" per 0.1 from a separate field test.

Limitations:
- Los Angeles is not Pune.
- These are pavement measurements taken from close range, not satellite observations of a 90 m mixture of surfaces.

That is why the output is a band. Any layout containing a reflective intervention reports its temperature change as a low/high band, and the optimizer ranks on the less-cooling end.

## Superseded: Day 2 fit on 30 m pixels

For the record: fitted on 30 m pixels, with an NDVI "impervious" class and a fitted albedo term, the model gave:

| Quantity | Value |
|---|---|
| `t_base_c` | 41.25 °C |
| `k_canopy` | +2.39 |
| `k_albedo` | **−27.92 (wrong sign)** |
| `k_impervious` | +1.34 |
| Hold-out RMSE | 1.83 °C (baseline 2.18 °C) |
| Hold-out R² | 0.30 |

Pixels observed at 44–48 °C were predicted at 41–44 °C. That attenuation is regression dilution from fitting 30 m regressors against a 100 m thermal signal. It led to the 90 m calibration cells and the published albedo coefficient above.

## Street design and intervention delta (Day 3)

- **Design grid.**
  - A 200 m segment centred on the longest straight OSM way of FC Road (way 281308015, 955 m, "Gopal Krushna Gokhale Path").
  - 40 m across, with 20 m either side of the centreline, in 2 m cells: 100 × 20 = 2,000 cells, oriented to the segment's bearing.
- **Street cross-section.**
  - OSM tags FC Road as 2 lanes, which would make a 7 m carriageway, but its sidewalks are mapped as separate lines further out.
  - The carriageway edge on each side is taken from the median offset of the mapped sidewalk lines along the segment, less half a sidewalk width.
  - Cells between the centreline and those edges are carriageway, and the sidewalk band is footway. Canopy over the road is kept as canopy.
  - Where a side has no mapped sidewalk, half the lane-count width is used.
- **Baseline today, per 2 m cell.**
  - The baseline model for the cell's surface class, plus the measured-minus-modelled residual of the 90 m calibration cell it sits in, so local heat the model does not explain is kept.
  - This is what "hottest cell" means for the greedy baseline.
- **Temperature change of a layout.**
  - The mean change in modelled surface temperature over all 2,000 design cells, including buildings.
  - Because the model is linear, that equals applying the 90 m coefficients to the changed area shares.
- **Tree.**
  - Planted on a cell, its crown covers every cell within 4 m of the pit (13 cells, 52 m²), which become canopy.
  - Gain per crown cell: −k_canopy over paving, −k_canopy − k_bare over bare ground, −k_canopy − k_built over a roof, and nothing over existing canopy. Overlapping crowns count once.
- **Reflective coating.**
  - Carriageway is assumed to be aged asphalt, the footway aged concrete, and the coating albedo 0.50 (all cited ranges).
  - The change is −k_albedo × Δalbedo. The most-cooling end pairs the largest albedo gain with the high coefficient; the least-cooling end pairs the smallest gain with the low one.
  - A coated cell under a new crown gains nothing from the coating.
- **Permeable paving.**
  - A paved footway becomes bare-like ground, using the fitted k_bare.
  - With k_bare positive in the pre-monsoon fit, that is a warming change. It is modelled honestly and left out of the Day 3 budget.
- **Shade structures.** No cited effect and no fitted coefficient, so they are not allowed anywhere yet.

### Street design assumptions

Each gives the value, the reasoning, and what changing it would change.

- **Segment and corridor (200 m × 40 m).**
  - Reasoning: long enough to contain a meaningful layout, straight enough for one bearing, and wide enough to reach the building line on FC Road, while staying under the 4,000-cell cap.
  - What it changes: a longer segment gives more cells and a slower search. A wider corridor takes in more private setbacks.
- **Mature crown diameter 8 m, equal to the cited minimum spacing.**
  - Reasoning: at the minimum spacing, mature crowns just meet.
  - What it changes: larger crowns give each tree more cooling and more overlap. Saplings are far smaller than this for years, so the tree effect describes maturity, not planting day.
- **Sidewalk width 2.5 m where OSM has none (IRC:103 commercial minimum).**
  - Reasoning: the code minimum for FC Road's land use.
  - What it changes: below the cited 4.3 m needed for a tree, so **no trees are allowed on footways at all.** Trees can only go on bare ground in the corridor, which includes private setbacks and open plots. A measured sidewalk width of 4.3 m or more would open footways to planting.
- **Existing surfaces: aged asphalt carriageway, aged concrete footway.**
  - Reasoning: FC Road is tagged `surface=asphalt`; its mapped sidewalks carry no surface tag.
  - What it changes: a brighter existing surface means a smaller albedo gain from coating, and less cooling.
- **Lane width 3.5 m, and carriageway width by road class where OSM has no lanes** (primary and trunk 14 m, secondary 10.5 m, tertiary 7 m, residential and unclassified 6 m, living street 5 m, service 4 m, links 7 m).
  - Reasoning: conventional urban values, not cited.
  - What it changes: wider roads mean more paved and less bare area in calibration, which shifts `t_base_c` and k_bare.
- **Budget matched by count, not by rupees.**
  - Reasoning: no Indian cost figure of adequate quality has been found for street trees with three years of establishment, pavement coatings or pervious concrete. Weak figures exist, such as a 2009 Delhi scheme fee and roof-coating prices, but they do not meet rule 7. SPEC.md §6.4 defines the random baseline by count ("same number of interventions"), so all three arms get the same number of trees and coated cells, and the cost term is zero until costs are sourced (Day 4).
  - What it changes: the comparison tests placement. It does not test the trade-off between trees and coatings, which needs real costs.
- **Greedy places trees first, then coatings, each on the hottest valid cell.**
  - Reasoning: "place at the currently hottest valid cell" does not say which intervention goes first.
  - What it changes: trees-first lets coatings avoid new crowns, which favours greedy.

### Day 3 result, FC Road segment

**Design grid.**
- 100 × 20 cells at 2 m, bearing 352.3°, origin (377672.6, 2048042.7) in EPSG:32643.
- Surfaces: 791 canopy, 768 bare, 234 carriageway, 207 built, 0 footway.

**Budget.** 20 trees and 150 reflective cells (600 m²) for every arm. GA settings: population 120, 400 generations.

Mean change in modelled surface temperature over the design area. The low end is more cooling; the high end is the conservative figure the arms are ranked on.

| Arm | Band | Conservative cooling |
|---|---|---|
| Random, mean of 30 seeds | high end −0.952 °C (best −1.001, worst −0.886) | 0.95 °C |
| Greedy, hottest cell first | −1.565 to −0.868 °C | 0.87 °C |
| GA, seed 0 | −1.823 to −1.125 °C | 1.13 °C |
| GA, seed 1 | −1.824 to −1.126 °C | 1.13 °C |
| GA, seed 2 | −1.819 to −1.121 °C | 1.12 °C |

Figure: [figures/pune-fc-road-layouts.png](figures/pune-fc-road-layouts.png).

- **The GA beats greedy and the best of 30 random layouts on every seed.** The three seeds agree within 0.005 °C and stop improving by about generation 200.
- **Greedy does worse than random, and that is expected.** In a linear model, how much an intervention gains at a cell does not depend on how hot the cell is now. "Hottest first" therefore crowds trees and coatings into the hot south end of the segment, where crowns overlap each other and existing canopy.

**Not yet physically credible: the cross-section.**
- No sidewalk is mapped in OSM within 117 m of this segment, so the carriageway fell back to the 7 m implied by the two-lane tag.
- The building lines sit about 13 m either side of the centreline. The strips between the 3.5 m carriageway edge and the buildings therefore count as bare ground wherever there is no canopy, and trees are allowed there.
- Greedy placed 6 trees 5 m from the centreline, and the GA placed 6 trees 7–9 m out. Those positions are very likely real carriageway, parking or footpath.
- The GA's advantage is real within the model as specified. The layouts are not credible street designs until FC Road's actual cross-section is known. Pune Municipal Corporation's *Urban Street Design Guidelines* (2016) are the first source to check.

**The magnitudes depend on uncertain coefficients.**
- A crown over bare ground gains k_canopy + k_bare = 7.8 °C per cell. Both coefficients carry standard errors of about 1 °C.
- The coating band spans a factor of seven (1.5 to 10.8 °C per asphalt cell).

## Earlier data-layer assumptions

### Scene-level cloud cover pre-filter: `SCENE_CLOUD_COVER_MAX_PERCENT = 40`
- **Reasoning.** A cheap pre-filter to avoid downloading mostly cloudy scenes; per-pixel masking is the real filter. Scene cloud cover is computed over a ~185 km scene, so a scene at 30% can still be clear over a 2 km window.
- **What it changes.** Lowering it discards partly cloudy scenes whose window may be clear. Raising it adds downloads that mostly get masked. It does not change which pixels count as clear.

### ST_QA uncertainty cut-off: `ST_QA_MAX_UNCERTAINTY_K = 5.0`
- **Reasoning.** USGS publishes the uncertainty band but no recommended cut-off. ST_QA grows near clouds, so it catches cloud-adjacent pixels QA_PIXEL misses. 5 K removes only clearly degraded observations.
- **What it changes.** Tighter removes more cloud-edge contamination and more valid observations. Looser lets more in; the median resists a minority.

### Minimum clear observations per pixel: `MIN_CLEAR_OBSERVATIONS = 5`
- **Reasoning.** A median of 5 tolerates 2 contaminated observations.
- **What it changes.** Higher gives more nulls; lower lets single-scene artefacts through.

### Landsat grid alignment: `LANDSAT_GRID_ORIGIN_OFFSET_M = 15`
- **Reasoning.** Observed from `proj:transform` on real Collection 2 items; windows are snapped to it so reads need no resampling.
- **What it changes.** If wrong, every read raises. It cannot silently shift data.

### Date window: March–May of 2024, 2025 and 2026
- **Reasoning.** June–September is monsoon, and cloud filtering leaves almost nothing. March–May is the pre-monsoon hot season, when skies are clearest (SPEC.md §4.2).
- **What it changes.** The composite describes a typical pre-monsoon state, not a specific day.

### Calibration window: 67 × 67 Landsat cells (2,010 m square)
- **Reasoning.** Nearest odd cell count to 2 km, keeping the window centred on a cell.
- **What it changes.** Larger windows include areas unlike the street; smaller ones give fewer independent measurements.

### Window centre and street extent
- **Reasoning.** The window was centred on a placeholder extent before OSM geometry existed. FC Road's verified OSM extent is now stored in fixture metadata. Its centre lies about 260 m north of the placeholder's, and about 180 m of the road's north end falls outside the window.
- **What it changes.** The design segment and calibration are unaffected. Re-centring would change the cached window and every number above.

### Broadband albedo from Landsat surface reflectance (Liang 2001)
- **Reasoning.** Liang's coefficients were derived for TM/ETM+ bands; applying them to the equivalent OLI bands is a common approximation. Albedo is now used only for the escalation test, not in the model.
- **What it changes.** An error here scales the albedo diagnostic correlations slightly. It does not affect the fitted model.

### Sentinel-2 SCL classes kept
- **Reasoning.** Only classes 0, 3, 8, 9 and 10 are masked (SPEC.md §4.3).
- **What it changes.** Class 2 (dark area) includes building shadow, and class 7 (low-probability cloud) sometimes includes bright roofs. Masking either would bias against dense built-up pixels.

### Water: `NDVI_WATER_MAX = 0.0`, `WATER_FRACTION_MAX_FOR_FIT = 0.25`
- **Reasoning.** Negative NDVI is the usual signature of open water. In this window it covers 0.2% of 10 m pixels, scattered. They are warmer than average, so not open water. The exclusion was chosen from that distribution before any fit.
- **What it changes.** At 90 m no cell exceeds 25% water, so nothing is excluded.

### NDVI thresholds used as class boundaries (Sobrino et al. 2004)
- **Reasoning.** The 0.5 full-vegetation threshold separates vegetation from soil for emissivity estimation. Using it as the canopy class boundary is our choice.
- **What it changes.** Lowering it counts sparser or drier vegetation as canopy, moving area out of "bare".
