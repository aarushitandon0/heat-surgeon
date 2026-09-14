import { useMemo } from 'react'
import { cityWayClass, svgPathData } from '../lib/basemap.ts'
import type { CityLocator } from '../types/contracts.ts'

interface CityLocatorMapProps {
  city: CityLocator
  /** [min_e, min_n, max_e, max_n] of the 2 km window, in metres, in the same crs as the city ways. */
  window_bounds_m: [number, number, number, number]
}

/** Static inset: the city's major roads and rivers from OpenStreetMap, with the 2 km window boxed. */
export function CityLocatorMap({ city, window_bounds_m }: CityLocatorMapProps) {
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
  return (
    <figure className="locator">
      <svg viewBox={`0 0 ${width_m} ${height_m}`} role="img" aria-label={`The 2 km window within ${city.city}`}>
        <rect className="locator-bg" width={width_m} height={height_m} />
        {paths.map((p, i) => (
          <path key={i} className={`locator-${p.wayClass}`} d={p.d} />
        ))}
        <rect className="locator-window" x={we - min_e_m} y={max_n_m - wN} width={wE - we} height={wN - wn} />
      </svg>
      <figcaption>
        {city.city}. Box: the 2 km window. Major roads and rivers from OpenStreetMap.
      </figcaption>
    </figure>
  )
}
