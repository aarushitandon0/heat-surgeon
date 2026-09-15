// Stage 00: pick the street, or read where trees cool most per rupee across the calibrated windows.

import { useEffect, useMemo, useState } from 'react'
import {
  CROSS_SECTION_SOURCE_LABELS,
  DELTA_DECIMALS,
  ERROR_DECIMALS,
  PROFILE_LABELS,
  formatBand,
  formatCoolingPerLakhRange,
  formatCount,
  formatInrRange,
  formatLatitude,
  formatLongitude,
  formatNumber,
  formatSigned,
} from '../lib/format.ts'
import { niceStep, stepsWithin } from '../lib/geometry.ts'
import {
  RANKED_TOP_COUNT,
  atCapacity,
  dominantWindow,
  errorRanges,
  formatRankRange,
  rankedKey,
  skippedByReason,
  uncertainRankCount,
} from '../lib/ranking.ts'
import { useStore } from '../store/store.ts'
import type { BBoxWGS84, RankedStreet, SkippedStreet, StreetRanking, StreetSummary } from '../types/contracts.ts'

/** What each backend skip reason means, in plain terms. Keyed by the exact reason strings in app/ranking.py. */
const SKIP_EXPLANATIONS: Record<string, string> = {
  "The design grid extends past the window's calibration cells.":
    'Its 200 m by 40 m design grid runs past the part of the window covered by calibration cells. Ranking it would take surface temperature from outside the calibrated area, so it is not ranked.',
  'The cross-section has no plantable tree pits.':
    "Its cross-section has no tree pit band: its OpenStreetMap tags give only footway and carriageway widths, no right of way could be measured from buildings, or the right of way is narrower than the narrowest Pune street design template (7 m). Trees might still fit on these streets; this method has no rule for placing them.",
}
import { useElementSize } from '../ui/hooks.ts'
import { Readout } from '../ui/Readout.tsx'

const MAP_MARGIN_PX = 40
const MAP_GRATICULE_LINES = 8
const DEG_TO_RAD = Math.PI / 180

function bboxCentre(bbox: BBoxWGS84): [number, number] {
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
}

export function LocatePanel() {
  const streets = useStore((s) => s.streets)
  const current = useStore((s) => s.street)
  const loadStreets = useStore((s) => s.loadStreets)
  const selectStreet = useStore((s) => s.selectStreet)
  const ranking = useStore((s) => s.ranking)
  const loadRanking = useStore((s) => s.loadRanking)

  useEffect(() => {
    if (streets.status === 'idle') void loadStreets()
  }, [streets.status, loadStreets])

  useEffect(() => {
    if (streets.status === 'ready' && ranking.status === 'idle') void loadRanking()
  }, [streets.status, ranking.status, loadRanking])

  return (
    <>
      <section className="panel-section">
        <h2 className="panel-title">Select a street to begin.</h2>
        <p className="panel-copy">
          Each street has a 2 km window of Landsat surface temperature and Sentinel-2 land cover. The model is
          calibrated on the window, then applied to the street.
        </p>
      </section>

      {streets.status === 'loading' && <p className="status">Loading streets.</p>}
      {streets.status === 'error' && (
        <section className="panel-section">
          <p className="status status-error" role="alert">
            {streets.message}
          </p>
          <button className="button" type="button" onClick={() => void loadStreets()}>
            Try again
          </button>
        </section>
      )}
      {streets.status === 'ready' && (
        <ul className="street-list">
          {streets.data.map((street) => {
            const [lon, lat] = bboxCentre(street.bbox_street)
            return (
              <li key={street.id}>
                <button
                  className="street-row"
                  type="button"
                  aria-pressed={current?.id === street.id}
                  onClick={() => selectStreet(street)}
                >
                  <span className="street-name">{street.name}</span>
                  <span className="street-meta">{PROFILE_LABELS[street.profile]}</span>
                  <span className="street-coords mono">
                    {formatLatitude(lat)} {formatLongitude(lon)}
                  </span>
                  <span className="street-meta">{street.cached ? 'Cached data' : 'Not cached. Needs live data.'}</span>
                  {!street.bbox_street_verified && (
                    <span className="street-meta">Street extent not yet checked against OpenStreetMap.</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {streets.status === 'ready' && ranking.status === 'loading' && <p className="status">Loading the street ranking.</p>}
      {streets.status === 'ready' && ranking.status === 'error' && (
        <section className="panel-section">
          <h3>Where trees cool most per rupee</h3>
          <p className="status status-error" role="alert">
            {ranking.message}
          </p>
        </section>
      )}
      {ranking.status === 'ready' && <RankingSection ranking={ranking.data} fixtures={streets.status === 'ready' ? streets.data : []} />}
    </>
  )
}

function RankingSection({ ranking, fixtures }: { ranking: StreetRanking; fixtures: StreetSummary[] }) {
  const selectedKey = useStore((s) => s.rankedKey)
  const selectRanked = useStore((s) => s.selectRanked)
  const [showAll, setShowAll] = useState(false)
  const errors = errorRanges(ranking.windows)
  const shown = showAll ? ranking.streets : ranking.streets.slice(0, RANKED_TOP_COUNT)
  const selected = ranking.streets.find((s) => rankedKey(s) === selectedKey) ?? null
  const dominant = dominantWindow(ranking.streets, RANKED_TOP_COUNT)
  const dominantName = ranking.windows.find((w) => w.street_id === dominant?.window_street_id)?.name

  return (
    <>
      <section className="panel-section" aria-labelledby="ranking-heading">
        <h3 id="ranking-heading">Where trees cool most per rupee</h3>
        <p className="panel-note">
          <span className="mono">{formatCount(ranking.streets.length)}</span> streets inside the four calibrated
          windows, ranked by modelled cooling per ₹1 lakh. Each gets up to{' '}
          <span className="mono">{formatCount(ranking.request.trees_max)}</span> trees and no coating, a short search of{' '}
          <span className="mono">{formatCount(ranking.request.generations)}</span> generations, and its own window's
          calibration. Modelled surface temperature at <span className="mono">{formatCount(ranking.resolution.design_resolution_m)}</span> m
          design resolution, not a measurement. The windows are not a ward.
        </p>
        <p className="panel-note">
          Model error in these windows is <span className="mono">±{formatBand(...errors.holdout_c, ERROR_DECIMALS)}</span> °C
          per <span className="mono">{formatCount(ranking.resolution.calibration_resolution_m)}</span> m cell, against{' '}
          <span className="mono">{formatBand(...errors.mean_baseline_c, ERROR_DECIMALS)}</span> °C for predicting the mean.
          That error is larger than the differences between most neighbouring ranks.
        </p>
        <p className="panel-note">
          Ranks are shown as the range each street could hold. Two streets are tied when their modelled cooling per tree
          differs by less than the 95% interval of the calibration coefficients' error.{' '}
          <span className="mono">{formatCount(uncertainRankCount(ranking.streets))}</span> of the{' '}
          <span className="mono">{formatCount(ranking.streets.length)}</span> streets could hold more than one rank. The
          coefficient errors are optimistic, so the true ranges are wider.
        </p>
        {dominant && dominant.streets > RANKED_TOP_COUNT / 2 && (
          <p className="panel-note">
            <span className="mono">{formatCount(dominant.streets)}</span> of the top{' '}
            <span className="mono">{formatCount(RANKED_TOP_COUNT)}</span> are in the {dominantName ?? dominant.window_street_id}{' '}
            window. Ranks across windows partly reflect differences between the windows' calibrations, not only between
            streets. Ranks within one window share a calibration and are sturdier.
          </p>
        )}
        <ol className="street-list">
          {shown.map((street) => {
            const key = rankedKey(street)
            return (
              <li key={key}>
                <button
                  className="street-row"
                  type="button"
                  aria-pressed={key === selectedKey}
                  onClick={() => selectRanked(key === selectedKey ? null : key)}
                >
                  <span className="street-name">{street.osm_name}</span>
                  <span className="street-meta">
                    {street.rank_best === street.rank_worst ? 'Rank ' : 'Ranks '}
                    <span className="mono">{formatRankRange(street)}</span>
                  </span>
                  <span className="street-meta">
                    <span className="mono">{formatCoolingPerLakhRange(street.cooling_c_per_lakh_inr_low, street.cooling_c_per_lakh_inr_high)}</span>{' '}
                    °C per ₹1 lakh, estimate
                  </span>
                  <span className="street-meta">
                    <span className="mono">{formatCount(street.trees)}</span> trees of{' '}
                    <span className="mono">{formatCount(street.tree_capacity)}</span> plantable
                    {atCapacity(street) && ', every pit used, so the search has little to choose'}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
        {!showAll && ranking.streets.length > RANKED_TOP_COUNT && (
          <button className="button" type="button" onClick={() => setShowAll(true)}>
            Show all {formatCount(ranking.streets.length)} streets
          </button>
        )}
      </section>
      {ranking.skipped.length > 0 && <SkippedSection skipped={ranking.skipped} ranked={ranking.streets.length} />}
      {selected && <RankedDetail street={selected} ranking={ranking} fixtures={fixtures} />}
    </>
  )
}

/** The streets the method could not rank, counted and explained. Stating the limit beats dropping them quietly. */
function SkippedSection({ skipped, ranked }: { skipped: SkippedStreet[]; ranked: number }) {
  const [open, setOpen] = useState(false)
  const groups = skippedByReason(skipped)
  return (
    <section className="panel-section" aria-labelledby="skipped-heading">
      <h3 id="skipped-heading">Streets not ranked</h3>
      <p className="panel-note">
        <span className="mono">{formatCount(skipped.length)}</span> of the{' '}
        <span className="mono">{formatCount(skipped.length + ranked)}</span> named streets long enough for a design segment
        are not ranked. This method only ranks a street where it has calibration cells under the whole design grid and a
        cross-section that allows tree pits.
      </p>
      {groups.map((group) => (
        <p key={group.reason} className="panel-note">
          <span className="mono">{formatCount(group.streets.length)}</span>. {SKIP_EXPLANATIONS[group.reason] ?? group.reason}
        </p>
      ))}
      <button className="button" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? 'Hide the streets not ranked' : 'List the streets not ranked'}
      </button>
      {open &&
        groups.map((group) => (
          <div key={group.reason}>
            <p className="panel-note">{group.reason}</p>
            <ul className="street-list">
              {group.streets.map((s) => (
                <li key={`${s.window_street_id}/${s.osm_name}`} className="street-meta">
                  {s.osm_name}
                </li>
              ))}
            </ul>
          </div>
        ))}
    </section>
  )
}

function RankedDetail({ street, ranking, fixtures }: { street: RankedStreet; ranking: StreetRanking; fixtures: StreetSummary[] }) {
  const selectStreet = useStore((s) => s.selectStreet)
  const window = ranking.windows.find((w) => w.street_id === street.window_street_id)
  const fixture = fixtures.find((f) => f.id === street.fixture_street_id) ?? null
  const cost = formatInrRange(street.cost_inr_low, street.cost_inr_high)

  return (
    <section className="panel-section" aria-labelledby="ranked-detail-heading">
      <h3 id="ranked-detail-heading">{street.osm_name}</h3>
      <dl className="readouts">
        <Readout
          label={street.rank_best === street.rank_worst ? 'Rank' : 'Ranks it could hold'}
          value={formatRankRange(street)}
          note="Within the 95% interval of the calibration coefficients' error."
        />
        <Readout
          label="Change, searched layout"
          value={`${formatSigned(street.temp_delta_c, DELTA_DECIMALS)} ± ${formatNumber(street.temp_delta_se_c, DELTA_DECIMALS)}`}
          unit="°C"
          note="Mean over the 200 m design segment, modelled. ± one standard error from the calibration coefficients."
        />
        <Readout label="Random layouts, mean" value={formatSigned(street.random_temp_delta_c, DELTA_DECIMALS)} unit="°C" />
        <Readout label="Design guideline" value={formatSigned(street.design_guideline_temp_delta_c, DELTA_DECIMALS)} unit="°C" />
        <Readout
          label="Trees"
          value={`${formatCount(street.trees)} of ${formatCount(street.tree_capacity)}`}
          note="Placed by the search, of the most the plantable strips hold."
        />
        {cost && <Readout label="Cost, estimate" value={cost} note="Planting, guard and first-year care." />}
        <Readout
          label="Cooling per ₹1 lakh"
          value={formatCoolingPerLakhRange(street.cooling_c_per_lakh_inr_low, street.cooling_c_per_lakh_inr_high)}
          unit="°C"
        />
      </dl>
      <p className="panel-note">
        Calibrated on the {window?.name ?? street.window_street_id} window. {CROSS_SECTION_SOURCE_LABELS[street.cross_section_source]}
      </p>
      {fixture && (
        <button className="button" type="button" onClick={() => selectStreet(fixture)}>
          Open the full analysis for this street
        </button>
      )}
    </section>
  )
}

export function LocateViewport() {
  const streets = useStore((s) => s.streets)
  const current = useStore((s) => s.street)
  const selectStreet = useStore((s) => s.selectStreet)
  const ranking = useStore((s) => s.ranking)
  const rankedKeySelected = useStore((s) => s.rankedKey)
  const selectRanked = useStore((s) => s.selectRanked)
  const data = streets.status === 'ready' ? streets.data : []
  const ranked = ranking.status === 'ready' ? ranking.data.streets : []
  const unverified = data.filter((s) => !s.bbox_street_verified).map((s) => s.name)

  return (
    <>
      <div className="viewport-head">
        <h2 className="viewport-title">Streets</h2>
        <p className="viewport-sub">
          Thin boxes are the 2 km calibration windows; heavy strokes are the street extents. WGS84, for display
          only.
          {ranked.length > 0 &&
            ` Short strokes are the ranked 200 m design segments, heavier for the streets that could rank in the top ${RANKED_TOP_COUNT} by modelled cooling per ₹1 lakh within the model's error.`}
          {unverified.length > 0 && ` Extent not yet checked against OpenStreetMap: ${unverified.join(', ')}.`}
        </p>
      </div>
      <StreetMap
        streets={data}
        selectedId={current?.id ?? null}
        onSelect={selectStreet}
        ranked={ranked}
        rankedSelectedKey={rankedKeySelected}
        onSelectRanked={selectRanked}
      />
    </>
  )
}

interface StreetMapProps {
  streets: StreetSummary[]
  selectedId: string | null
  onSelect: (street: StreetSummary) => void
  ranked: RankedStreet[]
  rankedSelectedKey: string | null
  onSelectRanked: (key: string | null) => void
}

function StreetMap({ streets, selectedId, onSelect, ranked, rankedSelectedKey, onSelectRanked }: StreetMapProps) {
  const [ref, size] = useElementSize<HTMLDivElement>()

  const layout = useMemo(() => {
    const { width_px, height_px } = size
    if (width_px === 0 || height_px === 0 || streets.length === 0) return null
    const boxes = streets.flatMap((s) => [s.bbox_window, s.bbox_street])
    const minLon = Math.min(...boxes.map((b) => b[0]))
    const minLat = Math.min(...boxes.map((b) => b[1]))
    const maxLon = Math.max(...boxes.map((b) => b[2]))
    const maxLat = Math.max(...boxes.map((b) => b[3]))
    // Equirectangular at the mean latitude: fine for a few kilometres, and only used for display.
    const kx = Math.cos(((minLat + maxLat) / 2) * DEG_TO_RAD)
    const scale_px_per_deg = Math.min(
      (width_px - 2 * MAP_MARGIN_PX) / ((maxLon - minLon) * kx),
      (height_px - 2 * MAP_MARGIN_PX) / (maxLat - minLat),
    )
    const ox = (width_px - (maxLon - minLon) * kx * scale_px_per_deg) / 2
    const oy = (height_px - (maxLat - minLat) * scale_px_per_deg) / 2
    const x = (lon: number) => ox + (lon - minLon) * kx * scale_px_per_deg
    const y = (lat: number) => oy + (maxLat - lat) * scale_px_per_deg
    const westLon = minLon - ox / (kx * scale_px_per_deg)
    const eastLon = westLon + width_px / (kx * scale_px_per_deg)
    const northLat = maxLat + oy / scale_px_per_deg
    const southLat = northLat - height_px / scale_px_per_deg
    const step_deg = niceStep(Math.max(eastLon - westLon, northLat - southLat), MAP_GRATICULE_LINES)
    return {
      x,
      y,
      lons: stepsWithin(westLon, eastLon, step_deg),
      lats: stepsWithin(southLat, northLat, step_deg),
      decimals: Math.max(0, Math.ceil(-Math.log10(step_deg))),
    }
  }, [size, streets])

  const rect = (bbox: BBoxWGS84) =>
    layout && {
      x: layout.x(bbox[0]),
      y: layout.y(bbox[3]),
      width: Math.max(2, layout.x(bbox[2]) - layout.x(bbox[0])),
      height: Math.max(2, layout.y(bbox[1]) - layout.y(bbox[3])),
    }

  const selectedRanked = ranked.find((s) => rankedKey(s) === rankedSelectedKey) ?? null

  return (
    <div className="map" ref={ref}>
      {layout && (
        <svg width={size.width_px} height={size.height_px} role="group" aria-label="Street locations">
          {layout.lons.map((lon) => (
            <g key={`lon${lon}`}>
              <line className="map-graticule" x1={layout.x(lon)} x2={layout.x(lon)} y1={0} y2={size.height_px} />
              <text className="map-graticule-label" x={layout.x(lon) + 4} y={14}>
                {formatLongitude(lon, layout.decimals)}
              </text>
            </g>
          ))}
          {layout.lats.map((lat) => (
            <g key={`lat${lat}`}>
              <line className="map-graticule" x1={0} x2={size.width_px} y1={layout.y(lat)} y2={layout.y(lat)} />
              <text className="map-graticule-label" x={4} y={layout.y(lat) - 4}>
                {formatLatitude(lat, layout.decimals)}
              </text>
            </g>
          ))}
          {streets.map((street) => {
            const selected = street.id === selectedId
            const windowRect = rect(street.bbox_window)!
            return (
              <g
                key={street.id}
                className={selected ? 'map-street-group map-selected' : 'map-street-group'}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                aria-label={street.name}
                onClick={() => onSelect(street)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(street)
                  }
                }}
              >
                <rect className="map-window" {...windowRect} />
                <rect className="map-street" {...rect(street.bbox_street)!} />
                <text className="map-label" x={windowRect.x + 6} y={windowRect.y + 16}>
                  {street.name}
                </text>
              </g>
            )
          })}
          {/* Ranked segments. The ranked list in the panel is the keyboard path; these are a pointer shortcut. */}
          <g aria-hidden="true">
            {[...ranked].reverse().map((street) => {
              const key = rankedKey(street)
              const [[lon0, lat0], [lon1, lat1]] = street.segment_wgs84
              const className = [
                'map-ranked',
                street.rank_best <= RANKED_TOP_COUNT ? 'map-ranked-top' : '',
                key === rankedSelectedKey ? 'map-ranked-selected' : '',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <line
                  key={key}
                  className={className}
                  x1={layout.x(lon0)}
                  y1={layout.y(lat0)}
                  x2={layout.x(lon1)}
                  y2={layout.y(lat1)}
                  onClick={() => onSelectRanked(key === rankedSelectedKey ? null : key)}
                />
              )
            })}
          </g>
          {selectedRanked && (
            <text
              className="map-label"
              x={layout.x((selectedRanked.segment_wgs84[0][0] + selectedRanked.segment_wgs84[1][0]) / 2) + 8}
              y={layout.y((selectedRanked.segment_wgs84[0][1] + selectedRanked.segment_wgs84[1][1]) / 2) - 8}
            >
              {selectedRanked.osm_name}, {selectedRanked.rank_best === selectedRanked.rank_worst ? 'rank' : 'ranks'}{' '}
              {formatRankRange(selectedRanked)}
            </text>
          )}
        </svg>
      )}
    </div>
  )
}
