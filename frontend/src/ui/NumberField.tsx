import { useState } from 'react'

interface NumberFieldProps {
  label: string
  value: number
  min: number
  onChange: (value: number) => void
}

/** Integer input. The value is numeric, so it is set in mono; the label is not. */
export function NumberField({ label, value, min, onChange }: NumberFieldProps) {
  const [draft, setDraft] = useState<string | null>(null)
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        className="field-input mono"
        type="number"
        inputMode="numeric"
        min={min}
        step={1}
        value={draft ?? String(value)}
        onChange={(event) => {
          setDraft(event.target.value)
          const parsed = Number(event.target.value)
          if (event.target.value !== '' && Number.isInteger(parsed) && parsed >= min) onChange(parsed)
        }}
        onBlur={() => setDraft(null)}
      />
    </label>
  )
}
