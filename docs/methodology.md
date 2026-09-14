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
| Built | Building footprint: OSM, plus Microsoft and Google footprints via Overture (Day 4) | 22.7% (19.4% with OSM alone) |
| Paved | OSM highway way, buffered to its tagged or estimated width | 7.7% |
| Water | NDVI below 0 | under 0.1% |
| Bare | everything else | 42.9% |

Limitations, stated plainly:
- **Building footprints are still incomplete.** With OSM alone, only 6 of 484 calibration cells in dense commercial FC Road were at least half built. Adding 2,686 Microsoft and Google footprints (Day 4) raised that to 9, and the built share from 19.4% to 22.7%: the added footprints are mostly small roofs. Unmapped roofs still fall into "bare".
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

## Calibration result, FC Road, with merged footprints (Day 4, current)

**Building footprints.** OSM footprints from our own Overpass pull, unioned with the non-OSM footprints in Overture Maps release 2026-08-19.0 (sources.md, [B1]). Overture's own OSM rows are skipped, since OSM comes from Overpass. A non-OSM footprint whose centroid falls inside an OSM footprint, or within 5 m of an OSM footprint's centroid, is a duplicate and dropped. Every building carries `footprint_source`.

| FC Road window | Count |
|---|---|
| OSM (Overpass) | 3,222 |
| Google Open Buildings added | 2,283 |
| Microsoft ML Buildings added | 403 |
| Dropped as duplicates | 6 |
| Dropped below confidence 0.65 | 0 |

**Refit.** Same cells, split and seed as before. Bare is the best-supported class (mean share 42.9%), so it is the reference in the report. All pairwise contrasts, as a full cell of the first class minus a full cell of the second:

| Contrast | °C | Standard error | \|z\| |
|---|---|---|---|
| canopy − bare | −7.98 | 0.40 | 19.9 |
| built − bare | −4.45 | 0.58 | 7.7 |
| paved − bare | −2.29 | 1.17 | 2.0 |
| canopy − built | −3.53 | 0.62 | 5.7 |
| canopy − paved | −5.68 | 1.11 | 5.1 |
| built − paved | −2.16 | 1.35 | 1.6 |

| Quantity | Value |
|---|---|
| Fully bare cell | 44.27 °C (se 0.23) |
| `t_base_c` (fully paved cell, contract field) | 41.98 °C (se 1.08) |
| `k_canopy_c_per_fraction`, `k_built_c_per_fraction`, `k_bare_c_per_fraction` | +5.68, −2.16, +2.29 |
| `rmse_holdout_c` / `rmse_mean_baseline_c` | 1.40 °C / 2.03 °C |
| `r2_holdout` | 0.53 |

What changed and what did not:
- **Built cooler than paved is no longer a tight result.** It is −2.16 ± 1.35 °C (|z| 1.6); with OSM alone it was −2.97 ± 1.28.
- **Built cooler than bare is robust.** Roofs are about 4.4 °C cooler than bare ground at the 10:57 overpass, |z| 7.7. Plausible reasons: shading between buildings, and roofs heating more slowly in the morning than dry exposed soil. This is a finding about this neighbourhood at mid-morning, not about roof materials in general.
- **Hold-out error is unchanged within noise** (1.36 → 1.40 °C). Better footprints moved area between classes but did not add explanatory power.
- **Changing the reference class cannot fix the paved coefficient.** Shares sum to one, so choosing the reference is a reparameterisation: predictions, error, every pairwise contrast and its standard error are identical under any choice. Paved − anything is uncertain because paved surface is only 7.7% of the window and majority nowhere. More paved area in the data (better carriageway widths), not a different reference, is what would tighten it. The contract keeps the k fields relative to paved and adds `contrasts` with standard errors and `fit_reference_class`.
- **Sentinel-2 B11 escalation rule: retired.** Within majority-built cells, albedo still correlates with surface temperature (r = +0.58, n = 9); the rule would fire again. The rule was meant to detect sparse footprints, and footprints are now addressed directly. NDBI from B11 confuses dry bare soil with roofs, the confound this model avoids. The correlation stays as a diagnostic in the calibration output.

## Superseded: calibration result with OSM footprints only (revision 4 model, Day 3)

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

## Day 4: costs, cross-sections and the design-guideline baseline

### Costs

- **What is priced.** Street trees only: planting in a 0.6 m × 1 m hole with manure, the sapling, fixing a guard and one year of maintenance, plus the guard itself. ₹3,720 to ₹5,902 per tree, from the Government of Rajasthan's RUIDP *Integrated Schedule of Rates 2023* (sources.md, [C1]).
- **What is not priced.** Reflective pavement coating, pervious concrete and shade structures. No Indian government rate schedule with these items could be opened within the 90-minute timebox; sources.md lists every source tried and why it failed.
- **What that means for the product.**
  - A layout that uses any unpriced intervention has **no cost**: `cost_inr_low` and `cost_inr_high` are null, and `unpriced_interventions` names what is missing. The UI drops cost from the headline rather than showing a partial sum or an estimate.
  - The comparison is matched by count (trees, coated cells), and counts are in every comparison arm so the match is checkable.
  - A rupee budget (`budget_inr_max`) is accepted only when no unpriced intervention is allowed (`reflective_cells_max = 0`). It then caps the tree count at the budget divided by the high end of the per-tree range, so total cost stays within budget at the conservative end.

Cost assumptions:
- **Jaipur 2023 rates stand in for Pune.** Reasoning: no Pune or Maharashtra schedule could be opened. What it changes: labour and material rates differ between states; the range is an order-of-magnitude estimate, labelled as such.
- **First-year care only.** SPEC.md §8 asks for three years of establishment care; years two and three have no sourced rate, so the range understates a three-year cost. What it changes: a three-year figure would be higher by the cost of two more years of watering and maintenance.

### Cross-section

The Day 3 layouts put trees 5–9 m from FC Road's centreline, very likely in carriageway or parking, because the corridor between a 7 m carriageway and the building line was treated as plantable bare ground. The cross-section now decides where interventions may go, and is labelled by source (`CrossSection.source`):

1. **`osm_tag`**: used when the OSM way tags carriageway width and both sidewalk widths. No Pune street surveyed has these tags.
2. **`published_design`**:
   - The right of way is measured from building footprints: at 2 m stations along the segment, the distance to the first building edge on each side within 30 m, median over stations.
   - It is divided by the PMC *Urban Street Design Guidelines* (2016) template for that width: the widest template no wider than the right of way, with spare width added to the outer footways (sources.md, [D3]).
   - This is Pune's own street design standard applied to the measured width, **not a survey of the street as built**. The reference string says so, and the UI must label the cross-section as assumed.
3. **`default_assumption`**: carriageway from lanes or road class, IRC:103 minimum sidewalks, and **no plantable band**, so no trees.

Rules that follow from the cross-section:
- Trees go only in `tree_pit` bands, never on a building or existing canopy.
- Coatings go only on carriageway, footway and cycle track inside the right of way.
- Nothing goes on private property outside the right of way, which removes the Day 3 plantings in private setbacks.
- **Today's surface inside the right of way** follows the bands where the land cover shows neither canopy nor building: carriageway as asphalt, footway, cycle track and tree pits as paved footway, buffers and medians as bare.

Cross-section assumptions:
- **Right of way measured to building edges.** Reasoning: no surveyed widths exist in OSM for these streets. What it changes: buildings set back behind compound walls or front yards make the measured right of way wider than the public street. FC Road's segment measures 28.2 m and takes template 24A; the public street is likely narrower. A narrower measure picks a smaller template with fewer and narrower tree pits.
- **30 m search reach, 30% of stations must hit a building on each side.** Reasoning: long enough for arterial setbacks, short enough to stay on the street. What it changes: a longer reach finds buildings across open ground and inflates the right of way; fewer stations makes the median noisier.
- **Template 21A's clear walkway is taken as 3.5 m.** Reasoning: the section's labelled widths sum to 21.5 m, while the plan view gives 8 m for that side of the carriageway. What it changes: 0.5 m of walkway on one side of 21 m streets.
- **15A and 24A bus-stop zones are recorded as tree pits.** Reasoning: the sections are drawn through a bus stop; the plan views show tree pits in that zone along the rest of the street. What it changes: without it those templates have trees on one side only, halving tree capacity.

### Baselines

- **Greedy is kept, and labelled weak.** In a linear model, an intervention's gain at a cell does not depend on how hot the cell is, so "hottest cell first" is not a sensible heuristic; beating it is not a claim.
- **`design_guideline_layout()` is the counterfactual that matters.** It is what a competent street designer would do with the same budget, with no optimisation:
  - Trees split evenly between the plantable strips on the two sides, each evenly spaced along the segment at no less than the IRC:SP:21 minimum of 8 m.
  - Coating on whole rows of paving not under a new crown, a contiguous run of the widest rows.
- **Matched budget.** Every arm gets the same tree count, capped at the most trees the plantable strips physically hold at 8 m spacing (`StreetGrid.tree_capacity()`), and the same number of coated cells. Without the cap, arms placed different numbers of trees when the request exceeded capacity.
- **The GA is not seeded with the guideline layout**, so matching or beating it is not guaranteed by construction.

### Permeable paving and shade structures stay out of the action set

- **Permeable paving warms in this model.** A paved footway made pervious is modelled as bare-like ground, and bare is 2.3 °C hotter than paved in the pre-monsoon fit.
- **That agrees with the albedo literature.** Pervious concrete is 0.05–0.20 less reflective than conventional concrete (Lu et al. 2023; Zhang et al. 2015; sources.md, [M2], [M3]).
- **Any cooling would come from evaporation**, which needs moisture that pre-monsoon Pune surfaces lack and which this model does not represent. It is left out, not tuned to look useful.
- **Shade structures** have no cited surface temperature effect and no fitted coefficient.

### Day 4 result: four arms on four streets

**Setup.**
- 200 m segment on each street, 2 m design grid, cross-section from template 24A on every street (measured right of way 26.2–28.2 m).
- The same budget for every arm: 20 trees and 150 reflective cells (600 m²).
- GA: population 120, 400 generations, 3 seeds. Random: mean of 30 seeds.
- Cost is null for every arm, because coating is unpriced.

Conservative cooling is the high end of the band, i.e. the smallest modelled drop in mean surface temperature over the design area:

| Street (profile) | Random | Greedy | Design guideline | GA (worst seed) | GA over guideline |
|---|---|---|---|---|---|
| FC Road (mixed) | 0.706 °C | 0.629 °C | 0.683 °C | 0.801 °C | +0.118 °C |
| Karve Road (wide arterial) | 0.933 °C | 0.832 °C | 0.933 °C | 1.045 °C | +0.112 °C |
| North Main Road (leafy residential) | 0.757 °C | 0.747 °C | 0.728 °C | 0.810 °C | +0.082 °C |
| Bajirao Road (dense commercial) | 0.725 °C | 0.682 °C | 0.699 °C | 0.781 °C | +0.082 °C |

Figures: `figures/<street-id>-layouts.png`.

- **The GA beats the design guideline on every street and every seed**, by 0.08–0.12 °C conservative. That is 11–17% more modelled cooling from the same trees and coating.
- **The guideline is not a strong baseline in this model.** It ties random on Karve Road and loses to it on North Main Road. Evenly spaced trees still overlap existing canopy, and the widest paved run is not always where coating pays most. The GA's advantage comes from choosing tree pits clear of existing crowns and coating what the new crowns do not cover.
- **The gap is smaller than the model error.** Hold-out RMSE is 1.2–1.7 °C per 90 m calibration cell. The comparison between arms shares the same coefficients, so the ranking is more robust than the absolute numbers, but none of these differences is measured.
- **The absolute cooling is driven by coefficients with standard errors of about 0.4–1.2 °C**, and by a coating band that spans a factor of seven.

### Day 4 offline run

- **How it ran.**
  - A `sitecustomize.py` guard blocked every non-loopback socket connection and DNS lookup; a test outbound request was refused.
  - The server ran with `USE_LIVE_DATA=false`.
  - For all four streets, a client drove: list streets, thermal (street scope), geometry, calibrate, optimize, the WebSocket until done, and the result.
- **Outcome.**
  - All four streets returned a complete, contract-valid `OptimizationResult`: resolution block, both provenance objects, cross-section and plantable mask.
  - The guard blocked nothing.
  - The integration test (`tests/test_integration_offline.py`) repeats this with the socket guard inside pytest.
- **Progress rate.**
  - The server sent 1.6–3.9 progress messages per second, one per generation, each run taking 116–271 s.
  - The 10 per second cap was never reached, because generations were slower than 0.1 s. Three command-line GA runs were sharing the CPU at the same time.
  - Previews are sent only when the best layout improved since the last message: 60–103 per run.

## Day 5: frontend display

These are display choices, not model constants. They live in `frontend/src/lib/format.ts` and `frontend/src/lib/motion.ts`.

- **Deltas shown to 2 decimals, absolute temperatures to 1.**
  - Reasoning: the arms differ by 0.08–0.12 °C, so one decimal would show the search tying the design guideline on North Main Road.
  - What it changes: two decimals suggest more precision than a 1.2–1.7 °C hold-out RMSE supports. The model error and its mean-only baseline are always on screen next to the delta, so the precision is read against the error.
- **Cost ends rounded outward to 2 significant figures.** The low end is rounded down and the high end up, so rounding never narrows the range. 20 trees at ₹3,720–5,902 each show as ₹74,000–1,20,000. No midpoint is ever computed.
  - What it changes: at most one step of the second significant figure on each end.
- **No cost when any end is null.** A layout using coating shows "Not priced" and names the unpriced intervention. There is no partial sum.
- **Overpass time labelled IST.** `provenance.overpass_local_time` carries no zone. Every street is in Pune, so the zone is Asia/Kolkata.
  - What it changes: nothing today. A street outside India needs the zone from the backend.
- **One colour scale across before and both after bands.** The domain is the minimum and maximum over all three modelled grids, so a colour is the same temperature in every view. The measured window uses its own `stats` range.
- **The convergence curve plots both ends of the best layout's modelled change per generation, not `best_fitness_score`.** The score is a dimensionless objective and is never displayed.
- **The after view defaults to the conservative end** (`after_lst_c_high`), the end the search ranks on. A toggle shows the more-cooling end when the two differ.
- **Both labels are on screen whenever their surface is.** Measured surfaces say "measured, 30 m"; the before and after grid says "modelled at 2 m design resolution". The resolution comes from the payload (`provenance.delivered_resolution_m`, `resolution.design_resolution_m`), never a literal.
- **Stage 03's 2D grid is drawn along the street, not north-up.**
  - Reasoning: FC Road's design grid is a 200 m by 40 m strip. Drawn north-up in a 1440 px window, 2 m cells render about 3 px wide; drawn along the street, about 9 px.
  - What it changes: the view is not a map. The subtitle says it is drawn along the street and gives the bearing. Stage 01's measured window stays north-up on its UTM grid, and the 3D scene (Day 6) returns to true geography.
- **Scrambled characters contain no digits.** A readout still being acquired never shows something that reads as a real number.
- **Decode timing.** The scramble runs exactly as long as the window thermal request. When data lands, rows resolve 90 ms apart at 16 ms per character. That is about 0.6 s for the longest row, and it starts only after the data exists. Returning to stage 01 later shows the final text with no replay.
- **Reveal timing.** 1.5 s, ease-in-out cubic. The grid interpolation and the delta count read one progress value, so they land on the same frame. Cost and the comparison table appear when it lands. `prefers-reduced-motion` skips both motions. (Day 7: the reveal now also drives the 3D ground shader and is started by "Apply the searched layout"; see Day 7, second half.)

## Day 6: 3D scene, before state

Stage 03 opens on a 3D scene; the 2D grid stays one toggle away and still carries the before/after view until the reveal moves into the scene.

**What is drawn:**
- **Ground.** The design grid's `before_lst_c`, one texel per 2 m cell. A fragment shader maps it through the five ramp tokens with the same piecewise-linear interpolation as the 2D canvas, using the same colour domain (before and both after bands). There is no tone mapping, so the colours are the token values.
  - Null cells are discarded.
  - Labelled "modelled at 2 m design resolution" and "Model output, not a measurement".
- **Buildings.** Every footprint the geometry endpoint returns, extruded to `height_m`, merged into one geometry, and drawn in surface colours only. Heights follow the rules in "Building heights" below, and the left panel counts footprints and heights by source.
- **Markers.** The searched layout drawn over the before-state ground. The ground does not include them yet.
  - A tree is a stake plus a flat ring at `TREE_CROWN_DIAMETER_M` (8 m), so it shows the shaded extent without hiding the heat under it.
  - A coated cell is a square outline.
  - Each type is one `<Instances>` draw call.
- **Graticule.** Offset so its 10 m and 50 m lines fall on UTM multiples.

**Display choices:**
- **Scene origin at the design grid centre.** UTM northings near 2 million metres would jitter in GPU floats.
- **Opening camera.** From the street's right-hand side, turned 38° back along it, 40° above the ground, at 0.95 × the segment length, field of view 35°. Orbit is limited to 70° from vertical so no view grazes the ground plane.

**Frame rate, measured on the largest fixture street.** Bajirao Road: 231 buildings, 20 tree markers and 150 coated-cell markers.
- **Setup.** Measured 2026-09-14 in Chrome 152 headless on an Intel Iris Xe (integrated laptop GPU, Direct3D 11), window 1440 × 900.
- **Method.** requestAnimationFrame intervals over 8 s idle, then 8 s while dragging to orbit.
- **Draw calls.** 6 in every run: graticule, ground, building faces, building edges, tree markers, coated markers. The scene is 7,192 triangles.

| Pixel ratio | Canvas | Frame cap | Idle: fps, p95 frame | Orbiting: fps, p95 frame | Worst frame |
|---|---|---|---|---|---|
| 1 | 1030 × 519 | on (120 Hz) | 120 fps, 8.6 ms | 120 fps, 8.6 ms | 9.5 ms |
| 1 | 1030 × 519 | off | 361 fps, 4.3 ms | 279 fps, 5.9 ms | 45 ms |
| 2 | 2060 × 1038 | off | 138 fps, 10.4 ms | 97 fps, 15.5 ms | 73 ms |

- With the cap on, the scene holds the cap: every frame lands inside the 8.3 ms budget.
- At pixel ratio 2 while orbiting, the scene still averages 97 fps with a p95 of 15.5 ms, inside a 60 Hz display's 16.7 ms budget.
- Isolated frames of 38–73 ms appear only with the cap off. They were not investigated.
- **Not measured:** a discrete-GPU machine, a 4K display, or a machine slower than an Iris Xe.

### Building heights (display only)

Height is used only by the 3D scene; the heat model does not use it. Each building's `height_source` says which rule applied.

1. **`osm_tag`:** OSM `height`, else `building:levels` × 3 m.
2. **`estimated_from_area`:** storeys looked up from footprint area, × 3 m.
3. **`default_assumption`:** 6 m, only for a degenerate footprint with zero area.

**Why area.**
- Almost no building next to the streets is tagged: 1–3 of the 131–231 buildings returned per street.
- Across the four 2 km windows, 188 unique OSM buildings carry a positive integer `building:levels`.
- In those, levels rise with footprint area (Spearman ρ = 0.59).

**The table** (`BUILDING_STOREYS_BY_FOOTPRINT_AREA_M2`) is the median `building:levels` per area bin. It was derived on 2026-09-14 with `python -m app.data.heights` and frozen in `config.py`, so adding a street does not change another street's heights.

| Footprint area | Tagged buildings | Median levels (IQR) | Drawn height |
|---|---|---|---|
| under 100 m² | 90 | 2 (1–3) | 6 m |
| 100–300 m² | 36 | 3 (2–4) | 9 m |
| 300–1,000 m² | 45 | 4 (2–5) | 12 m |
| 1,000 m² and over | 17 | 5 (4–10) | 15 m |

Assumptions, stated plainly:
- **Tagged buildings are not a random sample.** Mappers tag apartment blocks, hospitals and colleges more than sheds and small shops, and 126 of the 188 come from North Main Road's window. The table probably overstates untagged buildings' heights, most in the smallest bin.
  - What it changes: a lower table flattens the scene. Nothing numeric in the product depends on it.
- **The spread within a bin is wide.** A 1,500 m² footprint can be a 2-storey market or a 12-storey tower. The drawn height is the bin median, not a claim about that building.
- **Storey height 3 m.** A conventional value, not cited.
- **OSM tags are used as given, including implausible ones.** A 4-level house tagged 60 m, for example. Only zero or negative values are treated as missing.
- **Microsoft and Google footprints carry no height**, so they always take the area estimate.

## Day 7: geographic context, the default run, and the comparison at capacity

### Default run: trees only

The app now opens on a trees-only search (`reflective_cells_max = 0`). Coating stays one toggle away in stage 01, and the band presentation returns whenever it is on.

- **Reasoning.** Coating is the unpriced intervention and the only source of the temperature band, because the published coefficient spans 5–27 °C per unit albedo. Trees only gives one modelled change with only model error attached, and a real cost range.
- **What it changes.** The headline cooling is smaller, but it is priced and needs no band.

Run on 2026-09-14 through the same job runner the API uses: 20 trees, population 120, 400 generations, seed 42, and the guideline fix below. Change is the conservative end. Cost is the raw payload range; the UI rounds each end outward to 2 significant figures.

| Street | Trees only: searched | Cost | Trees + 150 coated cells: searched | Guideline, trees only | Search over guideline, trees only / coated |
|---|---|---|---|---|---|
| FC Road | −0.70 °C | ₹74,400–1,18,040 | −1.50 to −0.80 °C, not priced | −0.60 °C | 17% / 18% |
| Karve Road | −0.94 °C | ₹74,400–1,18,040 | −1.75 to −1.06 °C, not priced | −0.84 °C | 11% / 13% |
| North Main Road | −0.70 °C | ₹74,400–1,18,040 | −1.51 to −0.81 °C, not priced | −0.64 °C | 9% / 11% |
| Bajirao Road | −0.67 °C | ₹74,400–1,18,040 | −1.48 to −0.78 °C, not priced | −0.61 °C | 11% / 12% |

Hold-out RMSE is 1.16–1.68 °C per 90 m calibration cell on these streets, larger than every difference between arms.

### The design-guideline layout now reaches the matched budget

- **The bug.** When the tree budget was near a street's capacity, the guideline placed fewer trees than the other arms: 26 of 30 on FC Road, 24 of 27 on Bajirao Road, 37 of 38 on Karve Road, 40 of 44 on North Main Road. It split trees evenly between the two sides without checking what each side's strip holds. It also spaced them evenly along strips that buildings and existing canopy interrupt.
- **The fix.**
  - A side that cannot hold its half passes the rest to the other side.
  - Where even spacing cannot fit a side's share, the side takes evenly chosen positions from its densest packing at the IRC:SP:21 minimum. Any subset of a validly spaced packing is still validly spaced.
  - Test: `test_design_guideline_reaches_capacity_when_the_strips_hold_unequal_counts`.
- **What it exposed.** On FC Road at 30 trees (capacity), the guideline now plants all 30.
  - Trees only: the search beats it by 0.2% (−0.879 against −0.877 °C). With coating: 2.1%.
  - The search itself placed 29 trees, or 28 with coating; the GA does not always fill the last pit.
  - The random arm places 26, because random sequential placement packs less densely than the maximum.
- **What that means.** The search's advantage comes from choosing which pits to plant when there are more pits than trees. At capacity every pit is planted and there is nothing left to choose. The demo budget of 20 trees is below capacity on every street (27–44).
- **The comparison caption states counts, not a verdict.** It reads, for example, "All layouts place 20 trees and no coating. The searched layout cools 17% more than the design-guideline layout." When arms differ by a tree, it gives the range ("25–26 trees") instead of calling the comparison unmatched. The margin is the conservative-end ratio, rounded to a whole percent.

### Basemap and locator (display only)

- **Stage 01.** The measured tile sits on the window's OSM highways and merged building footprints: the same cached OSM and Overture data the model classifies land cover from, with no new network call at demo time. The frame extends 150 m past the window so streets visibly carry on.
- **Tile opacity 0.78.** A display choice, so the streets under the tile show.
  - What it changes: a map colour is the ramp colour blended 22% towards the base and linework.
  - The legend bar is drawn at the same opacity over the same base, so the key still matches the map.
- **Locator.** Pune's motorway, trunk, primary and secondary roads and its rivers (Mula, Mutha, Mula-Mutha, Pavana, Ramnadi), with the 2 km window boxed.
  - Pulled once with `prefetch` into `fixtures/cache/overpass/osm_city_major_roads_rivers/`.
  - `CITY_LOCATOR_BOUNDS_WGS84` is an assumption: hand-chosen to cover central Pune and all four windows.
  - **The pull came from the overpass.kumi.systems mirror.** overpass-api.de answered 504 on 2026-09-14. The mirror's database timestamp is 2026-05-31T22:37:44Z, three and a half months older than the window pulls. Major roads and rivers rarely change on that timescale.
- **Stages 02 and 03.** Road centrelines and building outlines are drawn as hairlines over the design grid: in the layout preview, and in the 2D grid, which gains 14 m of context on each side of the street.
- **Simplification is an assumption.** Douglas-Peucker at 1 m in the window and 15 m in the locator (`BASEMAP_WINDOW_SIMPLIFY_M`, `BASEMAP_CITY_SIMPLIFY_M`). Both are below a screen pixel at the scales drawn. The model never sees this geometry; it reads the unsimplified cache.

### Convergence chart

The y axis is scaled to the conservative end only, padded by 10% of its range (at least 0.02 °C each side). When the two ends differ, the more-cooling end is drawn as a shaded band from it, and the legend says the band can run past the axis. Trees-only runs have no band.

### 3D scene

- **Trees read as trees.** Each tree is a trunk and a canopy, merged into one instanced draw call. (First drawn with a 4.5 m canopy; corrected later on Day 7 to the modelled 8 m crown, see Day 7, second half.)
- **Building outlines at 22% opacity**, so the modelled ground carries the frame.

### Contract changes (both files, same commit)

- `GET /api/street/{id}/basemap` returns `StreetBasemap`: roads (`BasemapWay`), building rings, the window's bounds in metres, a `CityLocator`, and attribution.
- `OptimizeJobHandle` gains `design_grid`, so stage 02 can place a layout preview on the street before the result exists.

## Day 7, second half: what the numbers can and cannot claim, the capacity curve, labels and the reveal

### Two separate statements about error

**(i) The absolute modelled change carries the model's error.**
- The trees-only result on FC Road, −0.70 °C, comes from coefficients fitted with a hold-out RMSE of ±1.40 °C per 90 m calibration cell, against 2.03 °C for predicting the mean.
- The coefficients a tree acts through have standard errors of about 1.1 °C: canopy against paved is −5.68 ±1.11 °C, bare against paved +2.29 ±1.17 °C.
- So −0.70 °C is a model output with that error attached. It is not a measured drop, and it is not known to a precision of 0.01 °C, even though it is displayed to two decimals so the ranking between arms stays visible.

**(ii) The ranking between layouts does not carry that error in the same way.**
- Every arm (random, greedy, design guideline, searched) is evaluated by the same calibrated model on the same street and the same design grid.
- An error in the fitted coefficients therefore moves every arm together. For the comparison it is common-mode: it changes how much each layout cools, not which one cools most.
- **The relevant stability evidence is seed-to-seed agreement.** Three GA seeds (42, 7, 2026), 20 trees, trees only:

| Street | Searched layout, three seeds | Spread | Design guideline | Search over guideline |
|---|---|---|---|---|
| FC Road | −0.696, −0.694, −0.695 °C | 0.002 °C | −0.597 °C | 16.4–16.7% |
| North Main Road | −0.698, −0.698, −0.698 °C | 0.000 °C | −0.641 °C | 8.9–9.0% |
| Bajirao Road | −0.674, −0.669, −0.671 °C | 0.005 °C | −0.607 °C | 10.1–11.0% |
| Karve Road | −0.936, −0.936, −0.944 °C | 0.008 °C | −0.845 °C | 10.8–11.7% |

  The searched result agrees across seeds within 0.008 °C on every street, and within 0.002 °C on FC Road. That is roughly ten times smaller than the 0.06–0.10 °C margin over the guideline.

- **Limit of (ii).** Common-mode holds for an error that scales every arm alike. An error in the *ratio* between coefficients, for example bare against canopy, could reorder two layouts that plant over different surfaces. Their gap would then move with that ratio, not with the overall error. The ranking is robust to the model being uniformly too strong or too weak; it is not immune to every coefficient error.

### The capacity curve: the search matters when there is a choice

FC Road, trees only, one GA seed (42) per budget, 400 generations (`python -m app.optimizer.capacity_curve`, figure `figures/capacity-curve.png`). The street's plantable strips hold 30 trees at the IRC:SP:21 minimum spacing.

| Tree budget | Searched | Design guideline | Random | Search over guideline |
|---|---|---|---|---|
| 4 | −0.148 °C | −0.130 °C | −0.128 °C | 14.0% |
| 8 | −0.296 °C | −0.228 °C | −0.259 °C | 29.8% |
| 12 | −0.437 °C | −0.356 °C | −0.384 °C | 22.9% |
| 16 | −0.568 °C | −0.484 °C | −0.505 °C | 17.4% |
| 20 | −0.696 °C | −0.597 °C | −0.626 °C | 16.7% |
| 24 | −0.793 °C | −0.726 °C | −0.741 °C | 9.2% |
| 28 | −0.865 °C | −0.817 °C | −0.769 °C (26 trees) | 5.9% |
| 30 (capacity) | −0.879 °C (29 trees) | −0.877 °C | −0.769 °C (26 trees) | 0.2% |

**Result.** Below capacity the search beats the guideline clearly: 17% at 20 trees on FC Road, and 9–17% across the four streets. At full capacity the guideline is already near-optimal, and the search's edge is 0.2%.

**Mechanism.** The search's advantage is choosing *which* pits to plant: those clear of existing crowns, over the surfaces a new crown cools most. When there are more plantable pits than trees, that choice matters. When every plantable pit is used, there is nothing left to choose, and any competent even spacing gets the same answer.

- Above 8 trees, the margin falls steadily as the budget approaches capacity.
- At 4 trees it is lower (14%): with so few trees, the guideline's evenly spaced positions can land on clear ground by chance. Each budget is one seed, so the small-budget points are the noisiest.
- At capacity the search placed 29 of 30 trees; the GA does not always fill the last pit.

### Why the carriageway reads cooler than the verge

In the modelled surface, the carriageway and footways read cooler than the unshaded ground beside them. That is a fitted result, not a rendering error.
- **The fit.** On FC Road's window, bare ground is fitted hotter than paved surface: +2.29 °C for a full calibration cell, standard error 1.17 °C (`k_bare`; pre-monsoon composite, 10:57 IST overpass).
- **Where it shows.** On the design grid, cells classified bare (unshaded, unbuilt ground outside the paved bands) average 44.8 °C in the before state. Carriageway averages 42.3 °C and footway 42.4 °C.
- **What bare means.** Bare is everything that is neither canopy, building nor mapped paving: in pre-monsoon Pune, mostly dry exposed earth and unmapped hard surfaces.
- **How to read it.** The difference is smaller than twice its standard error. It is a finding about this neighbourhood's pre-monsoon surfaces, not a general claim that asphalt is cool.
- This is also why a tree over bare ground cools more in the model than a tree over paving: k_canopy + k_bare = 7.98 °C per full cell on FC Road.

### Place-name labels (display only)

Labels are chrome, not data: body face, `--paper-dim`, with a thin `--base` halo, never mono and never the thermal ramp. All names come from the cached OSM data; nothing new is fetched.
- **Stage 01 roads.**
  - Up to 10 labels, set along the centreline on a stretch that bends less than 3 px under the label, turned upright.
  - The design street comes first, under its display name (FC Road for the OSM way named Gopal Krushna Gokhale Path). Then trunk, primary and secondary roads by drawn length. Tertiary roads fill only the slots that remain; residential and smaller roads are never labelled.
  - A label that would collide with another, with the locator inset, or with the canvas edge is dropped, not moved.
- **Stage 01 places.**
  - Up to 4 named OSM buildings, largest footprint first, placed after the roads.
  - Names that start with a lower-case letter ("cs department") are mapper notes, not place names, and are skipped.
  - Parks, water and amenities are not in the cached window query, so only buildings are named.
- **Stages 02 and 03.** The design street, and its three nearest cross streets where they meet the lines one cell outside the grid's long edges. That catches T-junctions as well as through roads.
- **Locator.** Up to 4 names: at most 2 rivers, then trunk roads, by length inside the extent.
- **Assumptions.** The caps (10, 4, 3, 4), the 3 px bend limit and the lower-case rule are display choices, not citations. Changing them changes only which names appear.

### Names in the 3D scene (display only)

The 3D scene carries road centrelines and names, so the street can be located without leaving stage 03.
- **Roads on the ground.** OSM centrelines (not footpaths) within 350 m of the design grid centre, as one hairline draw call just above the heat ground.
- **Which names, in priority order.**
  - The design street, under its display name.
  - Its three nearest cross streets, of any class, 3 cells outside the planted strip.
  - Up to 14 other named roads within 350 m, by class then length. Trunk to tertiary come first; residential, unclassified and living streets fill what remains, because close up it is local streets that locate a place. Stage 01's 2 km window still stops at tertiary.
  - Up to 12 named buildings and places, nearest the design street first (see "Building and place names" below).
- **Placement, recomputed whenever the camera moves.**
  - Each name has several candidate positions: road names every 50 m along the road (nearest the design street first), the street name at five points along its centreline, and cross-street names on either side of the street.
  - The first candidate that is on screen and overlaps no name already placed is used. Road names turn to follow their road on screen and are never upside down.
  - A name with no free position is hidden, not squeezed in.
- **Rendering.** HTML text over the canvas, in the body face and `--paper-dim` with a thin `--base` halo, so no font file is fetched. The street's own name is one size larger. It is interaction, not motion: names move only when the viewer orbits.
- **Assumptions.** The 350 m radius, the caps (3, 14, 12) and the 50 m spacing are display choices. Changing them changes only which names appear and where.

### Building and place names (display only)

- **Where names come from.** OpenStreetMap only.
  - Building outlines with a `name` tag, from the cached window pull.
  - Named places: shops, banks, restaurants, schools, hospitals, places of worship, hotels, parks. These come from a separate cached pull per window of elements with a `name` and an `amenity`, `shop`, `office`, `tourism`, `leisure` or `historic` tag (sources.md).
  - Windows hold 215–463 displayable places.
- **Nothing is named that OSM does not name.** The Microsoft and Google footprints carry no names, and no commercial places service is used.
- **Which names are skipped.**
  - Names starting with a lower-case letter ("cs department", "b12") are mapper notes.
  - Block codes ("B12", "A-3") name nothing a reader would recognise.
  - A place with the same name as a named building is the same thing mapped twice, so only the building is kept.
- **Stage 01** still names only the 4 largest named buildings in the 2 km window.
- **3D scene.**
  - Up to 12 names within 350 m, nearest the design street first, one per name.
  - A name that falls inside a drawn building sits 2 m above that building's roof, using the height rules above. Otherwise it sits 3 m above the street.
  - As with road names, a name that would collide is hidden.
- **Assumptions.** OSM coverage decides which places appear; a well-known place that nobody has mapped is simply absent. Roof heights come from the area-based height table, so a name can float above or below the true roof.

### The reveal (motion moment two)

- **The trigger.** Stage 03 opens on today's street with the searched layout placed but not applied. "Apply the searched layout" starts the reveal.
- **What moves.**
  - The 3D ground shader interpolates each cell's modelled temperature from before to after. Both grids are uploaded once as one float texture, and only a uniform changes.
  - The 2D grid interpolates the same way.
  - The delta numeral counts from 0 to its final value.
  - All three read one progress value: 1.5 s, ease-in-out cubic. They land on the same frame.
- **Temperatures, not colours.** Interpolating temperatures means every intermediate frame is a valid position on the same colour scale.
- **After the reveal.** A Before/After toggle, and the coating band toggle when the band exists, switch instantly for inspection. The reveal does not replay.
- **Reduced motion.** `prefers-reduced-motion` lands the ground and the numeral on their final values immediately.

### 3D trees at the modelled crown

- **The canopy is 8 m across**, the same `TREE_CROWN_DIAMETER_M` the model uses to decide which cells a tree shades, so the drawn tree and the modelled shade match exactly.
- **Assumption, display only:** the trunk is 4 m tall and the canopy 2.2 m deep, so that from the opening three-quarter view the cooled ground under the crown stays visible.
- The flat crown ring is removed; it drew the same extent as the canopy.

### Contract changes (both files, same commit)

`StreetBasemap` gains `street_osm_name` and `features` (`BasemapFeature`: name, OSM building value, an anchor inside the footprint, and `footprint_area_m2`). Road names prefer OSM `name:en`.

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
