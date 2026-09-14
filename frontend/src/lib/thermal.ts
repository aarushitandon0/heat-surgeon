// Mapping surface temperature grids onto the five-stop thermal ramp. Pure functions; the ramp
// colours themselves are read from tokens.css at runtime (src/ui/tokens.ts).

export type RGB = readonly [number, number, number]
export type Grid = (number | null)[][]

export interface Domain {
  min_c: number
  max_c: number
}

/** "#rrggbb" or "#rgb" as written in tokens.css. */
export function parseHexColor(value: string): RGB {
  const hex = value.trim().replace(/^#/, '')
  const full = hex.length === 3 ? [...hex].map((ch) => ch + ch).join('') : hex
  if (!/^[0-9a-fA-F]{6}$/.test(full)) throw new Error(`Not a hex colour: ${value}`)
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) as unknown as RGB
}

/** Linear interpolation along evenly spaced stops; t is clamped to [0, 1]. */
export function rampColor(stops: readonly RGB[], t: number): RGB {
  const clamped = Math.min(1, Math.max(0, t))
  const segments = stops.length - 1
  const position = clamped * segments
  const i = Math.min(segments - 1, Math.floor(position))
  const f = position - i
  const a = stops[i]
  const b = stops[i + 1]
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ]
}

/** Position of a temperature in the domain, 0 at min_c and 1 at max_c. A zero-width domain maps to the middle. */
export function normalise(value_c: number, domain: Domain): number {
  const span_c = domain.max_c - domain.min_c
  return span_c === 0 ? 0.5 : (value_c - domain.min_c) / span_c
}

/** Min and max over every non-null cell of every grid, so grids drawn side by side share one scale. */
export function gridDomain(...grids: Grid[]): Domain | null {
  let min_c = Infinity
  let max_c = -Infinity
  for (const grid of grids) {
    for (const row of grid) {
      for (const value of row) {
        if (value === null) continue
        if (value < min_c) min_c = value
        if (value > max_c) max_c = value
      }
    }
  }
  return min_c === Infinity ? null : { min_c, max_c }
}

/** Cell-wise interpolation; null wherever either grid is null. */
export function lerpGrid(from: Grid, to: Grid, t: number): Grid {
  return from.map((row, r) =>
    row.map((a, c) => {
      const b = to[r]?.[c] ?? null
      return a === null || b === null ? null : a + (b - a) * t
    }),
  )
}

export function hasNull(grid: Grid): boolean {
  return grid.some((row) => row.some((value) => value === null))
}

/** RGBA bytes, row-major, one pixel per cell. Null cells are fully transparent. */
export function paintGrid(grid: Grid, domain: Domain, stops: readonly RGB[]): Uint8ClampedArray<ArrayBuffer> {
  const rows = grid.length
  const cols = rows === 0 ? 0 : grid[0].length
  const bytes = new Uint8ClampedArray(rows * cols * 4)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const value = grid[r][c]
      if (value === null) continue
      const [red, green, blue] = rampColor(stops, normalise(value, domain))
      const i = (r * cols + c) * 4
      bytes[i] = red
      bytes[i + 1] = green
      bytes[i + 2] = blue
      bytes[i + 3] = 255
    }
  }
  return bytes
}
