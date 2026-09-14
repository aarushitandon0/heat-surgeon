import { Instance, Instances } from '@react-three/drei'
import { useEffect, useMemo } from 'react'
import { BufferAttribute, Color, CylinderGeometry, RingGeometry, SphereGeometry, type BufferGeometry } from 'three'
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js'
import type { DesignGrid, Intervention } from '../types/contracts.ts'
import { readSurfaceColor } from '../ui/tokens.ts'
import { interventionPositions, streetRotationY_rad, type SceneOrigin } from './frame.ts'

// The canopy is drawn at backend TREE_CROWN_DIAMETER_M (an ASSUMPTION logged in docs/methodology.md), the ground
// the model treats as shaded, so the drawn tree and the modelled shade are the same size. Trunk height and
// canopy depth are display only: a tall clear trunk and a shallow crown leave the cooled ground under the crown
// visible from the opening three-quarter view.
const TREE_CANOPY_DIAMETER_M = 8
const TREE_CANOPY_DEPTH_M = 2.2
const TREE_TRUNK_HEIGHT_M = 4
const TREE_TRUNK_RADIUS_M = 0.2
const MARKER_Y_M = 0.15
const COATED_OUTLINE_M = 0.2

interface InterventionMarkersProps {
  design: DesignGrid
  interventions: Intervention[]
  origin: SceneOrigin
}

/** Gives every vertex of a geometry one colour, so differently coloured parts merge into one draw call. */
function painted(geometry: BufferGeometry, color: Color): BufferGeometry {
  const count = geometry.getAttribute('position').count
  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) colors.set([color.r, color.g, color.b], i * 3)
  geometry.setAttribute('color', new BufferAttribute(colors, 3))
  return geometry
}

/**
 * Where the searched layout places each intervention, over the before-state ground.
 * One instanced draw call per intervention type, however many cells the layout uses.
 */
export function InterventionMarkers({ design, interventions, origin }: InterventionMarkersProps) {
  const positions = useMemo(() => interventionPositions(design, interventions, origin), [design, interventions, origin])
  const coatedColor = useMemo(() => readSurfaceColor('--paper-dim'), [])

  // Trunk and canopy, merged with per-vertex colour so trees stay one draw call.
  const tree = useMemo(() => {
    const paper = new Color(readSurfaceColor('--paper'))
    const paperDim = new Color(readSurfaceColor('--paper-dim'))
    const trunk = new CylinderGeometry(TREE_TRUNK_RADIUS_M, TREE_TRUNK_RADIUS_M, TREE_TRUNK_HEIGHT_M, 6)
    trunk.translate(0, TREE_TRUNK_HEIGHT_M / 2, 0)
    const canopy = new SphereGeometry(TREE_CANOPY_DIAMETER_M / 2, 20, 10)
    canopy.scale(1, TREE_CANOPY_DEPTH_M / TREE_CANOPY_DIAMETER_M, 1)
    canopy.translate(0, TREE_TRUNK_HEIGHT_M + TREE_CANOPY_DEPTH_M / 2 - TREE_TRUNK_RADIUS_M, 0)
    const parts = [painted(trunk, paperDim), painted(canopy, paper)]
    const merged = mergeGeometries(parts, false)
    parts.forEach((part) => part.dispose())
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
          <meshLambertMaterial vertexColors />
          {positions.trees.map(([x, z], i) => (
            <Instance key={i} position={[x, MARKER_Y_M, z]} />
          ))}
        </Instances>
      )}
      {positions.coated.length > 0 && (
        <Instances limit={positions.coated.length} range={positions.coated.length} geometry={square} frustumCulled={false}>
          <meshBasicMaterial color={coatedColor} />
          {positions.coated.map(([x, z], i) => (
            <Instance key={i} position={[x, MARKER_Y_M, z]} rotation={[0, rotationY, 0]} />
          ))}
        </Instances>
      )}
    </>
  )
}
