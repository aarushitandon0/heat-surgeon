import { useCallback, useEffect, useRef, useState } from 'react'
import { REVEAL_DURATION_MS, easeInOutCubic } from '../lib/motion.ts'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia(REDUCED_MOTION_QUERY).matches)
  useEffect(() => {
    const query = window.matchMedia(REDUCED_MOTION_QUERY)
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}

/**
 * Eased progress for the stage 03 reveal. play() runs 0 to 1 over REVEAL_DURATION_MS; with reduced
 * motion it jumps straight to 1.
 */
export function useReveal(): { progress: number; play: () => void } {
  const reduced = usePrefersReducedMotion()
  const [progress, setProgress] = useState(0)
  const frame = useRef<number | null>(null)

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  const play = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    if (reduced) {
      setProgress(1)
      return
    }
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / REVEAL_DURATION_MS)
      setProgress(easeInOutCubic(t))
      frame.current = t < 1 ? requestAnimationFrame(tick) : null
    }
    frame.current = requestAnimationFrame(tick)
  }, [reduced])

  return { progress, play }
}

export function useElementSize<T extends HTMLElement>(): [React.RefObject<T>, { width_px: number; height_px: number }] {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width_px: 0, height_px: 0 })
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width_px: Math.floor(width), height_px: Math.floor(height) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, size]
}
