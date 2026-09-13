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
