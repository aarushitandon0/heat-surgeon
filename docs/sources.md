# Sources

Every cited constant in `backend/app/config.py` and where it comes from. Constants that cannot be cited are marked `# ASSUMPTION:` in config and logged in [methodology.md](methodology.md) instead (CLAUDE.md rule 7).

"Verified" means the value was read from that source during the build. Where a primary document was not opened, that is said, and the cross-check that was done instead is named.

## Landsat 8/9 Collection 2 Level 2

| Constant | Value | Source |
|---|---|---|
| `LANDSAT_ST_B10_SCALE_K_PER_DN` | 0.00341802 | [L2], [L4] verified; [L1] |
| `LANDSAT_ST_B10_OFFSET_K` | 149.0 | [L2], [L4] verified; [L1] |
| `LANDSAT_ST_QA_SCALE_K_PER_DN` | 0.01 | [L3], [L4] verified |
| `LANDSAT_ST_QA_NODATA_DN` | −9999 | [L3], [L4] verified |
| `LANDSAT_SR_SCALE_PER_DN` | 0.0000275 | [L4] verified; [L1] |
| `LANDSAT_SR_OFFSET` | −0.2 | [L4] verified; [L1] |
| `LANDSAT_FILL_DN` | 0 | [L4] verified (`nodata: 0` on ST and SR assets) |
| `LANDSAT_QA_PIXEL_REJECT_BITS` | 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow | [L3] verified; [L1] |
| `LANDSAT_CELL_SIZE_M` | 30 | [L4] verified |
| `LANDSAT_TIRS_NATIVE_RESOLUTION_M` | 100 | [L1] |
| `LANDSAT_COLLECTION_CATEGORY` | T1 | [L1] (Tier 1 is the highest-quality, terrain-corrected tier) |

The ST_B10 conversion test (`backend/tests/test_landsat_scaling.py`) uses the worked example from [L2]: DN 44,947 → 302.6 K.

- **[L1]** U.S. Geological Survey. *Landsat 8-9 Collection 2 (C2) Level 2 Science Product Guide*, LSDS-1619. https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/LSDS-1619_Landsat8-9-Collection2-Level2-Science-Product-Guide-v6.pdf — primary document; not opened during the build, values cross-checked against [L2]–[L4].
- **[L2]** U.S. Geological Survey. *How do I use a scale factor with Landsat Level-2 science products?* https://www.usgs.gov/faqs/how-do-i-use-a-scale-factor-landsat-level-2-science-products
- **[L3]** Digital Earth Africa. *Landsat Collection 2 Level-2 Surface Temperature* product specification (QA_PIXEL bit table, ST_QA band). https://docs.digitalearthafrica.org/en/latest/data_specs/Landsat_C2_ST_specs.html
- **[L4]** Microsoft Planetary Computer, `landsat-c2-l2` STAC item metadata (`raster:bands` scale, offset, nodata, unit; `proj:transform`). Read from item `LC09_L2SP_147047_20250529_02_T1` on 2026-09-14.

## Broadband albedo

| Constant | Value | Source |
|---|---|---|
| `LIANG_2001_OLI_COEFFICIENTS` | 0.356 blue, 0.130 red, 0.373 NIR, 0.085 SWIR1, 0.072 SWIR2, −0.0018 | [A1] |

- **[A1]** Liang, S. (2001). Narrowband to broadband conversions of land surface albedo I: Algorithms. *Remote Sensing of Environment*, 76(2), 213–238. https://doi.org/10.1016/S0034-4257(00)00205-4 — citation metadata verified via Crossref. The coefficients were derived for Landsat TM/ETM+ bands 1, 3, 4, 5, 7; applying them to the equivalent OLI bands is an approximation, logged in methodology.md.

## Sentinel-2 L2A

| Constant | Value | Source |
|---|---|---|
| `S2_SCL_REJECT_CLASSES` | 0 no data, 3 cloud shadows, 8 cloud medium probability, 9 cloud high probability, 10 cirrus | [S1] verified |
| `S2_NODATA_DN` | 0 | [S1] (SCL 0 = no data); [S2] |
| `S2_CELL_SIZE_M`, `S2_SCL_CELL_SIZE_M` | 10, 20 | [S3] verified (`gsd`, `proj:transform` on B04, B08, SCL) |
| `S2_HARMONIZED_QUANTIFICATION_VALUE` | 10000 | [S4] (Earth Engine adapter only) |

`BOA_ADD_OFFSET` and `BOA_QUANTIFICATION_VALUE` are deliberately **not** constants. They are read from each product's `MTD_MSIL2A.xml`. On 2026-09-14 the tile 43QCA products at baseline 05.11 carried −1000 and 10000 respectively [S3]. The offset was introduced with processing baseline 04.00 in January 2022 [S1], [S2].

Planetary Computer does not apply the offset to its COGs. This was checked directly, not assumed. Over the same 6 km area around FC Road, a baseline 02.12 scene (2021-03-05) and a baseline 05.11 scene (2025-03-14) differ by roughly +1000 DN at every percentile: B04 median 951 vs 1970, B08 median 1854 vs 2914. The request to harmonise it on Planetary Computer is open and unanswered [S5].

- **[S1]** Sinergise / Sentinel Hub. *Sentinel-2 L2A* data documentation (SCL classes; baseline 04.00). https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/
- **[S2]** ESA. *Sentinel-2 MSI Level-2A Processing Overview*. https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/level-2a-algorithms-products — not opened during the build.
- **[S3]** Microsoft Planetary Computer, `sentinel-2-l2a` STAC item metadata and product metadata XML. Read from item `S2C_MSIL2A_20250428T052711_R105_T43QCA_20250428T103005` on 2026-09-14.
- **[S4]** Google Earth Engine Data Catalog. *Harmonized Sentinel-2 MSI: MultiSpectral Instrument, Level-2A* (`COPERNICUS/S2_SR_HARMONIZED`). https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED — not opened during the build.
- **[S5]** Bunting, P. (2022). *Sentinel-2 BOA_ADD_OFFSET harmonisation*. microsoft/PlanetaryComputer issue #134. https://github.com/microsoft/PlanetaryComputer/issues/134

## Land cover

| Constant | Value | Source |
|---|---|---|
| `NDVI_BARE_SOIL_MAX` | 0.2 | [V1] |
| `NDVI_FULL_VEGETATION_MIN` | 0.5 | [V1] |

- **[V1]** Sobrino, J. A., Jiménez-Muñoz, J. C., & Paolini, L. (2004). Land surface temperature retrieval from LANDSAT TM 5. *Remote Sensing of Environment*, 90(4), 434–440. https://doi.org/10.1016/j.rse.2004.02.003 — citation metadata verified via Crossref. The 0.2 and 0.5 thresholds were confirmed from summaries of the paper and its reuse in later LST studies; the paper itself was not opened during the build. Sobrino et al. set these thresholds to separate soil from vegetation for emissivity estimation. Reusing them as land-cover class boundaries is our choice, logged in methodology.md.

## Material albedo

`ALBEDO_BY_MATERIAL`, as (low, high) broadband albedo. Solar reflectance and albedo are treated as the same quantity.

| Key | Value | Source |
|---|---|---|
| `asphalt_new` | 0.05 | [M1] "new SR 5%" |
| `asphalt_aged` | 0.10–0.20 | [M1] "aged SR 10-20%" |
| `concrete_new` | 0.30–0.50 | [M1] "new SR 30-50%" |
| `concrete_aged` | 0.20–0.35 | [M1] "aged SR 20-35%" |
| `high_albedo_coating` | 0.50 | [M1] "coatings for asphalt concrete pavements that reflect about 50% of sunlight" |
| `permeable_concrete_dry` | 0.20–0.35 | [M2]; [M3] reports 0.25–0.35 |
| `permeable_concrete_wet` | 0.15 | [M2] |

Both pervious concrete studies find it 0.05–0.20 *less* reflective than conventional concrete. Permeable pavement is not a cooling intervention through albedo; any cooling has to come from evaporation, which this model does not represent. See methodology.md.

- **[M1]** Lawrence Berkeley National Laboratory, Heat Island Group. *Cool Pavements*. https://heatisland.lbl.gov/coolscience/cool-pavements — read 2026-09-14.
- **[M2]** Lu, Y., Qin, Y., Huang, C., & Pang, X. (2023). Albedo of pervious concrete and its implications for mitigating urban heat island. *Sustainability*, 15(10), 8222. https://doi.org/10.3390/su15108222 — abstract verified via Crossref.
- **[M3]** Zhang, R., Jiang, G., & Liang, J. (2015). The albedo of pervious cement concrete linearly decreases with porosity. *Advances in Materials Science and Engineering*, 2015, 746592. https://doi.org/10.1155/2015/746592 — abstract verified via Crossref.

## Albedo effect on surface temperature (published, not fitted)

| Constant | Value | Source |
|---|---|---|
| `K_ALBEDO_LOW_C_PER_UNIT_ALBEDO` | 5.0 °C per unit albedo | [K1]: 0.9 °C reduction for a 0.18 albedo increase at 09:00 (0.9 / 0.18) |
| `K_ALBEDO_HIGH_C_PER_UNIT_ALBEDO` | 27.0 °C per unit albedo | [K1]: "2.7 °C per 0.1 increase in pavement albedo" (5 °C peak at 15:00); [K2] corroborates, summarising "close to 2.5 K" per 0.1 |

- **[K1]** Ko, J., Schlaerth, H., Bruce, A., Sanders, K., & Ban-Weiss, G. (2022). Measuring the impacts of a real-world neighborhood-scale cool pavement deployment on albedo and temperatures in Los Angeles. *Environmental Research Letters*, 17(4), 044027. https://doi.org/10.1088/1748-9326/ac58a8 — full text read. Field measurement: mean pavement albedo rose from 0.08 to 0.26. Surface temperature from mobile and stationary infrared radiometers, with a difference-in-differences design against a control site. The reduction was smallest at 09:00 (0.9 °C) and largest at 15:00 (5 °C). Our 10:57 overpass lies between the two ends.
- **[K2]** Santamouris, M. (2013). Using cool pavements as a mitigation strategy to fight urban heat island — a review of the actual developments. *Renewable and Sustainable Energy Reviews*, 26, 224–240. Full text read (via the Cool Roof Toolkit copy). The per-0.1 summary comes from a Japanese field test of high-albedo asphalt coatings reported in the review.

## Street design

| Constant | Value | Source |
|---|---|---|
| `TREE_MIN_SPACING_M` | 8.0 m | [D1] §11.14.1: shade trees "8-12 m" apart |
| `MIN_SIDEWALK_WIDTH_FOR_TREES_M` | 4.3 m | [D2] Table 2: 2.5 m minimum obstacle-free walkway, commercial/mixed use; plus 6.10: multi-functional (planting) zone "a minimum of 1.8 m wide" |
| `SIDEWALK_WIDTH_M`, `FOOTWAY_WIDTH_M` | 2.5 m, 1.8 m | [D2] minimums, used only where OSM has no width (logged as assumptions) |

- **[D1]** Indian Roads Congress. *IRC:SP:21-2009, Guidelines on Landscaping and Tree Plantation*. https://archive.org/details/govlawircy2009sp21 — read via the Internet Archive full text.
- **[D2]** Indian Roads Congress. *IRC:103-2012, Guidelines for Pedestrian Facilities*. https://law.resource.org/pub/in/bis/irc/irc.gov.in.103.2012.pdf — full text read.

| `USDG_TEMPLATES` | 9A, 12A, 15A, 18A, 21A, 24A, 30A band widths | [D3] chapter 8 reference templates, section drawings read from the PDF (pp. 74, 76, 81, 85, 90, 94, 99). 21A and the 15A/24A bus-stop zones are adjusted as logged in methodology.md |
| Template choice rule | widest template no wider than the right of way; spare width to non-motorised space | [D3] chapter 8 introduction ("For eg: For streets with ROW 20 meters, street template for ROW 18 meters should be used and remaining 2 meters should be designed as a part of NMT space") |
| Tree placement | trees in the verge / MUZ / parking belt between footpath and carriageway, never in the clear walkway | [D3] §5.2 Plantation |

- **[D3]** Pune Municipal Corporation. *Urban Street Design Guidelines, Pune*, Version I:2016. Published with ITDP India. https://www.itdp.in/wp-content/uploads/2016/07/Urban-street-design-guidelines.pdf — full text and template drawings read 2026-09-14.

## Costs

| Constant | Value | Source |
|---|---|---|
| `TREE_PLANTING_FIRST_YEAR_INR` | ₹1,682 per tree | [C1] item 39.30: "Planting of trees by the road side (Avenue trees) in 0.60 m dia holes, 1 m deep dug in the ground, mixing the soil with decayed farm yard/sludge manure, planting the saplings, backfilling the trench, watering, fixing the tree guard and maintaining the plants for one year" |
| `TREE_GUARD_INR_LOW` | ₹2,038 | [C1] item 39.31: half brick circular tree guard, 1.25 m internal diameter, 1.2 m high |
| `TREE_GUARD_INR_HIGH` | ₹4,220 | [C1] item 39.39: M.S. tree guard 50 cm square, 1.4 m above ground |
| `COST_INR_BY_INTERVENTION["tree"]` | ₹3,720 to ₹5,902 | Sum of the above. Scope: planting, guard and **first-year** care only |
| Reflective coating, pervious concrete, shade structure | no value | Not sourced; see below |

- **[C1]** Government of Rajasthan, Rajasthan Urban Infrastructure Development Project. *Integrated Schedule of Rates 2023* (w.e.f. 01/10/2023). https://lsg.urban.rajasthan.gov.in/content/dam/raj/udh/organizations/ruidp/Downloads/SOR-2023/SOR%20RUIDP%20-%202023.pdf — full text read 2026-09-14. Item 39.33 (bitumen-drum guard, ₹1,026) is not used as the low guard because the drum is supplied by the department and not included in the rate.

Searched within the 90-minute cost timebox and **not** usable:
- CPWD *Delhi Schedule of Rates (Horticulture & Landscaping) 2020*: the copy at cpwd.gov.in refused the download; the copy hosted by Indian Railways (ICF) opened, but its chapter 2 rate pages are scanned images with no text layer. Chapter 7 gives sapling prices only (₹45 to ₹750 each), not pits or care.
- Pune Municipal Corporation *Garden DSR 2016-17* (pmc.gov.in): the server refused connections from the build machine.
- Maharashtra PWD district schedules: mahapwd.com has an invalid TLS certificate; copies found were on Scribd only. The maharashtra.gov.in "Horticulture 2023-24" PDF is an agriculture department programme budget, not a rate schedule.
- MoRTH *Standard Data Book*: available only on Scribd and mirrors; it is an analysis-of-rates method, not a rate list.
- Reflective pavement coating: no Indian government schedule item found. RUIDP item 10.8 (hot-applied thermoplastic road marking) is a different product. Cool **roof** coating prices (Telangana Cool Roof Policy 2023-28, Ahmedabad Heat Action Plan) are not traffic-rated pavement coatings and are not used.

## Building footprints

| Constant | Value | Source |
|---|---|---|
| `OVERTURE_RELEASE` | 2026-08-19.0 | [B1] |
| `GOOGLE_OPEN_BUILDINGS_MIN_CONFIDENCE` | 0.65 | Observed minimum in the release over Pune; logged as an assumption |

- **[B1]** Overture Maps Foundation. *Buildings theme*, release 2026-08-19.0, GeoParquet at `s3://overturemaps-us-west-2/release/2026-08-19.0/theme=buildings/type=building/`, read anonymously with DuckDB. Conflates OpenStreetMap (ODbL), Microsoft Global ML Building Footprints (ODbL) and Google Open Buildings (CC BY 4.0 / ODbL). Each footprint's `sources[1].dataset` is kept verbatim as `footprint_source`.

## OpenStreetMap

Building footprints and highway geometry: © OpenStreetMap contributors, available under the Open Database License (ODbL 1.0), https://www.openstreetmap.org/copyright. Pulled via the Overpass API (https://overpass-api.de); database timestamp 2026-09-13T19:08:06Z, stored with the cached result.

City locator (display only): Pune's motorway, trunk, primary and secondary roads and waterway=river ways, © OpenStreetMap contributors, ODbL 1.0. Pulled 2026-09-14 from the overpass.kumi.systems mirror of the Overpass API, after overpass-api.de answered 504; mirror database timestamp 2026-05-31T22:37:44Z, stored with the cached result.

## Physical constants

| Constant | Value | Source |
|---|---|---|
| `KELVIN_AT_ZERO_CELSIUS` | 273.15 | Definition of the degree Celsius in the SI: BIPM, *The International System of Units (SI)*, 9th edition, 2019. |
| `LOCAL_UTC_OFFSET_MINUTES` | 330 | Indian Standard Time is UTC+05:30 with no daylight saving. |
