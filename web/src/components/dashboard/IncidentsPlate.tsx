import * as React from "react"

import { Plate } from "@/components/argos/Plate"
import { SnapshotPlaceholder } from "@/components/argos/SnapshotPlaceholder"
import type { Incident } from "@/data/contract"
import { endingLabel, formatClock, standDownLabel, triggerLabel } from "@/data/derive"

import { printSentence } from "./sentence"

const NUMERALS: readonly [number, string][] = [
  [1000, "M"],
  [900, "CM"],
  [500, "D"],
  [400, "CD"],
  [100, "C"],
  [90, "XC"],
  [50, "L"],
  [40, "XL"],
  [10, "X"],
  [9, "IX"],
  [5, "V"],
  [4, "IV"],
  [1, "I"],
]

function roman(n: number) {
  let out = ""
  for (const [value, numeral] of NUMERALS) {
    while (n >= value) {
      out += numeral
      n -= value
    }
  }
  return out
}

function howItEnded(incident: Incident, person: string) {
  if (incident.status === "stood_down") return standDownLabel(incident.stood_down_by, person)
  if (incident.status === "acknowledged") {
    const by = incident.acknowledged_by ?? "Someone"
    return incident.acknowledged_at ? `Acknowledged by ${by} at ${formatClock(incident.acknowledged_at)}` : `Acknowledged by ${by}`
  }
  return null
}

export interface IncidentsPlateProps {
  /** Newest first, as the role may see them. */
  incidents: readonly Incident[]
  person: string
  wrapClassName?: string
  /** Family, live: the stored picture. Absent means the placeholder, which is what the script uses. */
  renderSnapshot?: (path: string) => React.ReactNode
}

/** A ledger of checks. Each row opens to its times, how it ended, and its report. */
export function IncidentsPlate({ incidents, person, wrapClassName, renderSnapshot }: IncidentsPlateProps) {
  const [open, setOpen] = React.useState<string | null>(null)
  const idBase = React.useId()

  return (
    <Plate label="Incidents" wrapClassName={wrapClassName}>
      {incidents.length ? (
        <ul className="argos-ledger">
          {incidents.map((incident, i) => {
            const expanded = open === incident.id
            const detailId = `${idBase}-${incident.id}`
            const ended = howItEnded(incident, person)
            return (
              <li key={incident.id}>
                <button
                  type="button"
                  className="argos-ledger-row"
                  aria-expanded={expanded}
                  aria-controls={detailId}
                  onClick={() => setOpen(expanded ? null : incident.id)}
                >
                  <span className="argos-ledger-num">{roman(incidents.length - i)}.</span>
                  <span className="argos-ledger-title">{triggerLabel(incident.trigger)}</span>
                  <span className="argos-ledger-end">{endingLabel(incident, person)}</span>
                  <time className="argos-ledger-when argos-mono" dateTime={incident.started_at}>
                    {formatClock(incident.started_at)}
                  </time>
                  <span className="argos-ledger-plus" aria-hidden="true">
                    +
                  </span>
                </button>
                {expanded && (
                  <div className="argos-ledger-detail" id={detailId}>
                    <dl>
                      <dt>Started</dt>
                      <dd className="argos-mono">{formatClock(incident.started_at)}</dd>
                      {incident.ended_at && (
                        <>
                          <dt>Ended</dt>
                          <dd className="argos-mono">{formatClock(incident.ended_at)}</dd>
                        </>
                      )}
                      {ended && (
                        <>
                          <dt>How it ended</dt>
                          <dd>{ended}</dd>
                        </>
                      )}
                    </dl>
                    {incident.summary && <p className="argos-summary">{printSentence(incident.summary)}</p>}
                    {incident.snapshot_path &&
                      (renderSnapshot ? renderSnapshot(incident.snapshot_path) : <SnapshotPlaceholder />)}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="argos-empty">No checks yet.</p>
      )}
    </Plate>
  )
}
