import { useMemo } from 'react'
import { cityWayClass, svgPathData } from '../lib/basemap.ts'
import { cityLabelCandidates, placePointLabels } from '../lib/labels.ts'
import type { CityLocator } from '../types/contracts.ts'
import { LABEL_HALO_PX, LABEL_PAD_PX } from './basemapDraw.ts'
import { useElementSize } from './hooks.ts'
import { measurer } from './textMeasure.ts'
import { readBodyFont } from './tokens.ts'

/** City names in the inset are smaller than street labels: the inset is 12rem wide. */
const LOCATOR_LABEL_FONT_PX = 10
/** A few names make it read as the city; more make it a gazetteer. */
const LOCATOR_LABELS_MAX = 4

interface CityLocatorMapProps {
  city: CityLocator
  /** [min_e, min_n, max_e, max_n] of the 2 km window, in metres, in the same crs as the city ways. */
  window_bounds_m: [number, number, number, number]
}

/** Static inset: the city's major roads and rivers from OpenStreetMap, a few of them named, with the 2 km window boxed. */
export function CityLocatorMap({ city, window_bounds_m }: CityLocatorMapProps) {
  const [frameRef, frameSize] = useElementSize<HTMLDivElement>()
  const [min_e_m, min_n_m, max_e_m, max_n_m] = city.bounds_m
  const width_m = max_e_m - min_e_m
  const height_m = max_n_m - min_n_m

  const paths = useMemo(() => {
    const project = (e_m: number, n_m: number): [number, number] => [e_m - min_e_m, max_n_m - n_m]
    // Rivers first, so roads cross over them.
    return city.ways
      .map((way) => ({ wayClass: cityWayClass(way.kind), d: svgPathData(way.path, project) }))
      .sort((a, b) => Number(b.wayClass === 'river') - Number(a.wayClass === 'river'))
  }, [city.ways, min_e_m, max_n_m])

  const [we, wn, wE, wN] = window_bounds_m
  // Placement runs in pixels; the SVG draws in metres, m_per_px metres to a pixel.
  const m_per_px = frameSize.width_px > 0 ? width_m / frameSize.width_px : 0
  const labels = useMemo(() => {
    if (m_per_px === 0) return []
    const toPx = (e_m: number, n_m: number) => ({ x: (e_m - min_e_m) / m_per_px, y: (max_n_m - n_m) / m_per_px })
    const windowTopLeft = toPx(we, wN)
    const windowBox = { x: windowTopLeft.x, y: windowTopLeft.y, w: (wE - we) / m_per_px, h: (wN - wn) / m_per_px }
    const candidates = cityLabelCandidates(city.ways, city.bounds_m).map((candidate) => ({
      text: candidate.text,
      anchors: candidate.anchors.map(([e, n]) => ({ ...toPx(e, n), align: 'center' as const })),
    }))
    return placePointLabels(
      candidates,
      measurer(readBodyFont(LOCATOR_LABEL_FONT_PX)),
      LOCATOR_LABEL_FONT_PX,
      { x: 0, y: 0, w: width_m / m_per_px, h: height_m / m_per_px },
      [windowBox],
      LOCATOR_LABELS_MAX,
      LABEL_PAD_PX / 2,
    )
  }, [m_per_px, city.ways, city.bounds_m, min_e_m, max_n_m, we, wn, wE, wN, width_m, height_m])

  return (
    <figure className="locator">
      <div ref={frameRef}>
        <svg viewBox={`0 0 ${width_m} ${height_m}`} role="img" aria-label={`The 2 km window within ${city.city}`}>
          <rect className="locator-bg" width={width_m} height={height_m} />
          {paths.map((p, i) => (
            <path key={i} className={`locator-${p.wayClass}`} d={p.d} />
          ))}
          <rect className="locator-window" x={we - min_e_m} y={max_n_m - wN} width={wE - we} height={wN - wn} />
          {labels.map((label) => (
            <text
              key={label.text}
              className="map-label"
              x={label.x * m_per_px}
              y={label.y * m_per_px}
              fontSize={LOCATOR_LABEL_FONT_PX * m_per_px}
              strokeWidth={LABEL_HALO_PX * m_per_px}
              textAnchor="middle"
              dominantBaseline="central"
            >
              {label.text}
            </text>
          ))}
        </svg>
      </div>
      <figcaption>
        {city.city}. Box: the 2 km window. Major roads and rivers from OpenStreetMap.
      </figcaption>
    </figure>
  )
}
