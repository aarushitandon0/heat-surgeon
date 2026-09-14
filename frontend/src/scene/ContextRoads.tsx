import { useEffect, useMemo } from 'react'
import { BufferGeometry, Float32BufferAttribute } from 'three'
import { roadWeight } from '../lib/basemap.ts'
import type { BasemapWay } from '../types/contracts.ts'
import { readSurfaceColor } from '../ui/tokens.ts'
import { utmToScene, type SceneOrigin } from './frame.ts'

/** Just above the heat ground (0.05 m), below every marker. */
const ROAD_Y_M = 0.12
const ROAD_OPACITY = 0.5

/** OpenStreetMap road centrelines on the ground, as one draw call, so the names have streets to sit on. Context only. */
export function ContextRoads({ roads, origin, radius_m }: { roads: BasemapWay[]; origin: SceneOrigin; radius_m: number }) {
  const geometry = useMemo(() => {
    const positions: number[] = []
    for (const way of roads) {
      if (roadWeight(way.kind) === 'path') continue
      const points = way.path.map(([e, n]) => utmToScene(origin, e, n))
      if (!points.some(([x, z]) => Math.hypot(x, z) <= radius_m)) continue
      for (let i = 1; i < points.length; i++) {
        positions.push(points[i - 1][0], ROAD_Y_M, points[i - 1][1], points[i][0], ROAD_Y_M, points[i][1])
      }
    }
    const g = new BufferGeometry()
    g.setAttribute('position', new Float32BufferAttribute(positions, 3))
    return g
  }, [roads, origin, radius_m])
  const color = useMemo(() => readSurfaceColor('--paper-dim'), [])

  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={color} transparent opacity={ROAD_OPACITY} depthWrite={false} />
    </lineSegments>
  )
}
