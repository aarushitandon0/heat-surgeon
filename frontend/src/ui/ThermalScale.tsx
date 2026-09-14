import { TEMP_DECIMALS, formatNumber } from '../lib/format.ts'
import type { Domain } from '../lib/thermal.ts'
import './ThermalScale.css'

interface ThermalScaleProps {
  domain: Domain
  /** What the colours encode, including whether it is measured or modelled. */
  caption: string
  /** The opacity the grid is drawn at, so the key's colours match the map's. */
  opacity?: number
}

/** The five-stop thermal ramp legend. The ramp is only ever a key to measured or modelled data. */
export function ThermalScale({ domain, caption, opacity = 1 }: ThermalScaleProps) {
  const mid_c = (domain.min_c + domain.max_c) / 2
  return (
    <figure className="thermal-scale">
      <div className="thermal-scale-bar" style={{ opacity }} aria-hidden="true" />
      <div className="thermal-scale-ticks">
        <span className="mono">{formatNumber(domain.min_c, TEMP_DECIMALS)} °C</span>
        <span className="mono">{formatNumber(mid_c, TEMP_DECIMALS)}</span>
        <span className="mono">{formatNumber(domain.max_c, TEMP_DECIMALS)} °C</span>
      </div>
      <figcaption className="thermal-scale-caption">{caption}</figcaption>
    </figure>
  )
}
