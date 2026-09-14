import { useEffect, useMemo } from 'react'
import { EdgesGeometry } from 'three'
import type { Building } from '../types/contracts.ts'
import { readSurfaceColor } from '../ui/tokens.ts'
import { mergedBuildings } from './buildingGeometry.ts'
import type { SceneOrigin } from './frame.ts'

/** Edges sharper than this are outlined, so walls and roof lines read without every triangle seam. */
const EDGE_THRESHOLD_DEG = 20

/** Context, not data: surface colours only. Two draw calls for every building: faces and outlines. */
export function Buildings({ buildings, origin }: { buildings: Building[]; origin: SceneOrigin }) {
  const faces = useMemo(() => mergedBuildings(buildings, origin), [buildings, origin])
  const edges = useMemo(() => (faces ? new EdgesGeometry(faces, EDGE_THRESHOLD_DEG) : null), [faces])
  const colors = useMemo(() => ({ face: readSurfaceColor('--rule'), edge: readSurfaceColor('--paper-dim') }), [])

  useEffect(() => () => faces?.dispose(), [faces])
  useEffect(() => () => edges?.dispose(), [edges])

  if (!faces || !edges) return null
  return (
    <group>
      <mesh geometry={faces}>
        <meshLambertMaterial color={colors.face} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={colors.edge} />
      </lineSegments>
    </group>
  )
}
