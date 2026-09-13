# Methodology and limitations

Every assumption made in the build is recorded here, in the same commit that introduces it. Cited constants are in [sources.md](sources.md).

## Data acquisition

**Adapter.** Satellite data is pulled through Microsoft Planetary Computer's public STAC API (`planetary_computer` adapter). Earth Engine was the preferred adapter, but no Earth Engine project was registered on the build machine on Day 1. `EarthEngineSource` exists but has not yet been run against a live account.

**No resampling of measured values.** Landsat surface temperature is read on its native UTM grid (EPSG:32643 for Pune), and any window that does not land exactly on that grid raises an error. Sentinel-2 reflectance is read on its own native 10 m grid. The only cross-grid operation is summarising 10 m land cover onto 30 m cells, which aggregates land-cover fractions by exact area overlap and never touches a temperature.

**Compositing.** Each product is a per-pixel median across all clear observations in the date window, never a single scene. For the FC Road window that is 30 Landsat scenes and 46 Sentinel-2 scenes across March–May of 2024, 2025 and 2026. Every one of the 4,489 Landsat pixels has at least 29 clear observations.

**Overpass time.** The median acquisition time of the Landsat scenes used is 10:57 IST (about 05:27 UTC); Sentinel-2's is 10:56 IST. SPEC.md describes Landsat's overpass as "around 10:30 local time". That matches local solar time at Pune (73.84° E is 4 h 55 min ahead of UTC, giving about 10:22), but the clock time a reader in Pune would recognise is nearer 11:00. Either way this is mid-morning land surface temperature, not the mid-afternoon peak. The interface states the measured clock time from `provenance.overpass_local_time` rather than a constant.

**Sentinel-2 offset.** From processing baseline 04.00 (January 2022), Sentinel-2 L2A digital numbers carry an additive offset. Planetary Computer serves them without the offset applied; this was checked against real scenes (see sources.md). The adapter reads the offset from each product's own metadata, applies it, and records that it did.

## Assumptions

Each entry gives the value, the reasoning, and what changing it would change.

### Scene-level cloud cover pre-filter: `SCENE_CLOUD_COVER_MAX_PERCENT = 40`
- **Reasoning.** This is a cheap pre-filter to avoid downloading mostly cloudy scenes. The real cloud filter is per-pixel masking (QA_PIXEL for Landsat, SCL for Sentinel-2). Scene cloud cover is computed over a ~185 km Landsat scene, so a scene at 30% can still be clear over a 2 km window.
- **What it changes.** Lowering it discards partly cloudy scenes whose window may be clear, so fewer observations per pixel. Raising it adds downloads that mostly get masked out. It does not change which pixels count as clear.

### ST_QA uncertainty cut-off: `ST_QA_MAX_UNCERTAINTY_K = 5.0`
- **Reasoning.** USGS publishes the ST_QA uncertainty band but no recommended cut-off. ST_QA grows with distance-to-cloud effects, so it catches cloud-adjacent pixels that QA_PIXEL misses. 5 K is deliberately loose: it removes only clearly degraded observations and leaves the median to absorb the rest.
- **What it changes.** A tighter cut-off (for example 2 K) removes more cloud-edge contamination but also more valid observations, and it biases the composite toward the clearest, driest days. A looser one lets more cloud-cooled observations into the stack; the median still resists a minority of them.

### Minimum clear observations per pixel: `MIN_CLEAR_OBSERVATIONS = 5`
- **Reasoning.** A median of 5 tolerates up to 2 contaminated observations. With roughly 30 Landsat scenes across three seasons, most pixels should comfortably exceed this. Pixels that don't are left `null` rather than represented by one or two scenes.
- **What it changes.** Higher values give more nulls and more robust values. Lower values give fewer nulls but let single-scene artefacts through.

### Landsat grid alignment: `LANDSAT_GRID_ORIGIN_OFFSET_M = 15`
- **Reasoning.** Observed from `proj:transform` on real Collection 2 items: the upper-left edge 269985 is 15 m past a multiple of 30. Windows are snapped to this grid so reads need no resampling.
- **What it changes.** If it were wrong, every read would raise, because the adapter checks each scene's own transform. It cannot silently produce shifted data.

### Date window: March–May of 2024, 2025 and 2026
- **Reasoning.** June–September is the southwest monsoon; cloud filtering over those months leaves almost nothing, and what survives is unrepresentative. March–May is the pre-monsoon hot season, when the surface heat signal is strongest and skies clearest. Three seasons give the median enough clear scenes (SPEC.md §4.2).
- **What it changes.** The composite describes a typical pre-monsoon state, not a specific day and not an annual average. Adding months into June would add cloud-masked noise. Fewer years would give fewer observations per pixel.

### Calibration window: 67 × 67 Landsat cells (2,010 m square)
- **Reasoning.** SPEC.md asks for a 1.5–2 km window. 67 cells is the nearest odd count to 2 km on the 30 m grid, keeping the window centred on a cell.
- **What it changes.** A larger window gives more pixels and more land-cover variety for calibration, but may include areas unlike the street (the river, hills). A smaller one gives fewer independent measurements; the thermal band is natively 100 m, so 30 m pixels are not independent.

### Window centre: placeholder street extent
- **Reasoning.** FC Road's `bbox_street` is a placeholder from SPEC.md, not a verified extent. The window is centred on its centre, and fixture metadata carries `bbox_street_verified: false`. It will be corrected when OSM geometry lands (Day 3).
- **What it changes.** A 2 km window is robust to a centre error of a few hundred metres. The street-scale results on Day 3 are not.

### Broadband albedo from Landsat surface reflectance
- **Reasoning.** The heat model needs an albedo term per calibration pixel, and material albedo tables cannot supply one: we do not know the material of every 30 m pixel in a 2 km window. So measured albedo is derived from the same Landsat scenes and masks as surface temperature, on the same grid, using Liang (2001).
- **What it changes.** Liang's coefficients were derived for TM/ETM+ bands, and applying them to the equivalent OLI bands is a common approximation, not an exact conversion. An error here scales the fitted albedo coefficient, but does not move the temperatures.

### Sentinel-2 SCL classes kept
- **Reasoning.** Only classes 0 (no data), 3 (cloud shadow), 8 and 9 (cloud medium and high probability) and 10 (cirrus) are masked, per SPEC.md §4.3. Class 1 (saturated or defective), 2 (dark area) and 7 (low-probability cloud or unclassified) are kept.
- **What it changes.** Class 2 includes building shadow in dense areas, so masking it would bias against dense built-up pixels. Class 7 is kept to avoid over-masking bright roofs, which the scene classifier sometimes confuses with cloud.

### Water in NDVI: `NDVI_WATER_MAX = 0.0`
- **Reasoning.** Open water is the common surface with NDVI below zero, and it has to be kept out of the "impervious" class.
- **What it changes.** In the FC Road window only 0.2% of 10 m pixels fall below zero, so moving this threshold moves almost nothing into or out of the impervious class.

### Water cells left out of calibration: `WATER_FRACTION_MAX_FOR_FIT = 0.25`
- **Reasoning.** This was chosen from the land-cover distribution alone, before any model was fitted. 52 of the 4,489 cells contain any NDVI-below-zero pixel. Those cells are scattered across the whole window, and 36 of them hold at most one 10 m pixel's worth. Their mean surface temperature is 42.4 °C against a window mean of 41.0 °C, so they are not open water, which would be cooler. More likely they are isolated dark roofs or deep shadow. Only 9 cells are more than a quarter "water", and those are excluded as possible real water.
- **What it changes.** Excluding every cell with any water would drop 52 cells on the strength of single noisy pixels. Excluding none would let a few possible water cells into the fit. Either way it is under 1.2% of the window.

### NDVI thresholds used as land-cover classes
- **Reasoning.** The model needs canopy and impervious fractions. Sentinel-2 NDVI at 10 m is the only land-cover measurement in Tier 1. The Sobrino et al. (2004) thresholds (0.2, 0.5) are well established, but they were set to separate soil from vegetation for emissivity estimation; using them as class boundaries is our choice.
- **What it changes.** See the land-cover limitations below. Moving the canopy threshold down counts sparser or drier vegetation as canopy. Moving the bare-soil threshold up counts more sparse vegetation as impervious.

## What is measured and what is modelled

Three resolutions coexist, and the rendered result is not a measurement.

| Layer | Resolution | What it is |
|---|---|---|
| Measurement | 30 m delivered, 100 m native | Real Landsat land surface temperature: a per-pixel median of 30 scenes. |
| Calibration | 2 km window (67 × 67 cells, 4,489 pixels) | Where the model's four coefficients are fitted. |
| Intervention design | 2 m cells | The resolution at which a tree or a coating is physically placed. |
| Rendered before/after surface | 2 m | **A model output at design resolution, not a measurement.** |

Interventions placed at 2 m change the land-cover fractions and albedo inside each 30 m model cell, and the calibrated model turns those changes into a modelled temperature change. The interface labels the 30 m data "measured" and the 2 m surface "modelled".

Because the thermal band is natively 100 m, a 150 m street contains only one or two independent thermal measurements. That is why the model is never fitted on a street's own pixels.

## Surface temperature, not air temperature

Landsat measures land surface temperature: the radiometric temperature of roofs, roads, bare ground and canopy tops, seen from above at about 11:00 IST. It is not the air temperature a person feels at head height, and the two can differ substantially on hot, dry, sunlit surfaces. Every string in the product says "surface temperature". No copy says a person will feel a change.

## Land cover from NDVI

Each 10 m Sentinel-2 pixel is classed by the NDVI of its median red and near-infrared reflectance. Each 30 m cell's fraction is the share of its observed area in each class, by exact area overlap (the two grids share a 5 m sub-grid).

| Class | NDVI | Share of 10 m pixels, FC Road window |
|---|---|---|
| Water | below 0 | 0.2% |
| Impervious | 0 to below 0.2 | 27.5% |
| Mixed (the model's reference class) | 0.2 to below 0.5 | 46.2% |
| Canopy | 0.5 and above | 26.2% |

Limitations, stated plainly:
- **"Impervious" is really "non-vegetated".** NDVI cannot tell pavement and roofs from bare dry soil. Pre-monsoon Pune has open plots, college grounds and dry hillsides with NDVI as low as concrete, and all of them land in this class.
- **"Canopy" is any vigorous green vegetation.** In March–May that is mostly trees and irrigated lawns, but a well-watered lawn counts the same as a tree canopy.
- **The mixed class absorbs everything in between**, including sparse and dry vegetation, and it is the baseline the model's `t_base_c` refers to.

## Calibration method

- Pixels are usable when they have a Landsat value and full Sentinel-2 coverage, and are not more than 25% water.
- 20% of usable pixels are held out at random (seed 42). The model is fitted by ordinary least squares on the rest.
- `rmse_holdout_c` is the error on held-out pixels. `rmse_mean_baseline_c` is the error from predicting every held-out pixel as the mean of the fitting pixels. `r2_holdout` is computed on held-out pixels only.
- Albedo enters as the difference from the mean albedo of the fitting pixels, so `t_base_c` is the modelled surface temperature of a cell with no canopy, no impervious surface and average albedo.

What the hold-out error does and does not show:
- **It measures misfit within this neighbourhood.** With four parameters and thousands of pixels, overfitting is not the risk, so hold-out and in-sample error come out close.
- **It does not show transfer to other neighbourhoods.** Held-out pixels are not spatially independent of fitting pixels: at 100 m native resolution, neighbours share a thermal footprint.
- **The printed coefficient standard errors are optimistic** for the same reason. They are a diagnostic, not confidence intervals.

## Calibration result, FC Road window (Day 2): fails the plausibility check

| Quantity | Value |
|---|---|
| `t_base_c` | 41.25 °C |
| `k_canopy_c_per_fraction` | +2.39 |
| `k_albedo_c_per_unit_albedo` | **−27.92 (wrong sign)** |
| `k_impervious_c_per_fraction` | +1.34 |
| `rmse_holdout_c` | 1.83 °C |
| `rmse_mean_baseline_c` | 2.18 °C |
| `r2_holdout` | 0.30 |
| Pixels | 3,584 fitted, 896 held out, 9 excluded as water |

Scatter: [figures/pune-fc-road-calibration.png](figures/pune-fc-road-calibration.png).

**These coefficients must not be used to evaluate interventions.**

- **Signs.** Canopy cools and impervious surface warms, as expected. Albedo does not: the fit says a brighter cell is hotter, by about 0.28 °C per 0.01 of albedo. Used by the optimizer, that would rank a high-albedo coating as a warming intervention.
- **Why albedo flips.** It is confounding, not a coding error:
  - Within cells that are at least 60% "impervious", albedo and surface temperature correlate at +0.45; within canopy-dominant cells, at −0.05.
  - The brightest fifth of cells averages 42.18 °C, with 0.43 impervious and 0.17 canopy fraction. The other four fifths average 40.5–41.0 °C.
  - The NDVI "impervious" class includes dry bare ground. In March–May at about 11:00, that ground is both brighter than asphalt and hotter, because it is dry. Albedo is acting as a proxy for dry, non-vegetated ground, not as a cooling surface property.
- **Albedo adds little.** Fitting without the albedo term gives hold-out RMSE 1.88 °C and R² 0.26, against 1.83 °C and 0.30 with it.
- **The fit is weak and flattened.** Pixels observed at 44–48 °C are predicted at 41–44 °C. The surface temperature map shows the blocky structure of the 100 m native thermal band, while the land-cover regressors carry 30 m detail the thermal band cannot see. That scale mismatch weakens the fitted coefficients (they are biased toward zero) and compresses the predictions.
- **Status.** The model is not calibrated to a usable standard. The fix is an open decision, recorded in the Day 2 report, not made silently here.
