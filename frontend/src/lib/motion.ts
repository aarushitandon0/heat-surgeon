// The app has exactly two motion moments (SPEC.md §9.7): the acquisition decode in stage 01 and the
// before-to-after reveal in stage 03. Their timing lives here and nowhere else.

/** The reveal: heat grid interpolation and delta count share this duration and easing so they land together. */
export const REVEAL_DURATION_MS = 1500

/** Decode: scramble refresh while the fetch is pending. */
export const DECODE_SCRAMBLE_INTERVAL_MS = 45
/** Decode: after the data arrives, each character locks this long after the previous one. */
export const DECODE_CHAR_MS = 16
/** Decode: each row of the provenance stack starts resolving this long after the row above. */
export const DECODE_ROW_STAGGER_MS = 90

export function easeInOutCubic(t: number): number {
  const x = Math.min(1, Math.max(0, t))
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2
}

/** Characters that have locked to their final value, given time since the row started resolving. */
export function lockedChars(elapsed_ms: number, length: number): number {
  if (elapsed_ms < 0) return 0
  return Math.min(length, Math.floor(elapsed_ms / DECODE_CHAR_MS) + 1)
}
