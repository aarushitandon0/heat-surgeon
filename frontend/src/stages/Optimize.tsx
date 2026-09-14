// Stage 02: the search, live. Every number here comes from the WebSocket stream.

import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import {
  DELTA_DECIMALS,
  ERROR_DECIMALS,
  INTERVENTION_LABELS,
  formatCount,
  formatInrRange,
  formatNumber,
  formatSigned,
} from '../lib/format.ts'
import { useStore, type JobState } from '../store/store.ts'
import type { GridShape, Intervention, OptimizeProgress } from '../types/contracts.ts'
import { Readout } from '../ui/Readout.tsx'

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
            <Readout
              label="Change, conservative end"
              value={formatSigned(latest.best_temp_delta_c_high, DELTA_DECIMALS)}
              unit="°C"
              note="Mean over the design area, modelled. The search ranks on this end."
            />
            <Readout label="Change, more-cooling end" value={formatSigned(latest.best_temp_delta_c_low, DELTA_DECIMALS)} unit="°C" />
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

  return (
    <>
      <div className="viewport-head">
        <h2 className="viewport-title">Convergence</h2>
        <p className="viewport-sub">
          Best layout found so far, by generation: change in mean modelled surface temperature over the design area, °C.
        </p>
      </div>
      {job.progress.length === 0 ? (
        <p className="viewport-message">
          {job.status === 'error' ? 'The search did not start.' : 'Waiting for the first generation.'}
        </p>
      ) : (
        <ConvergenceChart progress={job.progress} generationsTotal={total} />
      )}
      <div className="legend">
        <span className="legend-item">
          <span className="legend-line" aria-hidden="true" />
          Conservative end
        </span>
        <span className="legend-item">
          <span className="legend-line legend-line-dashed" aria-hidden="true" />
          More-cooling end
        </span>
      </div>
      {job.handle && <LayoutPreview shape={job.handle.grid_shape} preview={job.preview} />}
    </>
  )
}

function ConvergenceChart({ progress, generationsTotal }: { progress: OptimizeProgress[]; generationsTotal: number }) {
  const data = useMemo(
    () => progress.map((p) => ({ generation: p.generation, high_c: p.best_temp_delta_c_high, low_c: p.best_temp_delta_c_low })),
    [progress],
  )
  return (
    <div className="convergence">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid className="chart-grid" vertical={false} />
          <XAxis
            dataKey="generation"
            type="number"
            domain={[0, generationsTotal]}
            allowDecimals={false}
            tickFormatter={(v: number) => formatCount(v)}
          />
          <YAxis width={64} domain={['auto', 'auto']} tickFormatter={(v: number) => formatSigned(v, DELTA_DECIMALS)} />
          <Line className="curve-conservative" dataKey="high_c" type="stepAfter" dot={false} activeDot={false} isAnimationActive={false} />
          <Line className="curve-cooling" dataKey="low_c" type="stepAfter" dot={false} activeDot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <p className="chart-axis-label">Generation</p>
    </div>
  )
}

function LayoutPreview({ shape, preview }: { shape: GridShape; preview: Intervention[] | null }) {
  const [rows, cols] = shape
  return (
    <figure className="layout-preview">
      {preview ? (
        <svg viewBox={`0 0 ${rows} ${cols}`} preserveAspectRatio="xMinYMid meet" role="img" aria-label="Current best layout">
          <rect className="layout-bg" x={0} y={0} width={rows} height={cols} />
          {preview
            .filter((iv) => iv.type !== 'tree')
            .flatMap((iv) => iv.cells.map(([row, col]) => <rect key={`${iv.type}${row}-${col}`} className="layout-coated" x={row} y={col} width={1} height={1} />))}
          {preview
            .filter((iv) => iv.type === 'tree')
            .flatMap((iv) => iv.cells.map(([row, col]) => <circle key={`tree${row}-${col}`} className="layout-tree" cx={row + 0.5} cy={col + 0.5} r={0.7} />))}
        </svg>
      ) : (
        <p className="viewport-sub">No layout received yet.</p>
      )}
      <figcaption className="legend">
        <span>Current best layout on the street-aligned design grid, drawn along the street. A layout, not temperatures.</span>
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
