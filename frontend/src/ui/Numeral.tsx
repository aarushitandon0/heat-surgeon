import { useEffect } from 'react'
import { formatNumber, formatSigned } from '../lib/format.ts'
import { useReveal } from './hooks.ts'

interface NumeralProps {
  value: number
  decimals: number
  /** Where the count starts. */
  from?: number
  /** Explicit plus on positive values. */
  signed?: boolean
  /**
   * Eased progress from a shared reveal, so the count lands with whatever it accompanies. Without it the
   * numeral runs its own count once per value. Reduced motion shows the final value either way.
   */
  progress?: number
  className?: string
}

/** A counting numeric value, in mono. Used only for the stage 03 delta; every other number is static. */
export function Numeral({ value, decimals, from = 0, signed = false, progress, className }: NumeralProps) {
  const own = useReveal()
  const { play } = own
  const controlled = progress !== undefined

  useEffect(() => {
    if (!controlled) play()
  }, [controlled, value, play])

  const t = controlled ? progress : own.progress
  const format = signed ? formatSigned : formatNumber
  const shown = format(from + (value - from) * t, decimals)
  const final = format(value, decimals)

  return (
    <span className={['mono', className].filter(Boolean).join(' ')}>
      <span aria-hidden="true">{shown}</span>
      <span className="visually-hidden">{final}</span>
    </span>
  )
}
