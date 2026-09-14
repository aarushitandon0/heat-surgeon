// Stage 01: pull the real surface temperature composite, fit the model, show what drives the heat.

import { useCallback, useMemo, useState } from 'react'
import {
  ERROR_DECIMALS,
  SOURCE_ADAPTER_LABELS,
  SURFACE_LABELS,
  TEMP_DECIMALS,
  formatBand,
  formatCount,
  formatNumber,
  formatOverpass,
  formatSeasons,
  formatSigned,
  formatLatitude,
  formatLongitude,
  streetShortName,
} from '../lib/format.ts'
import { expandBounds } from '../lib/basemap.ts'
import { ROAD_LABEL_FRACTIONS, placePointLabels, placeRoadLabels, roadCandidates, type XY } from '../lib/labels.ts'
import { affineFromTransform, cellToUtm, gridBounds, utmToScreen } from '../lib/geometry.ts'
import { DECODE_ROW_STAGGER_MS } from '../lib/motion.ts'
import { contrastAgainst } from '../lib/model.ts'
import { COATED_CELLS_WHEN_ON, useStore } from '../store/store.ts'
import type { CalibrationResult, Provenance, ThermalGrid } from '../types/contracts.ts'
import { LABEL_FONT_PX, LABEL_PAD_PX, drawLabels, strokeBasemap, type ContextStyle } from '../ui/basemapDraw.ts'
import { measurer } from '../ui/textMeasure.ts'
import { CityLocatorMap } from '../ui/CityLocatorMap.tsx'
import { Decode } from '../ui/Decode.tsx'
import { HeatCanvas, type OverlayContext } from '../ui/HeatCanvas.tsx'
import { NumberField } from '../ui/NumberField.tsx'
import { Readout } from '../ui/Readout.tsx'
import { ThermalScale } from '../ui/ThermalScale.tsx'
import { readBodyFont, readSurfaceColor } from '../ui/tokens.ts'

/** Road labels: trunk, primary and secondary first; tertiary roads only fill slots that remain. */
const ROAD_LABEL_RANK_MAX = 3
const ROAD_LABELS_MAX = 10
/** A label is set only on a stretch that bends less than this under it. */
const ROAD_LABEL_MAX_BEND_PX = 3
/** Named buildings, largest first, after the roads. Recognition, not a gazetteer. */
const PLACE_LABELS_MAX = 4

/** Streets shown this far past the measured window on every side. */
const WINDOW_CONTEXT_MARGIN_M = 150
/**
 * The measured tile is drawn see-through so the streets under it show. Display choice (docs/methodology.md,
 * Day 7); the legend bar is drawn at the same opacity, so a colour on the map still matches the key.
 */
const MEASURED_OPACITY_OVER_STREETS = 0.78
const WINDOW_CONTEXT_STYLE: ContextStyle = {
  buildingAlpha: 0.28,
  minorAlpha: 0.55,
  majorAlpha: 0.85,
  buildingWidth_px: 0.5,
  minorWidth_px: 0.75,
  majorWidth_px: 1.5,
}

interface StackRow {
  /** Stable across pending and ready, so a row keeps its Decode instance when the data lands. */
  key: string
  label: string
  text: string | null
  mono: boolean
  placeholderLength: number
}

/** The provenance stack (SPEC.md §9.3). Row text is null while the real fetch is pending. */
function provenanceRows(p: Provenance | null): StackRow[] {
  if (!p) {
    return [
      { key: 'scenes', label: 'Scenes', text: null, mono: true, placeholderLength: 2 },
      { key: 'seasons', label: 'Seasons', text: null, mono: false, placeholderLength: 18 },
      { key: 'collection-0', label: 'Collections', text: null, mono: false, placeholderLength: 13 },
      { key: 'platform-0', label: 'Platforms', text: null, mono: false, placeholderLength: 9 },
      { key: 'composite', label: 'Composite', text: null, mono: false, placeholderLength: 16 },
      { key: 'overpass', label: 'Overpass', text: null, mono: true, placeholderLength: 5 },
    ]
  }
  return [
    { key: 'scenes', label: 'Scenes', text: formatCount(p.scene_count), mono: true, placeholderLength: 2 },
    { key: 'seasons', label: 'Seasons', text: formatSeasons(p.months, p.date_range), mono: false, placeholderLength: 18 },
    // Collection IDs verbatim, as the adapter reports them (CLAUDE.md rule 13).
    ...p.collections.map((id, i) => ({ key: `collection-${i}`, label: i === 0 ? 'Collections' : '', text: id, mono: false, placeholderLength: 13 })),
    ...p.platforms.map((id, i) => ({ key: `platform-${i}`, label: i === 0 ? 'Platforms' : '', text: id, mono: false, placeholderLength: 9 })),
    { key: 'composite', label: 'Composite', text: p.compositing, mono: false, placeholderLength: 16 },
    { key: 'overpass', label: 'Overpass', text: formatOverpass(p.overpass_local_time), mono: true, placeholderLength: 5 },
  ]
}

export function DiagnosePanel() {
  const street = useStore((s) => s.street)!
  const thermalWindow = useStore((s) => s.thermalWindow)
  const thermalStreet = useStore((s) => s.thermalStreet)
  const calibration = useStore((s) => s.calibration)
  const request = useStore((s) => s.request)
  const job = useStore((s) => s.job)
  const setRequest = useStore((s) => s.setRequest)
  const startOptimize = useStore((s) => s.startOptimize)

  // Decode only if this panel watched the fetch happen; coming back to stage 01 later shows final text.
  const [sawAcquiring] = useState(() => thermalWindow.status === 'loading')
  const provenance = thermalWindow.status === 'ready' ? thermalWindow.data.provenance : null
  const [lon, lat] = [(street.bbox_street[0] + street.bbox_street[2]) / 2, (street.bbox_street[1] + street.bbox_street[3]) / 2]
  const searchRunning = job.status === 'starting' || job.status === 'searching' || job.status === 'loading_result'
  const coatingOn = request.reflective_cells_max > 0
  const [coatedWhenOn, setCoatedWhenOn] = useState(COATED_CELLS_WHEN_ON)

  return (
    <>
      <section className="panel-section">
        <h2 className="panel-title">{street.name}</h2>
        <p className="street-coords mono">
          {formatLatitude(lat)}
          <br />
          {formatLongitude(lon)}
        </p>
      </section>

      <section className="panel-section" aria-labelledby="composite-heading">
        <h3 id="composite-heading">Surface temperature composite</h3>
        {thermalWindow.status === 'error' ? (
          <p className="status status-error" role="alert">
            {thermalWindow.message}
          </p>
        ) : (
          <>
            <p className="status" aria-live="polite">
              {provenance
                ? `Acquired from ${SOURCE_ADAPTER_LABELS[provenance.source_adapter]}.`
                : 'Acquiring surface temperature for the 2 km window.'}
            </p>
            <dl className="readouts">
              {provenanceRows(provenance).map((row, i) => (
                <Readout
                  key={row.key}
                  label={row.label}
                  kind={row.mono ? 'numeric' : 'text'}
                  value={
                    <Decode
                      text={row.text}
                      mono={row.mono}
                      placeholderLength={row.placeholderLength}
                      delayMs={i * DECODE_ROW_STAGGER_MS}
                      decodeOnMount={sawAcquiring}
                    />
                  }
                />
              ))}
            </dl>
            {provenance && <p className="panel-note">{provenance.cloud_masking}</p>}
          </>
        )}
      </section>

      <section className="panel-section">
        {thermalStreet.status === 'ready' && (
          <dl className="readouts">
            <Readout
              size="lg"
              label="Street surface temperature, mean"
              value={formatNumber(thermalStreet.data.stats.mean_c, TEMP_DECIMALS)}
              unit="°C"
              note={`measured, ${formatCount(thermalStreet.data.provenance.delivered_resolution_m)} m`}
            />
          </dl>
        )}
        {thermalStreet.status === 'ready' && (
          <p className="panel-note">
            Mean of {formatCount(thermalStreet.data.stats.valid_pixels)} pixels over the street, delivered at{' '}
            {formatCount(thermalStreet.data.provenance.delivered_resolution_m)} m from a{' '}
            {formatCount(thermalStreet.data.provenance.native_resolution_m)} m thermal band. Mid-morning land
            surface, not air temperature.
          </p>
        )}
        {thermalStreet.status === 'loading' && <p className="status">Reading the street&apos;s measured pixels.</p>}
        {thermalStreet.status === 'error' && (
          <p className="status status-error" role="alert">
            {thermalStreet.message}
          </p>
        )}
      </section>

      <section className="panel-section" aria-labelledby="model-heading">
        <h3 id="model-heading">Model</h3>
        {calibration.status === 'loading' && (
          <p className="status" aria-live="polite">
            Fitting the model on calibration cells across the window.
          </p>
        )}
        {calibration.status === 'error' && (
          <p className="status status-error" role="alert">
            {calibration.message}
          </p>
        )}
        {calibration.status === 'ready' && <CalibrationReadouts calibration={calibration.data} />}
      </section>

      <section className="panel-section" aria-labelledby="search-heading">
        <h3 id="search-heading">Search settings</h3>
        <p className="panel-note">
          The search, random layouts, greedy placement and the design-guideline layout all get the same budget.
        </p>
        <div className="segmented" role="group" aria-label="Interventions">
          <button
            type="button"
            aria-pressed={!coatingOn}
            onClick={() => {
              if (coatingOn) setCoatedWhenOn(request.reflective_cells_max)
              setRequest({ reflective_cells_max: 0 })
            }}
          >
            Trees only
          </button>
          <button type="button" aria-pressed={coatingOn} onClick={() => setRequest({ reflective_cells_max: coatedWhenOn })}>
            Trees and coating
          </button>
        </div>
        <div className="fields">
          <NumberField label="Trees, at most" value={request.trees_max} min={0} onChange={(v) => setRequest({ trees_max: v })} />
          {coatingOn && (
            <NumberField
              label="Coated cells, at most"
              value={request.reflective_cells_max}
              min={1}
              onChange={(v) => setRequest({ reflective_cells_max: v })}
            />
          )}
          <NumberField label="Generations" value={request.generations} min={1} onChange={(v) => setRequest({ generations: v })} />
          <NumberField label="Population" value={request.population} min={2} onChange={(v) => setRequest({ population: v })} />
        </div>
        {coatingOn ? (
          <p className="panel-note">
            Reflective coating has no sourced rate, so a layout that uses it is shown without a cost. Its modelled
            change is a band from the published coating coefficient range.
          </p>
        ) : (
          <p className="panel-note">
            Trees only: every layout is priced, and the modelled change carries only the model error.
          </p>
        )}
        <button
          className="button button-primary"
          type="button"
          disabled={calibration.status !== 'ready'}
          onClick={() => void startOptimize()}
        >
          Search layouts
        </button>
        {calibration.status !== 'ready' && <p className="panel-note">Available once the model is calibrated.</p>}
        {searchRunning && <p className="panel-note">A search is running. Starting another replaces it.</p>}
      </section>
    </>
  )
}

function CalibrationReadouts({ calibration }: { calibration: CalibrationResult }) {
  const landCover = calibration.provenance.find((p) => p.product === 'land_cover')
  const cell_m = formatCount(calibration.calibration_resolution_m)
  return (
    <>
      <dl className="readouts">
        <Readout
          label="Model error"
          value={`±${formatNumber(calibration.rmse_holdout_c, ERROR_DECIMALS)}`}
          unit="°C"
          note={`Hold-out RMSE on ${formatCount(calibration.n_cells_holdout)} cells of ${cell_m} m`}
        />
        <Readout
          label="Mean-only baseline"
          value={formatNumber(calibration.rmse_mean_baseline_c, ERROR_DECIMALS)}
          unit="°C"
          note="Error from predicting every held-out cell as the mean"
        />
        <Readout label="R² on hold-out" value={formatNumber(calibration.r2_holdout, ERROR_DECIMALS)} />
        <Readout
          label="Cells fitted"
          value={formatCount(calibration.n_cells_fit)}
          note={`${cell_m} m calibration cells across the window`}
        />
      </dl>

      <h3>What drives surface temperature here</h3>
      <p className="panel-note">
        Modelled change for a fully covered {cell_m} m cell, relative to paved surface. ± is one standard error, not a
        confidence interval.
      </p>
      <dl className="readouts">
        {(['canopy', 'built', 'bare'] as const).map((surface) => {
          const contrast = contrastAgainst(calibration.contrasts, surface, 'paved')
          return (
            contrast && (
              <Readout
                key={surface}
                label={`${SURFACE_LABELS[surface]} instead of paved`}
                value={`${formatSigned(contrast.difference_c, ERROR_DECIMALS)} ±${formatNumber(contrast.standard_error_c, ERROR_DECIMALS)}`}
                unit="°C"
              />
            )
          )
        })}
        <Readout
          label="Reflective coating"
          value={formatBand(calibration.k_albedo_low_c_per_unit_albedo, calibration.k_albedo_high_c_per_unit_albedo, 1)}
          unit="°C"
          note="Per unit of albedo gained. Published measurement range, not fitted."
        />
      </dl>

      {landCover && (
        <>
          <h3>Land cover</h3>
          <dl className="readouts">
            <Readout label="Scenes" value={formatCount(landCover.scene_count)} />
            <Readout label="Collections" kind="text" value={landCover.collections.join(', ')} />
            <Readout label="Composite" kind="text" value={landCover.compositing} />
            <Readout label="Resolution" value={formatCount(landCover.delivered_resolution_m)} unit="m" />
            <Readout label="Building footprints" kind="text" value={calibration.building_footprint_sources.join(', ')} />
          </dl>
        </>
      )}
    </>
  )
}

export function DiagnoseViewport() {
  const thermalWindow = useStore((s) => s.thermalWindow)
  const thermalStreet = useStore((s) => s.thermalStreet)

  if (thermalWindow.status === 'error') {
    return (
      <p className="viewport-message status-error" role="alert">
        {thermalWindow.message}
      </p>
    )
  }
  if (thermalWindow.status !== 'ready') {
    return <p className="viewport-message">Acquiring surface temperature for the 2 km window.</p>
  }
  return <MeasuredWindow grid={thermalWindow.data} street={thermalStreet.status === 'ready' ? thermalStreet.data : null} />
}

function MeasuredWindow({ grid, street }: { grid: ThermalGrid; street: ThermalGrid | null }) {
  const basemapLoad = useStore((s) => s.basemap)
  const basemap = basemapLoad.status === 'ready' ? basemapLoad.data : null
  const affine = useMemo(() => affineFromTransform(grid.transform), [grid.transform])
  const domain = useMemo(() => ({ min_c: grid.stats.min_c, max_c: grid.stats.max_c }), [grid.stats])
  // A margin around the window, so the streets visibly carry on past the measured tile.
  const frame = useMemo(() => expandBounds(gridBounds(affine, grid.shape), WINDOW_CONTEXT_MARGIN_M), [affine, grid.shape])
  const p = grid.provenance
  const [rows, cols] = grid.shape
  const gridOpacity = basemap ? MEASURED_OPACITY_OVER_STREETS : 1

  const underlay = useCallback(
    ({ ctx, view }: OverlayContext) => {
      if (!basemap) return
      strokeBasemap(ctx, basemap.roads, basemap.buildings, (e_m, n_m) => utmToScreen(view, e_m, n_m), WINDOW_CONTEXT_STYLE)
    },
    [basemap],
  )

  const summary = useStore((s) => s.street)
  const streetLabel = summary ? streetShortName(summary.name) : null

  const overlay = useCallback(
    ({ ctx, view, width_px, height_px, reserved }: OverlayContext) => {
      if (street) strokeStreetExtent(ctx, view, street)
      if (!basemap || !streetLabel) return
      const project = (e_m: number, n_m: number): XY => utmToScreen(view, e_m, n_m)
      const bounds = { x: 0, y: 0, w: width_px, h: height_px }
      const measure = measurer(readBodyFont(LABEL_FONT_PX))
      const roads = placeRoadLabels(
        roadCandidates(basemap.roads, project, ROAD_LABEL_RANK_MAX, { osmName: basemap.street_osm_name, label: streetLabel }),
        measure,
        LABEL_FONT_PX,
        bounds,
        reserved,
        { max: ROAD_LABELS_MAX, fractions: ROAD_LABEL_FRACTIONS, maxBend: ROAD_LABEL_MAX_BEND_PX, pad: LABEL_PAD_PX },
      )
      const places = placePointLabels(
        basemap.features.map((feature) => {
          const [x, y] = project(...feature.anchor)
          return { text: feature.name, anchors: [{ x, y, align: 'center' as const }] }
        }),
        measure,
        LABEL_FONT_PX,
        bounds,
        [...reserved, ...roads.map((label) => label.box)],
        PLACE_LABELS_MAX,
        LABEL_PAD_PX,
      )
      drawLabels(ctx, [...roads, ...places])
    },
    [street, basemap, streetLabel],
  )

  return (
    <>
      <div className="viewport-head">
        <h2 className="viewport-title">Surface temperature, measured, {formatCount(p.delivered_resolution_m)} m</h2>
        <p className="viewport-sub">
          Per-pixel median of {formatCount(p.scene_count)} scenes at the {formatOverpass(p.overpass_local_time)} overpass,{' '}
          {formatSeasons(p.months, p.date_range)}. A composite, not a single acquisition. {formatCount(cols * grid.cell_size_m)} m
          window, {grid.crs}, north up.
        </p>
      </div>
      <HeatCanvas
        values={grid.lst_c}
        affine={affine}
        shape={grid.shape}
        domain={domain}
        frame={frame}
        underlay={underlay}
        gridOpacity={gridOpacity}
        overlay={overlay}
        inset={basemap && <CityLocatorMap city={basemap.city} window_bounds_m={basemap.window_bounds_m} />}
        ariaLabel={`Measured surface temperature, ${rows} by ${cols} cells at ${formatCount(grid.cell_size_m)} m, over OpenStreetMap streets`}
      />
      <div className="viewport-foot">
        <div className="viewport-foot-rows">
          <ThermalScale
            domain={domain}
            opacity={gridOpacity}
            caption={`Surface temperature, °C, measured, ${formatCount(p.delivered_resolution_m)} m`}
          />
          <div className="legend">
            {street && (
              <span className="legend-item">
                <span className="legend-outline" aria-hidden="true" />
                Street extent
              </span>
            )}
            {basemap && (
              <span className="legend-item">
                <span className="legend-context" aria-hidden="true" />
                Roads and building footprints, under the measured tile
              </span>
            )}
          </div>
          {basemapLoad.status === 'error' && (
            <p className="attribution status-error" role="alert">
              Street geometry did not load, so the tile is drawn without it. {basemapLoad.message}
            </p>
          )}
          {basemap && <p className="attribution">{basemap.attribution}</p>}
        </div>
      </div>
    </>
  )
}

/** The street's measured extent: the street-scope thermal grid's outer edge. */
function strokeStreetExtent(ctx: CanvasRenderingContext2D, view: OverlayContext['view'], street: ThermalGrid) {
  const streetAffine = affineFromTransform(street.transform)
  const [streetRows, streetCols] = street.shape
  const corners = [
    [0, 0],
    [streetCols, 0],
    [streetCols, streetRows],
    [0, streetRows],
  ].map(([col, row]) => utmToScreen(view, ...cellToUtm(streetAffine, col, row)))
  ctx.save()
  ctx.strokeStyle = readSurfaceColor('--paper')
  ctx.lineWidth = 1.5
  ctx.beginPath()
  corners.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)))
  ctx.closePath()
  ctx.stroke()
  ctx.restore()
}
