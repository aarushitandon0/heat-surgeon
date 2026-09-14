// Stage 00: pick the street.

import { useEffect, useMemo } from 'react'
import { PROFILE_LABELS, formatLatitude, formatLongitude } from '../lib/format.ts'
import { niceStep, stepsWithin } from '../lib/geometry.ts'
import { useStore } from '../store/store.ts'
import type { BBoxWGS84, StreetSummary } from '../types/contracts.ts'
import { useElementSize } from '../ui/hooks.ts'

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

  useEffect(() => {
    if (streets.status === 'idle') void loadStreets()
  }, [streets.status, loadStreets])

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
    </>
  )
}

export function LocateViewport() {
  const streets = useStore((s) => s.streets)
  const current = useStore((s) => s.street)
  const selectStreet = useStore((s) => s.selectStreet)
  const data = streets.status === 'ready' ? streets.data : []
  const unverified = data.filter((s) => !s.bbox_street_verified).map((s) => s.name)

  return (
    <>
      <div className="viewport-head">
        <h2 className="viewport-title">Streets</h2>
        <p className="viewport-sub">
          Thin boxes are the 2 km calibration windows; heavy strokes are the street extents. WGS84, for display
          only.
          {unverified.length > 0 && ` Extent not yet checked against OpenStreetMap: ${unverified.join(', ')}.`}
        </p>
      </div>
      <StreetMap streets={data} selectedId={current?.id ?? null} onSelect={selectStreet} />
    </>
  )
}

interface StreetMapProps {
  streets: StreetSummary[]
  selectedId: string | null
  onSelect: (street: StreetSummary) => void
}

function StreetMap({ streets, selectedId, onSelect }: StreetMapProps) {
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
        </svg>
      )}
    </div>
  )
}
