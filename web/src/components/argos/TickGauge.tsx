export interface TickGaugeProps {
  value: number | null
  min: number
  max: number
  /** Read aloud in place of the ticks. */
  label: string
  ticks?: number
  /** Every this many ticks, a taller one. */
  major?: number
}

/** A row of tick marks, inked up to the value. */
export function TickGauge({ value, min, max, label, ticks = 30, major = 5 }: TickGaugeProps) {
  const share = value === null || max <= min ? 0 : Math.min(1, Math.max(0, (value - min) / (max - min)))
  const on = Math.round(share * ticks)
  return (
    <div className="argos-ticks" role="img" aria-label={label}>
      {Array.from({ length: ticks }, (_, i) => (
        <span key={i} data-on={i < on ? true : undefined} data-major={(i + 1) % major === 0 ? true : undefined} />
      ))}
    </div>
  )
}
