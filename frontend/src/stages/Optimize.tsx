// Stage 02: the search, live. Every number here comes from the WebSocket stream.

import { useId, useMemo } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { designGridContext, type CellPoint } from '../lib/basemap.ts'
import { designGridLabels } from '../lib/labels.ts'
import { LABEL_FONT_PX, LABEL_HALO_PX, LABEL_PAD_PX } from '../ui/basemapDraw.ts'
import { useElementSize } from '../ui/hooks.ts'
import { measurer } from '../ui/textMeasure.ts'
import { readBodyFont } from '../ui/tokens.ts'
import {
  DELTA_DECIMALS,
  ERROR_DECIMALS,
  INTERVENTION_LABELS,
  formatCount,
  formatInrRange,
  formatNumber,
  formatSigned,
  streetShortName,
} from '../lib/format.ts'
import { paddedDomain } from '../lib/model.ts'
import { useStore, type JobState } from '../store/store.ts'
import type { DesignGrid, Intervention, OptimizeProgress } from '../types/contracts.ts'
import { Readout } from '../ui/Readout.tsx'

/** The y axis spans the conservative curve plus this fraction of its range on each side. */
const CHART_PAD_FRACTION = 0.1
/** ...and at least this much, so a flat curve still gets ticks 0.01 °C apart. */
const CHART_MIN_PAD_C = 0.02
/** Streets and footprints this far outside the design grid are drawn (and clipped at its edge). */
const PREVIEW_CONTEXT_MARGIN_M = 2
/** The layout preview grows with the viewport width up to this height. */
const PREVIEW_MAX_HEIGHT_REM = 12
/** The street and at most this many nearest cross streets are named on the preview. */
const CROSS_STREET_LABELS_MAX = 3
const PREVIEW_LABEL_GAP_PX = 4

function bandsDiffer(p: OptimizeProgress): boolean {
  return formatSigned(p.best_temp_delta_c_low, DELTA_DECIMALS) !== formatSigned(p.best_temp_delta_c_high, DELTA_DECIMALS)
}

function StatusLine({ job }: { job: JobState }) {
  const latest = job.progress.at(-1)
  switch (job.status) {
    case 'starting':
      return <>Starting the search.</>
    case 'searching':
      if (!latest) return <>Search started. Waiting for the first generation.</>
      if (latest.generation >= latest.generations_total) {
        return (
          <>
            Generation <span className="mono">{formatCount(latest.generation)}</span> of{' '}
            <span className="mono">{formatCount(latest.generations_total)}</span>. Running the baselines at the same
            budget.
          </>
        )
      }
      return (
        <>
          Searching layouts. Generation <span className="mono">{formatCount(latest.generation)}</span> of{' '}
          <span className="mono">{formatCount(latest.generations_total)}</span>.
        </>
      )
    case 'loading_result':
      return <>Search finished. Loading the result.</>
    case 'done':
      return <>Search finished.</>
    default:
      return null
  }
}

export function OptimizePanel() {
  const street = useStore((s) => s.street)!
  const job = useStore((s) => s.job)
  const request = useStore((s) => s.request)
  const calibration = useStore((s) => s.calibration)
  const goTo = useStore((s) => s.goTo)
  const latest = job.progress.at(-1)

  return (
    <>
      <section className="panel-section">
        <h2 className="panel-title">{street.name}</h2>
        {job.status === 'error' ? (
          <>
            <p className="status status-error" role="alert">
              {job.message}
            </p>
            <button className="button" type="button" onClick={() => goTo('diagnose')}>
              Back to search settings
            </button>
          </>
        ) : (
          <p className="status" aria-live="polite">
            <StatusLine job={job} />
          </p>
        )}
      </section>

      {job.handle && (
        <section className="panel-section" aria-labelledby="space-heading">
          <h3 id="space-heading">Search space</h3>
          <dl className="readouts">
            <Readout
              label="Design cells"
              value={formatCount(job.handle.cells)}
              note={`${formatCount(job.handle.grid_shape[0])} along the street by ${formatCount(job.handle.grid_shape[1])} across, ${formatCount(job.handle.states_per_cell)} states each`}
            />
            <Readout label="Trees, at most" value={formatCount(request.trees_max)} />
            <Readout label="Coated cells, at most" value={formatCount(request.reflective_cells_max)} />
            <Readout label="Population" value={formatCount(request.population)} />
          </dl>
        </section>
      )}

      {latest && (
        <section className="panel-section" aria-labelledby="best-heading">
          <h3 id="best-heading">Best layout so far</h3>
          <dl className="readouts">
            {bandsDiffer(latest) ? (
              <>
                <Readout
                  label="Change, conservative end"
                  value={formatSigned(latest.best_temp_delta_c_high, DELTA_DECIMALS)}
                  unit="°C"
                  note="Mean over the design area, modelled. The search ranks on this end."
                />
                <Readout label="Change, more-cooling end" value={formatSigned(latest.best_temp_delta_c_low, DELTA_DECIMALS)} unit="°C" />
              </>
            ) : (
              <Readout
                label="Change"
                value={formatSigned(latest.best_temp_delta_c_high, DELTA_DECIMALS)}
                unit="°C"
                note="Mean over the design area, modelled."
              />
            )}
            <ProgressCost progress={latest} />
          </dl>
        </section>
      )}

      {calibration.status === 'ready' && (
        <section className="panel-section">
          <dl className="readouts">
            <Readout
              label="Model error"
              value={`±${formatNumber(calibration.data.rmse_holdout_c, ERROR_DECIMALS)}`}
              unit="°C"
              note="Hold-out RMSE per calibration cell"
            />
            <Readout label="Mean-only baseline" value={formatNumber(calibration.data.rmse_mean_baseline_c, ERROR_DECIMALS)} unit="°C" />
          </dl>
        </section>
      )}
    </>
  )
}

function ProgressCost({ progress }: { progress: OptimizeProgress }) {
  const range = formatInrRange(progress.best_cost_inr_low, progress.best_cost_inr_high)
  if (range) return <Readout label="Cost" value={range} note="Estimate, order of magnitude" />
  return <Readout label="Cost" kind="text" value="Not priced" note="The layout uses an intervention with no sourced rate." />
}

export function OptimizeViewport() {
  const job = useStore((s) => s.job)
  const request = useStore((s) => s.request)
  const total = job.progress.at(-1)?.generations_total ?? request.generations
  const showBand = job.progress.some(bandsDiffer)

  return (
    <>
      <div className="viewport-head">
        <h2 className="viewport-title">Convergence</h2>
        <p className="viewport-sub">
          Best layout found so far, by generation: change in mean modelled surface temperature over the design area.
        </p>
      </div>
      {job.progress.length === 0 ? (
        <p className="viewport-message">
          {job.status === 'error' ? 'The search did not start.' : 'Waiting for the first generation.'}
        </p>
      ) : (
        <ConvergenceChart progress={job.progress} generationsTotal={total} showBand={showBand} />
      )}
      <div className="legend">
        <span className="legend-item">
          <span className="legend-line" aria-hidden="true" />
          {showBand ? 'Conservative end, the end the search ranks on' : 'Best layout'}
        </span>
        {showBand && (
          <span className="legend-item">
            <span className="legend-band" aria-hidden="true" />
            Band to the more-cooling end, from the published coating coefficient range. The axis follows the
            conservative end, so the band can run past it.
          </span>
        )}
      </div>
      {job.handle && <LayoutPreview design={job.handle.design_grid} preview={job.preview} />}
    </>
  )
}

function ConvergenceChart({
  progress,
  generationsTotal,
  showBand,
}: {
  progress: OptimizeProgress[]
  generationsTotal: number
  showBand: boolean
}) {
  const data = useMemo(
    () =>
      progress.map((p) => ({
        generation: p.generation,
        high_c: p.best_temp_delta_c_high,
        band_c: [p.best_temp_delta_c_low, p.best_temp_delta_c_high],
      })),
    [progress],
  )
  const domain = useMemo(
    () => paddedDomain(progress.map((p) => p.best_temp_delta_c_high), CHART_PAD_FRACTION, CHART_MIN_PAD_C),
    [progress],
  )
  return (
    <div className="convergence">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 24, bottom: 8, left: 16 }}>
          <CartesianGrid className="chart-grid" vertical={false} />
          <XAxis
            dataKey="generation"
            type="number"
            domain={[0, generationsTotal]}
            allowDecimals={false}
            tickFormatter={(v: number) => formatCount(v)}
          />
          <YAxis
            width={72}
            domain={domain}
            allowDataOverflow
            tickFormatter={(v: number) => formatSigned(v, DELTA_DECIMALS)}
            label={{ value: 'Change in surface temperature, °C', angle: -90, position: 'insideLeft', offset: -8, style: { textAnchor: 'middle' } }}
          />
          {showBand && (
            <Area className="band-cooling" dataKey="band_c" type="stepAfter" activeDot={false} isAnimationActive={false} />
          )}
          <Line className="curve-conservative" dataKey="high_c" type="stepAfter" dot={false} activeDot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="chart-axis-label">Generation</p>
    </div>
  )
}

/** SVG path data in the preview's coordinates: x along the street (row), y across it (column). */
function previewPath(points: CellPoint[]): string {
  return points.map(([col, row], i) => `${i === 0 ? 'M' : 'L'}${row.toFixed(2)} ${col.toFixed(2)}`).join('')
}

function LayoutPreview({ design, preview }: { design: DesignGrid; preview: Intervention[] | null }) {
  const basemap = useStore((s) => s.basemap)
  const street = useStore((s) => s.street)
  const clipId = `layout-clip${useId().replace(/:/g, '')}`
  const [frameRef, frameSize] = useElementSize<HTMLDivElement>()
  const [rows, cols] = design.shape
  const context = useMemo(
    () =>
      basemap.status === 'ready'
        ? designGridContext(basemap.data.roads, basemap.data.buildings, design, PREVIEW_CONTEXT_MARGIN_M)
        : null,
    [basemap, design],
  )
  // Labels are placed in pixels, then drawn in grid units: one unit is one cell, px_per_cell pixels wide.
  const px_per_cell = frameSize.width_px / rows
  const labels = useMemo(() => {
    if (!context || basemap.status !== 'ready' || !street || px_per_cell <= 0) return []
    return designGridLabels(
      context.roads,
      design.shape,
      (col, row) => [row * px_per_cell, col * px_per_cell],
      { osmName: basemap.data.street_osm_name, label: streetShortName(street.name) },
      measurer(readBodyFont(LABEL_FONT_PX)),
      LABEL_FONT_PX,
      { x: 0, y: 0, w: rows * px_per_cell, h: cols * px_per_cell },
      { gap: PREVIEW_LABEL_GAP_PX, pad: LABEL_PAD_PX, maxCrossStreets: CROSS_STREET_LABELS_MAX, inward: true },
    )
  }, [context, basemap, street, px_per_cell, design.shape, rows, cols])

  return (
    <figure className="layout-preview">
      <div ref={frameRef}>
      <svg
        viewBox={`0 0 ${rows} ${cols}`}
        // Sized to the grid's own proportions, so the border is the grid edge and the street never looks cut short.
        style={{ aspectRatio: `${rows} / ${cols}`, maxWidth: `calc(${PREVIEW_MAX_HEIGHT_REM}rem * ${rows / cols})` }}
        role="img"
        aria-label="Current best layout on the street"
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={0} y={0} width={rows} height={cols} />
          </clipPath>
        </defs>
        <rect className="layout-bg" x={0} y={0} width={rows} height={cols} />
        {preview
          ?.filter((iv) => iv.type !== 'tree')
          .flatMap((iv) => iv.cells.map(([row, col]) => <rect key={`${iv.type}${row}-${col}`} className="layout-coated" x={row} y={col} width={1} height={1} />))}
        {context && (
          <g clipPath={`url(#${clipId})`}>
            {context.buildings.map((ring, i) => (
              <path key={`b${i}`} className="layout-context-building" d={previewPath(ring)} />
            ))}
            {context.roads.map((road, i) => (
              <path key={`r${i}`} className={`layout-context-road layout-context-${road.weight}`} d={previewPath(road.points)} />
            ))}
          </g>
        )}
        {preview
          ?.filter((iv) => iv.type === 'tree')
          .flatMap((iv) => iv.cells.map(([row, col]) => <circle key={`tree${row}-${col}`} className="layout-tree" cx={row + 0.5} cy={col + 0.5} r={0.7} />))}
        {labels.map((label) => (
          <text
            key={label.text}
            className="place-label"
            x={label.x / px_per_cell}
            y={label.y / px_per_cell}
            // Inline, in user units (cells here), so no stylesheet font size can override the scale.
            style={{ fontSize: `${LABEL_FONT_PX / px_per_cell}px`, strokeWidth: `${LABEL_HALO_PX / px_per_cell}px` }}
            textAnchor={label.align === 'center' ? 'middle' : label.align === 'right' ? 'end' : 'start'}
            dominantBaseline="central"
          >
            {label.text}
          </text>
        ))}
      </svg>
      </div>
      <figcaption className="legend">
        <span>
          {preview
            ? 'Current best layout on the street-aligned design grid, drawn along the street. A layout, not temperatures.'
            : 'No layout received yet.'}
        </span>
        {context && (
          <span className="legend-item">
            <span className="legend-context" aria-hidden="true" />
            Road centrelines and building footprints, OpenStreetMap and Overture
          </span>
        )}
        {preview?.map((iv) => (
          <span className="legend-item" key={iv.type}>
            <span className={iv.type === 'tree' ? 'legend-tree' : 'legend-coated'} aria-hidden="true" />
            <span className="mono">{formatCount(iv.cells.length)}</span> {INTERVENTION_LABELS[iv.type]}
            {iv.cells.length === 1 ? '' : iv.type === 'tree' ? 's' : ' cells'}
          </span>
        ))}
      </figcaption>
    </figure>
  )
}
