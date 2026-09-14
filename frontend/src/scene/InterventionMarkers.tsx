import { Instance, Instances } from '@react-three/drei'
import { useEffect, useMemo } from 'react'
import { CylinderGeometry, RingGeometry } from 'three'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'
import type { DesignGrid, Intervention } from '../types/contracts.ts'
import { readSurfaceColor } from '../ui/tokens.ts'
import { interventionPositions, streetRotationY_rad, type SceneOrigin } from './frame.ts'

// Display sizes, not model inputs. The ring matches backend TREE_CROWN_DIAMETER_M (an ASSUMPTION logged in
// docs/methodology.md), so it outlines the ground the model treats as shaded without hiding the heat under it.
const TREE_CROWN_DIAMETER_M = 8
const TREE_RING_WIDTH_M = 0.3
const TREE_STAKE_HEIGHT_M = 6
const TREE_STAKE_RADIUS_M = 0.2
const MARKER_Y_M = 0.15
const COATED_OUTLINE_M = 0.2

interface InterventionMarkersProps {
  design: DesignGrid
  interventions: Intervention[]
  origin: SceneOrigin
}

/**
 * Where the searched layout places each intervention, as outline markers over the before-state ground.
 * One instanced draw call per intervention type, however many cells the layout uses.
 */
export function InterventionMarkers({ design, interventions, origin }: InterventionMarkersProps) {
  const positions = useMemo(() => interventionPositions(design, interventions, origin), [design, interventions, origin])
  const colors = useMemo(() => ({ tree: readSurfaceColor('--paper'), coated: readSurfaceColor('--paper-dim') }), [])

  // A stake at the planting position and a flat ring at crown extent, merged so trees stay one draw call.
  const tree = useMemo(() => {
    const ring = new RingGeometry(TREE_CROWN_DIAMETER_M / 2 - TREE_RING_WIDTH_M, TREE_CROWN_DIAMETER_M / 2, 48)
    ring.rotateX(-Math.PI / 2)
    const stake = new CylinderGeometry(TREE_STAKE_RADIUS_M, TREE_STAKE_RADIUS_M, TREE_STAKE_HEIGHT_M, 6)
    stake.translate(0, TREE_STAKE_HEIGHT_M / 2, 0)
    const merged = mergeGeometries([ring, stake], false)
    ring.dispose()
    stake.dispose()
    return merged
  }, [])
  // A four-segment ring is a square outline; starting at 45° puts its edges along the cell edges.
  const square = useMemo(() => {
    const outer_m = design.cell_size_m / Math.SQRT2
    const g = new RingGeometry(outer_m - COATED_OUTLINE_M * Math.SQRT2, outer_m, 4, 1, Math.PI / 4)
    g.rotateX(-Math.PI / 2)
    return g
  }, [design.cell_size_m])

  useEffect(() => () => tree.dispose(), [tree])
  useEffect(() => () => square.dispose(), [square])

  const rotationY = streetRotationY_rad(design)

  return (
    <>
      {positions.trees.length > 0 && (
        <Instances limit={positions.trees.length} range={positions.trees.length} geometry={tree} frustumCulled={false}>
          <meshBasicMaterial color={colors.tree} />
          {positions.trees.map(([x, z], i) => (
            <Instance key={i} position={[x, MARKER_Y_M, z]} />
          ))}
        </Instances>
      )}
      {positions.coated.length > 0 && (
        <Instances limit={positions.coated.length} range={positions.coated.length} geometry={square} frustumCulled={false}>
          <meshBasicMaterial color={colors.coated} />
          {positions.coated.map(([x, z], i) => (
            <Instance key={i} position={[x, MARKER_Y_M, z]} rotation={[0, rotationY, 0]} />
          ))}
        </Instances>
      )}
    </>
  )
}
