// Stage 03: the result. For now a 2D heat grid; the 3D scene replaces the viewport on Day 6.

import { useCallback, useMemo, useState } from 'react'
import {
  CROSS_SECTION_SOURCE_LABELS,
  DELTA_DECIMALS,
  ERROR_DECIMALS,
  INTERVENTION_LABELS,
  TEMP_DECIMALS,
  formatBand,
  formatCount,
  formatDeltaBand,
  formatInrRange,
  formatNumber,
  formatSigned,
} from '../lib/format.ts'
import { streetFrameAffine } from '../lib/geometry.ts'
import { ARM_ORDER, budgetMatched } from '../lib/model.ts'
import { gridDomain } from '../lib/thermal.ts'
import { useStore } from '../store/store.ts'
import type { Comparison, ComparisonArm, OptimizationResult } from '../types/contracts.ts'
import { HeatCanvas, type OverlayContext } from '../ui/HeatCanvas.tsx'
import { Numeral } from '../ui/Numeral.tsx'
import { Readout } from '../ui/Readout.tsx'
import { ThermalScale } from '../ui/ThermalScale.tsx'
import { useReveal } from '../ui/hooks.ts'
import { readSurfaceColor } from '../ui/tokens.ts'

type View = 'before' | 'after'
type BandEnd = 'high' | 'low'

const ARM_LABELS: Record<keyof Comparison, string> = {
  random: 'Random layouts, mean',
  greedy: 'Greedy, hottest cell first',
  design_guideline: 'Design guideline layout',
  ga: 'Searched layout',
}

/** Owns the one reveal clock, shared by the heat grid and the delta numeral so they land together. */
export function OperateStage() {
  const result = useStore((s) => s.result)!
  const [view, setView] = useState<View>('before')
  const [bandEnd, setBandEnd] = useState<BandEnd>('high')
  const [revealed, setRevealed] = useState(false)
  const { progress, play } = useReveal()

  const showAfter = () => {
    setView('after')
    if (!revealed) {
      setRevealed(true)
      play()
    }
  }

  return (
    <>
      <aside className="panel" aria-label="Result data">
        <OperatePanel result={result} />
      </aside>
      <section className="viewport" aria-label="Result viewport">
        <OperateViewport
          result={result}
          view={view}
          onBefore={() => setView('before')}
          onAfter={showAfter}
          bandEnd={bandEnd}
          onBandEnd={setBandEnd}
          progress={view === 'after' ? progress : 0}
        />
      </section>
      <ResultBar result={result} revealed={revealed} progress={progress} />
    </>
  )
}

function OperatePanel({ result }: { result: OptimizationResult }) {
  const thermalStreet = useStore((s) => s.thermalStreet)
  const goTo = useStore((s) => s.goTo)
  const design_m = formatCount(result.resolution.design_resolution_m)
  const cellArea_m2 = result.design_grid.cell_size_m ** 2
  const trees = result.interventions.filter((iv) => iv.type === 'tree').reduce((n, iv) => n + iv.cells.length, 0)
  const coated = result.interventions.filter((iv) => iv.type !== 'tree').reduce((n, iv) => n + iv.cells.length, 0)

  return (
    <>
      <section className="panel-section">
        <h2 className="panel-title">{result.street.name}</h2>
      </section>

      <section className="panel-section">
        <dl className="readouts">
          {thermalStreet.status === 'ready' && (
            <Readout
              size="lg"
              label="Street surface temperature, mean"
              value={formatNumber(thermalStreet.data.stats.mean_c, TEMP_DECIMALS)}
              unit="°C"
              note={`measured, ${formatCount(thermalStreet.data.provenance.delivered_resolution_m)} m`}
            />
          )}
          <Readout
            label="Design area, before"
            value={formatNumber(result.baseline_temp_c, TEMP_DECIMALS)}
            unit="°C"
            note={`modelled at ${design_m} m design resolution`}
          />
          <Readout
            label="Design area, after"
            value={formatBand(result.optimized_temp_c_low, result.optimized_temp_c_high, TEMP_DECIMALS)}
            unit="°C"
            note={`modelled at ${design_m} m design resolution`}
          />
          <Readout
            label="Model error"
            value={`±${formatNumber(result.model.rmse_holdout_c, ERROR_DECIMALS)}`}
            unit="°C"
            note={`Hold-out RMSE per ${formatCount(result.resolution.calibration_resolution_m)} m calibration cell`}
          />
          <Readout label="Mean-only baseline" value={formatNumber(result.model.rmse_mean_baseline_c, ERROR_DECIMALS)} unit="°C" />
        </dl>
      </section>

      <section className="panel-section" aria-labelledby="layout-heading">
        <h3 id="layout-heading">Layout</h3>
        <dl className="readouts">
          <Readout label="Street trees" value={formatCount(trees)} />
          <Readout label="Coated cells" value={formatCount(coated)} note={`${formatCount(coated * cellArea_m2)} m² of reflective coating`} />
        </dl>
      </section>

      <section className="panel-section" aria-labelledby="section-heading">
        <h3 id="section-heading">Cross-section</h3>
        <p className="panel-note">{CROSS_SECTION_SOURCE_LABELS[result.cross_section.source]}</p>
        <p className="panel-note">{result.cross_section.reference}</p>
      </section>

      <button className="button" type="button" onClick={() => goTo('diagnose')}>
        Change search settings
      </button>
    </>
  )
}

interface OperateViewportProps {
  result: OptimizationResult
  view: View
  onBefore: () => void
  onAfter: () => void
  bandEnd: BandEnd
  onBandEnd: (end: BandEnd) => void
  progress: number
}

function OperateViewport({ result, view, onBefore, onAfter, bandEnd, onBandEnd, progress }: OperateViewportProps) {
  // Along the street, not north-up: a 200 m by 40 m strip drawn north-up leaves 2 m cells a few pixels wide.
  const affine = useMemo(() => streetFrameAffine(result.design_grid), [result.design_grid])
  // One scale for before and both after bands, so a colour means the same temperature in every view.
  const domain = useMemo(
    () => gridDomain(result.before_lst_c, result.after_lst_c_low, result.after_lst_c_high),
    [result.before_lst_c, result.after_lst_c_low, result.after_lst_c_high],
  )
  const after = bandEnd === 'high' ? result.after_lst_c_high : result.after_lst_c_low
  const bandsDiffer = formatSigned(result.temp_delta_c_low, DELTA_DECIMALS) !== formatSigned(result.temp_delta_c_high, DELTA_DECIMALS)
  const design_m = formatCount(result.resolution.design_resolution_m)

  const overlay = useCallback(
    ({ ctx, cellToScreen, cell_px }: OverlayContext) => {
      if (view !== 'after') return
      const paper = readSurfaceColor('--paper')
      const paperDim = readSurfaceColor('--paper-dim')
      for (const iv of result.interventions) {
        if (iv.type === 'tree') {
          ctx.strokeStyle = paper
          ctx.lineWidth = 1.5
          for (const [row, col] of iv.cells) {
            const [x, y] = cellToScreen(col + 0.5, row + 0.5)
            ctx.beginPath()
            ctx.arc(x, y, Math.max(3, cell_px * 0.9), 0, 2 * Math.PI)
            ctx.stroke()
          }
        } else {
          ctx.strokeStyle = paperDim
          ctx.lineWidth = 1
          for (const [row, col] of iv.cells) {
            ctx.beginPath()
            ;[
              [col, row],
              [col + 1, row],
              [col + 1, row + 1],
              [col, row + 1],
            ].forEach(([c, r], i) => {
              const [x, y] = cellToScreen(c, r)
              if (i === 0) ctx.moveTo(x, y)
              else ctx.lineTo(x, y)
            })
            ctx.closePath()
            ctx.stroke()
          }
        }
      }
    },
    [view, result.interventions],
  )

  return (
    <>
      <div className="viewport-head">
        <h2 className="viewport-title">Surface temperature, modelled at {design_m} m design resolution</h2>
        <p className="viewport-sub">
          Model output, not a measurement. {view === 'before' ? "Today's street, from the calibrated model." : 'With the searched layout applied.'}{' '}
          Drawn along the street, start at the left: {formatCount(result.design_grid.shape[0])} by{' '}
          {formatCount(result.design_grid.shape[1])} cells, the street bearing {formatNumber(result.design_grid.bearing_deg, 1)}° from
          grid north.
        </p>
        <div className="controls">
          <div className="segmented" role="group" aria-label="Street state">
            <button type="button" aria-pressed={view === 'before'} onClick={onBefore}>
              Before
            </button>
            <button type="button" aria-pressed={view === 'after'} onClick={onAfter}>
              After
            </button>
          </div>
          {bandsDiffer && (
            <div className="segmented" role="group" aria-label="End of the coating coefficient range">
              <button type="button" aria-pressed={bandEnd === 'high'} onClick={() => onBandEnd('high')}>
                Conservative end
              </button>
              <button type="button" aria-pressed={bandEnd === 'low'} onClick={() => onBandEnd('low')}>
                More-cooling end
              </button>
            </div>
          )}
        </div>
      </div>
      {domain && (
        <HeatCanvas
          values={result.before_lst_c}
          valuesTo={after}
          progress={progress}
          affine={affine}
          shape={result.design_grid.shape}
          domain={domain}
          overlay={overlay}
          ariaLabel={`Modelled surface temperature ${view}, at ${design_m} m design resolution`}
        />
      )}
      <div className="viewport-foot">
        {domain && <ThermalScale domain={domain} caption={`Surface temperature, °C, modelled at ${design_m} m design resolution`} />}
        {view === 'after' && (
          <div className="legend">
            {result.interventions.map((iv) => (
              <span className="legend-item" key={iv.type}>
                <span className={iv.type === 'tree' ? 'legend-tree' : 'legend-coated'} aria-hidden="true" />
                {INTERVENTION_LABELS[iv.type]}
              </span>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

function ArmCost({ arm }: { arm: ComparisonArm }) {
  const range = formatInrRange(arm.cost_inr_low, arm.cost_inr_high)
  return range ? <span className="mono">{range}</span> : <>Not priced</>
}

function ResultBar({ result, revealed, progress }: { result: OptimizationResult; revealed: boolean; progress: number }) {
  const landed = revealed && progress >= 1
  const cost = formatInrRange(result.cost_inr_low, result.cost_inr_high)
  const bandsDiffer = formatDeltaBand(result.temp_delta_c_low, result.temp_delta_c_high).includes(' to ')
  const ga = result.comparison.ga

  return (
    <footer className="resultbar" aria-label="Result">
      <div className="result-block">
        {revealed ? (
          <p className="delta" aria-live="polite">
            <span className="delta-value">
              <Numeral value={result.temp_delta_c_low} decimals={DELTA_DECIMALS} signed progress={progress} />
              {bandsDiffer && (
                <>
                  <span className="delta-to"> to </span>
                  <Numeral value={result.temp_delta_c_high} decimals={DELTA_DECIMALS} signed progress={progress} />
                </>
              )}
            </span>
            <span className="delta-unit">&nbsp;°C</span>
          </p>
        ) : (
          <p className="result-label">Switch to after to apply the searched layout.</p>
        )}
        <p className="result-label">
          Change in mean surface temperature over the design area, modelled at{' '}
          {formatCount(result.resolution.design_resolution_m)} m design resolution.
        </p>
        {bandsDiffer && <p className="result-note">More-cooling end to conservative end, from the published coating coefficient range.</p>}
        <p className="result-note">
          Model error <span className="mono">{`±${formatNumber(result.model.rmse_holdout_c, ERROR_DECIMALS)} °C`}</span> per
          calibration cell; mean-only baseline <span className="mono">{`${formatNumber(result.model.rmse_mean_baseline_c, ERROR_DECIMALS)} °C`}</span>.
        </p>
      </div>

      {landed && (
        <div className="result-block">
          <p className="result-heading">Cost</p>
          {cost ? (
            <>
              <p className="result-cost-value mono">{cost}</p>
              <p className="result-note">Estimate, order of magnitude. Sources in docs/sources.md.</p>
            </>
          ) : (
            <p className="result-note">
              Not priced. No sourced rate for {result.unpriced_interventions.map((t) => INTERVENTION_LABELS[t]).join(', ')}, so
              no cost is shown.
            </p>
          )}
        </div>
      )}

      {landed && (
        <div className="result-block">
          <p className="result-heading">
            {budgetMatched(result.comparison) ? (
              <>
                Same budget for every layout: <span className="mono">{formatCount(ga.trees)}</span> trees,{' '}
                <span className="mono">{formatCount(ga.reflective_cells)}</span> coated cells.
              </>
            ) : (
              'The layouts placed different counts, so this is not a matched-budget comparison.'
            )}
          </p>
          <div className="table-scroll">
            <table className="comparison">
              <thead>
                <tr>
                  <th scope="col">Layout</th>
                  <th scope="col">Change, °C</th>
                  <th scope="col">Trees</th>
                  <th scope="col">Coated cells</th>
                  <th scope="col">Cost</th>
                </tr>
              </thead>
              <tbody>
                {ARM_ORDER.map((key) => {
                  const arm = result.comparison[key]
                  return (
                    <tr key={key} className={key === 'ga' ? 'comparison-ours' : undefined}>
                      <th scope="row">{ARM_LABELS[key]}</th>
                      <td className="mono">{formatDeltaBand(arm.temp_delta_c_low, arm.temp_delta_c_high)}</td>
                      <td className="mono">{formatCount(arm.trees)}</td>
                      <td className="mono">{formatCount(arm.reflective_cells)}</td>
                      <td>
                        <ArmCost arm={arm} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </footer>
  )
}
