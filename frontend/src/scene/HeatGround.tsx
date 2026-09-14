import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import {
  BufferAttribute,
  BufferGeometry,
  DataTexture,
  DoubleSide,
  FloatType,
  NearestFilter,
  RGBAFormat,
  Vector3,
  type ShaderMaterial,
} from 'three'
import type { Domain, Grid } from '../lib/thermal.ts'
import type { DesignGrid } from '../types/contracts.ts'
import { readThermalRamp } from '../ui/tokens.ts'
import { groundQuad, packRevealTexture, type SceneOrigin } from './frame.ts'

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
// The reveal interpolates each cell's temperature, not its colour: the same as lerpGrid in the 2D grid.
const fragmentShader = /* glsl */ `
uniform sampler2D uHeat;
uniform float uProgress;
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
  if (texel.b < 0.5) discard;
  float value_c = mix(texel.r, texel.g, uProgress);
  float span_c = uMaxC - uMinC;
  float t = span_c > 0.0 ? (value_c - uMinC) / span_c : 0.5;
  gl_FragColor = vec4(ramp(t), 1.0);
}
`

interface HeatGroundProps {
  before: Grid
  after: Grid
  /** 0 draws before, 1 draws after; in between is the reveal, driven by the one shared reveal clock. */
  progress: number
  design: DesignGrid
  origin: SceneOrigin
  domain: Domain
}

/**
 * Modelled surface temperature on the design grid, one texel per 2 m cell, drawn through the thermal ramp.
 * Before and after are uploaded once; the reveal only changes a uniform.
 */
export function HeatGround({ before, after, progress, design, origin, domain }: HeatGroundProps) {
  const [rows, cols] = design.shape

  const texture = useMemo(() => {
    const t = new DataTexture(packRevealTexture(before, after), cols, rows, RGBAFormat, FloatType)
    t.magFilter = NearestFilter
    t.minFilter = NearestFilter
    t.needsUpdate = true
    return t
  }, [before, after, rows, cols])

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
      uProgress: { value: 0 },
      uMinC: { value: domain.min_c },
      uMaxC: { value: domain.max_c },
      uStops: { value: readThermalRamp().map(([r, g, b]) => new Vector3(r / 255, g / 255, b / 255)) },
    }),
    [texture, domain],
  )
  // The latest committed progress, written to the uniform just before each frame is drawn, so the ground and the
  // numeral committed in the same render land on the same frame.
  const progressRef = useRef(progress)
  const material = useRef<ShaderMaterial>(null)
  useEffect(() => {
    progressRef.current = progress
  }, [progress])
  useFrame(() => {
    if (material.current) material.current.uniforms.uProgress.value = progressRef.current
  })

  useEffect(() => () => texture.dispose(), [texture])
  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    <mesh geometry={geometry}>
      <shaderMaterial ref={material} vertexShader={vertexShader} fragmentShader={fragmentShader} uniforms={uniforms} side={DoubleSide} />
    </mesh>
  )
}
