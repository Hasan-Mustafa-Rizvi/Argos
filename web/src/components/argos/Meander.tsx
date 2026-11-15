import { cn } from "@/lib/utils"
import { usePrefersReducedMotion } from "@/lib/hooks"

export interface MeanderProps {
  /** Counts heartbeats. Each new value steps the key forward one unit. */
  beat: number
  /** Flat when Argos is offline: no heartbeat to show. */
  flat?: boolean
  className?: string
}

/** The Greek key under the header. It steps once per heartbeat. */
export function Meander({ beat, flat, className }: MeanderProps) {
  const still = usePrefersReducedMotion()
  return (
    <div
      className={cn("argos-meander argos-fade", className)}
      data-flat={flat || undefined}
      style={{ ["--beat" as string]: still ? 0 : beat }}
      aria-hidden="true"
    >
      <div className="argos-meander-key" />
      <div className="argos-meander-flat" />
    </div>
  )
}
