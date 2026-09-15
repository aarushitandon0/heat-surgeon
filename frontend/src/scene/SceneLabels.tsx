import { useFrame, type RootState } from '@react-three/fiber'
import { useMemo, useRef, type MutableRefObject } from 'react'
import { Matrix4, Raycaster, Vector3, type Object3D } from 'three'
import { boxesOverlap, rotatedBox, uprightAngle, type Box } from '../lib/labels.ts'
import type { SceneLabel } from '../lib/sceneLabels.ts'
import { BUILDING_FACES_NAME } from './Buildings.tsx'
import { utmToScene, type SceneOrigin } from './frame.ts'

/** Road names float just above the ground. Display only. */
const ROAD_LABEL_Y_M = 1.5
/** A name on a drawn building sits this far above its roof; a place not inside one sits at head height. */
const ROOF_CLEARANCE_M = 2
const STREET_LEVEL_PLACE_Y_M = 3
const LABEL_PAD_PX = 4
const EDGE_PX = 4
/** A building face closer to the camera than the label by more than this hides the label. */
const OCCLUSION_TOLERANCE_M = 1

export type LabelElements = MutableRefObject<(HTMLSpanElement | null)[]>

/** The label text, as HTML over the canvas, so it uses the body face and needs no font download. */
export function SceneLabelLayer({ labels, elements }: { labels: SceneLabel[]; elements: LabelElements }) {
  return (
    <div className="scene-labels">
      {labels.map((label, i) => (
        <span
          key={`${label.kind}-${label.text}`}
          ref={(el) => {
            elements.current[i] = el
          }}
          className={`scene-label scene-label-${label.kind}`}
        >
          {label.text}
        </span>
      ))}
    </div>
  )
}

/**
 * Inside the canvas: whenever the camera moves, projects each label to the screen, turns road names to follow their
 * road (never upside down), and hides any label that would leave the frame, collide with one placed before it, or sit
 * behind a building. Labels arrive most important first, so the street's own name always wins a collision.
 */
export function SceneLabelProjector({ labels, origin, elements }: { labels: SceneLabel[]; origin: SceneOrigin; elements: LabelElements }) {
  const world = useMemo(
    () =>
      labels.map((label) =>
        label.candidates.map((candidate) => {
          const y =
            candidate.height_m !== null
              ? candidate.height_m + ROOF_CLEARANCE_M
              : label.kind === 'place'
                ? STREET_LEVEL_PLACE_Y_M
                : ROAD_LABEL_Y_M
          const [x, z] = utmToScene(origin, ...candidate.anchor)
          const toward = candidate.toward ? utmToScene(origin, ...candidate.toward) : null
          return { at: new Vector3(x, y, z), toward: toward ? new Vector3(toward[0], y, toward[1]) : null }
        }),
      ),
    [labels, origin],
  )
  const last = useRef({ matrix: new Matrix4(), width: 0, height: 0, world: null as unknown, blockers: null as Object3D | null })
  const scratch = useRef({ a: new Vector3(), b: new Vector3(), dir: new Vector3(), ray: new Raycaster() })

  useFrame(({ camera, size, scene }: RootState) => {
    const blockers = scene.getObjectByName(BUILDING_FACES_NAME) ?? null
    const seen = last.current
    if (
      seen.world === world &&
      seen.blockers === blockers &&
      seen.width === size.width &&
      seen.height === size.height &&
      seen.matrix.equals(camera.matrixWorld)
    )
      return
    seen.matrix.copy(camera.matrixWorld)
    seen.width = size.width
    seen.height = size.height
    seen.world = world
    seen.blockers = blockers

    const { a, b, dir, ray } = scratch.current
    const hidden = (at: Vector3) => {
      if (!blockers) return false
      dir.copy(at).sub(camera.position)
      const distance_m = dir.length()
      ray.set(camera.position, dir.normalize())
      ray.far = Math.max(0, distance_m - OCCLUSION_TOLERANCE_M)
      return ray.intersectObject(blockers, false).length > 0
    }

    const placed: Box[] = []
    world.forEach((candidates, i) => {
      const el = elements.current[i]
      if (!el) return
      // Measured on every pass: a web font can finish loading after the first, and a stale width lets labels overlap.
      const dims = { w: el.offsetWidth, h: el.offsetHeight }
      for (const point of candidates) {
        a.copy(point.at).project(camera)
        if (a.z > 1) continue
        const x = ((a.x + 1) / 2) * size.width
        const y = ((1 - a.y) / 2) * size.height
        let angle_rad = 0
        if (point.toward) {
          b.copy(point.toward).project(camera)
          angle_rad = uprightAngle(Math.atan2(((1 - b.y) / 2) * size.height - y, ((b.x + 1) / 2) * size.width - x))
        }
        const box = rotatedBox(x, y, dims.w, dims.h, angle_rad, LABEL_PAD_PX)
        const outside = box.x < EDGE_PX || box.y < EDGE_PX || box.x + box.w > size.width - EDGE_PX || box.y + box.h > size.height - EDGE_PX
        if (outside || placed.some((other) => boxesOverlap(box, other)) || hidden(point.at)) continue
        placed.push(box)
        el.style.visibility = 'visible'
        el.style.transform = `translate(${x}px, ${y}px) rotate(${angle_rad}rad) translate(-50%, -50%)`
        return
      }
      el.style.visibility = 'hidden'
    })
  })
  return null
}
