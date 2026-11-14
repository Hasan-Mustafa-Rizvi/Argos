import * as React from "react"

import { Button } from "@/components/ui/button"
import type { Incident } from "@/data/contract"
import { formatClock, triggerLabel } from "@/data/derive"
import type { AckResult } from "@/data/source"

import { printSentence } from "./sentence"

export interface AcknowledgeBarProps {
  incident: Incident
  onAcknowledge: (incidentId: string) => Promise<AckResult>
  className?: string
}

/** Shown only while an escalated incident waits. Its button is the dashboard's only primary one. */
export function AcknowledgeBar({ incident, onAcknowledge, className }: AcknowledgeBarProps) {
  const headingId = React.useId()
  const [busy, setBusy] = React.useState(false)
  const [problem, setProblem] = React.useState("")

  async function acknowledge() {
    setBusy(true)
    const result = await onAcknowledge(incident.id)
    setBusy(false)
    if (!result.ok) setProblem(result.reason)
  }

  return (
    <section className={["argos-ack", className].filter(Boolean).join(" ")} aria-labelledby={headingId}>
      <div className="argos-ack-text">
        <h2 className="argos-label" id={headingId}>
          Waiting for someone to acknowledge
        </h2>
        <p>
          <b>{triggerLabel(incident.trigger)}</b> at <span className="argos-mono">{formatClock(incident.started_at)}</span>. No
          answer came.
        </p>
        {incident.summary && <p className="argos-summary">{printSentence(incident.summary)}</p>}
        {problem && <p role="alert">{problem}</p>}
      </div>
      <Button onClick={acknowledge} disabled={busy}>
        Acknowledge
      </Button>
    </section>
  )
}
