import { Grid as Graticule, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useMemo } from 'react'
import type { Domain } from '../lib/thermal.ts'
import type { OptimizationResult, StreetGeometry } from '../types/contracts.ts'
import { readSurfaceColor } from '../ui/tokens.ts'
import { Buildings } from './Buildings.tsx'
import { designGridCentre, graticuleOffset, threeQuarterPose, type ThreeQuarterView } from './frame.ts'
import { HeatGround } from './HeatGround.tsx'
import { InterventionMarkers } from './InterventionMarkers.tsx'

// The opening frame: from the right of the street, turned back towards its start and raised, so the
// segment runs diagonally across the view with buildings on both sides. Checked by eye on Bajirao Road,
// North Main Road and FC Road (2026-09-14); not yet on Karve Road.
const FIELD_OF_VIEW_DEG = 35
const OPENING_VIEW: Omit<ThreeQuarterView, 'distance_m'> = { azimuth_deg: 38, elevation_deg: 40 }
/** Opening distance as a multiple of the segment length. */
const OPENING_DISTANCE_PER_SEGMENT_LENGTH = 0.95

const GRATICULE_CELL_M = 10
const GRATICULE_SECTION_M = 50
const GRATICULE_Y_M = -0.05
const GRATICULE_FADE_M = 700

const MIN_DISTANCE_M = 25
const MAX_DISTANCE_M = 1500
/** 70° from straight down: never a grazing view along the ground plane. */
const MAX_POLAR_ANGLE_RAD = (70 * Math.PI) / 180

interface StreetSceneProps {
  result: OptimizationResult
  geometry: StreetGeometry
  domain: Domain
}

/** Before state only: modelled ground, real building footprints, the searched layout as markers. */
export function StreetScene({ result, geometry, domain }: StreetSceneProps) {
  const design = result.design_grid
  const origin = useMemo(() => designGridCentre(design), [design])
  const pose = useMemo(() => {
    const length_m = design.shape[0] * design.cell_size_m
    return threeQuarterPose(design, { ...OPENING_VIEW, distance_m: length_m * OPENING_DISTANCE_PER_SEGMENT_LENGTH })
  }, [design])
  const colors = useMemo(
    () => ({ base: readSurfaceColor('--base'), rule: readSurfaceColor('--rule'), paper: readSurfaceColor('--paper') }),
    [],
  )
  const [offsetX, offsetZ] = graticuleOffset(origin, GRATICULE_SECTION_M)

  return (
    <div className="scene-frame">
      <Canvas
        flat
        dpr={[1, 2]}
        camera={{ position: pose.position, fov: FIELD_OF_VIEW_DEG, near: 1, far: 6000 }}
        onCreated={({ gl }) => {
          // Development hook for the frame-rate measurement in docs/methodology.md.
          if (import.meta.env.DEV) Object.assign(window, { __heatSurgeonRenderer: gl })
        }}
      >
        <color attach="background" args={[colors.base]} />
        <hemisphereLight args={[colors.paper, colors.base, 1.1]} />
        <directionalLight position={[-220, 320, 160]} intensity={1.6} color={colors.paper} />
        <Graticule
          position={[offsetX, GRATICULE_Y_M, offsetZ]}
          args={[1, 1]}
          infiniteGrid
          cellSize={GRATICULE_CELL_M}
          sectionSize={GRATICULE_SECTION_M}
          cellThickness={0.5}
          sectionThickness={1}
          cellColor={colors.rule}
          sectionColor={colors.rule}
          fadeDistance={GRATICULE_FADE_M}
          followCamera={false}
        />
        <HeatGround grid={result.before_lst_c} design={design} origin={origin} domain={domain} />
        <Buildings buildings={geometry.buildings} origin={origin} />
        <InterventionMarkers design={design} interventions={result.interventions} origin={origin} />
        <OrbitControls
          makeDefault
          target={pose.target}
          enableDamping
          minDistance={MIN_DISTANCE_M}
          maxDistance={MAX_DISTANCE_M}
          maxPolarAngle={MAX_POLAR_ANGLE_RAD}
        />
      </Canvas>
    </div>
  )
}
