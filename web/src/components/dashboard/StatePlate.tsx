import type { InkState } from "@/components/argos/ink"
import { Plate } from "@/components/argos/Plate"
import { StateWord } from "@/components/argos/StateWord"
import { formatAgo, formatClock } from "@/data/derive"

export interface StatePlateProps {
  state: InkState
  /** When the device entered this state, or null when the records do not say. */
  since: string | null
  /** The device's last report. */
  lastSeen: string | null
  now: number
  wrapClassName?: string
}

export function StatePlate({ state, since, lastSeen, now, wrapClassName }: StatePlateProps) {
  return (
    <Plate label="State" wrapClassName={wrapClassName}>
      <StateWord state={state} />
      <dl className="argos-meta">
        {since && state !== "offline" && (
          <div>
            <dt>Since</dt>
            <dd className="argos-mono">{formatClock(since)}</dd>
          </div>
        )}
        <div>
          <dt>Last report</dt>
          <dd className="argos-mono">{lastSeen ? `${formatClock(lastSeen)} · ${formatAgo(lastSeen, now)}` : "None yet"}</dd>
        </div>
      </dl>
    </Plate>
  )
}
