import { BufferGeometry, ExtrudeGeometry, Shape, Vector2 } from 'three'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'
import type { Building } from '../types/contracts.ts'
import { footprintShapePoints, ringArea_m2, type SceneOrigin } from './frame.ts'

/** One footprint extruded to its height, standing on y = 0. Null for a degenerate ring. */
export function buildingGeometry(building: Building, origin: SceneOrigin): BufferGeometry | null {
  const points = footprintShapePoints(building.footprint, origin)
  if (points.length < 3 || ringArea_m2(points) === 0) return null
  const shape = new Shape(points.map(([x, y]) => new Vector2(x, y)))
  const geometry = new ExtrudeGeometry(shape, { depth: building.height_m, bevelEnabled: false, steps: 1 })
  geometry.rotateX(-Math.PI / 2)
  return geometry
}

/** Every building merged into one geometry, so the whole block draws in a single call. */
export function mergedBuildings(buildings: Building[], origin: SceneOrigin): BufferGeometry | null {
  const parts = buildings.map((b) => buildingGeometry(b, origin)).filter((g): g is BufferGeometry => g !== null)
  if (parts.length === 0) return null
  const merged = mergeGeometries(parts, false)
  parts.forEach((part) => part.dispose())
  return merged
}
