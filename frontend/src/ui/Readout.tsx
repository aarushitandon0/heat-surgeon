import type { ReactNode } from 'react'

interface ReadoutProps {
  /** Sentence-case label, always in the body face. */
  label: ReactNode
  value: ReactNode
  unit?: string
  /** 'numeric' sets the value in mono. Text values (a compositing method, a collection ID) stay in the body face. */
  kind?: 'numeric' | 'text'
  note?: ReactNode
  size?: 'md' | 'lg'
}

/** A label and its value. Place inside a <dl className="readouts">. */
export function Readout({ label, value, unit, kind = 'numeric', note, size = 'md' }: ReadoutProps) {
  return (
    <div className={`readout readout-${size}`}>
      <dt className="readout-label">{label}</dt>
      <dd className="readout-body">
        <span className={kind === 'numeric' ? 'readout-value mono' : 'readout-value'}>
          {value}
          {unit && <span className="readout-unit">{` ${unit}`}</span>}
        </span>
        {note && <span className="readout-note">{note}</span>}
      </dd>
    </div>
  )
}
