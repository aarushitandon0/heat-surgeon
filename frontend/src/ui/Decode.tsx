import { useEffect, useRef, useState } from 'react'
import { DECODE_SCRAMBLE_INTERVAL_MS, lockedChars } from '../lib/motion.ts'
import { usePrefersReducedMotion } from './hooks.ts'

interface DecodeProps {
  /** The resolved value, or null while the real fetch is still pending. */
  text: string | null
  /** Scrambled width while pending. */
  placeholderLength?: number
  /** Start resolving this long after the text arrives, so a stack resolves in sequence. */
  delayMs?: number
  mono?: boolean
  /**
   * Resolve even if the text is already present at mount. Set when the parent saw the fetch pending, so a
   * row that first appears with the data still decodes. Without it, remounting on data already loaded
   * shows the final text at once: the decode never replays without a real fetch behind it.
   */
  decodeOnMount?: boolean
}

// No digits in either set: a pending readout must never show something that reads as a real number.
const NUMERIC_GLYPHS = '%&*+=?/<>'
const TEXT_GLYPHS = 'abcdefghjkmnpqrstuvwxyz-'

function randomGlyph(glyphs: string): string {
  return glyphs[Math.floor(Math.random() * glyphs.length)]
}

/** The first `locked` characters final, the rest scrambled; spaces stay spaces. */
function resolving(text: string, locked: number, glyphs: string): string {
  return [...text].map((ch, i) => (i < locked || ch === ' ' ? ch : randomGlyph(glyphs))).join('')
}

/**
 * Scramble while the fetch is pending, then resolve character by character. The scramble lasts exactly as
 * long as the request; nothing waits on a fixed timer before data exists.
 */
export function Decode({ text, placeholderLength = 8, delayMs = 0, mono = false, decodeOnMount = false }: DecodeProps) {
  const reduced = usePrefersReducedMotion()
  const glyphs = mono ? NUMERIC_GLYPHS : TEXT_GLYPHS
  const [shown, setShown] = useState(() => (text !== null && !decodeOnMount ? text : ''))
  const sawPending = useRef(text === null || decodeOnMount)

  useEffect(() => {
    if (reduced) return
    let timer: number | null = null
    let raf: number | null = null

    if (text === null) {
      sawPending.current = true
      const refresh = () => setShown(resolving('x'.repeat(placeholderLength), 0, glyphs))
      raf = requestAnimationFrame(refresh)
      timer = window.setInterval(refresh, DECODE_SCRAMBLE_INTERVAL_MS)
    } else if (sawPending.current) {
      const start_ms = performance.now() + delayMs
      const tick = (now_ms: number) => {
        const locked = lockedChars(now_ms - start_ms, text.length)
        setShown(resolving(text, locked, glyphs))
        raf = locked < text.length ? requestAnimationFrame(tick) : null
      }
      raf = requestAnimationFrame(tick)
    }

    return () => {
      if (timer !== null) window.clearInterval(timer)
      if (raf !== null) cancelAnimationFrame(raf)
    }
  }, [text, delayMs, reduced, placeholderLength, glyphs])

  const className = mono ? 'decode mono' : 'decode'

  if (text === null) {
    return (
      <span className={`${className} decode-pending`} aria-busy="true">
        <span aria-hidden="true">{reduced ? '—' : shown}</span>
        <span className="visually-hidden">Acquiring</span>
      </span>
    )
  }

  return (
    <span className={className}>
      <span aria-hidden="true">{reduced ? text : shown}</span>
      <span className="visually-hidden">{text}</span>
    </span>
  )
}
