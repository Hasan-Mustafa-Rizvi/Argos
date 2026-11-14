export interface SparklineProps {
  values: readonly (number | null)[]
  /** Read aloud in place of the drawing. */
  label: string
  min?: number
  max?: number
}

const W = 100
const H = 32

/** A small inline drawing of a series, oldest on the left. */
export function Sparkline({ values, label, min, max }: SparklineProps) {
  const points = values.flatMap((v, i) => (v === null ? [] : [[i, v] as const]))
  if (points.length < 2) return <span className="argos-empty">Not enough readings yet.</span>
  const nums = points.map(([, v]) => v)
  const lo = min ?? Math.min(...nums)
  const hi = max ?? Math.max(...nums)
  const span = hi - lo || 1
  const last = Math.max(1, values.length - 1)
  const d = points
    .map(([i, v], k) => {
      const x = (i / last) * W
      const y = H - 2 - (Math.min(hi, Math.max(lo, v)) - lo) / span * (H - 4)
      return `${k ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(" ")
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}
