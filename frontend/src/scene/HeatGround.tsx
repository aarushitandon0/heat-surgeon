import { useEffect, useMemo } from 'react'
import { BufferAttribute, BufferGeometry, DataTexture, DoubleSide, FloatType, NearestFilter, RGFormat, Vector3 } from 'three'
import type { Domain, Grid } from '../lib/thermal.ts'
import type { DesignGrid } from '../types/contracts.ts'
import { readThermalRamp } from '../ui/tokens.ts'
import { groundQuad, packHeatTexture, type SceneOrigin } from './frame.ts'

/** Lifted clear of the graticule underneath, below every marker. */
const GROUND_Y_M = 0.05

const vertexShader = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

// Same piecewise-linear ramp as src/lib/thermal.ts rampColor, so 2D and 3D colours agree. Output is the
// token's sRGB value untouched: no tone mapping or colour space chunk is included.
const fragmentShader = /* glsl */ `
uniform sampler2D uHeat;
uniform float uMinC;
uniform float uMaxC;
uniform vec3 uStops[5];
varying vec2 vUv;

vec3 ramp(float t) {
  float position = clamp(t, 0.0, 1.0) * 4.0;
  int i = int(min(floor(position), 3.0));
  return mix(uStops[i], uStops[i + 1], position - float(i));
}

void main() {
  vec4 texel = texture2D(uHeat, vUv);
  if (texel.g < 0.5) discard;
  float span_c = uMaxC - uMinC;
  float t = span_c > 0.0 ? (texel.r - uMinC) / span_c : 0.5;
  gl_FragColor = vec4(ramp(t), 1.0);
}
`

interface HeatGroundProps {
  grid: Grid
  design: DesignGrid
  origin: SceneOrigin
  domain: Domain
}

/** Modelled surface temperature on the design grid, one texel per 2 m cell, drawn through the thermal ramp. */
export function HeatGround({ grid, design, origin, domain }: HeatGroundProps) {
  const [rows, cols] = design.shape

  const texture = useMemo(() => {
    const t = new DataTexture(packHeatTexture(grid), cols, rows, RGFormat, FloatType)
    t.magFilter = NearestFilter
    t.minFilter = NearestFilter
    t.needsUpdate = true
    return t
  }, [grid, rows, cols])

  const geometry = useMemo(() => {
    const { positions, uvs } = groundQuad(design, origin, GROUND_Y_M)
    const g = new BufferGeometry()
    g.setAttribute('position', new BufferAttribute(positions, 3))
    g.setAttribute('uv', new BufferAttribute(uvs, 2))
    g.setIndex([0, 1, 2, 0, 2, 3])
    return g
  }, [design, origin])

  const uniforms = useMemo(
    () => ({
      uHeat: { value: texture },
      uMinC: { value: domain.min_c },
      uMaxC: { value: domain.max_c },
      uStops: { value: readThermalRamp().map(([r, g, b]) => new Vector3(r / 255, g / 255, b / 255)) },
    }),
    [texture, domain],
  )

  useEffect(() => () => texture.dispose(), [texture])
  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    <mesh geometry={geometry}>
      <shaderMaterial vertexShader={vertexShader} fragmentShader={fragmentShader} uniforms={uniforms} side={DoubleSide} />
    </mesh>
  )
}
