import type * as React from "react"

import { ArgosMark } from "./ArgosMark"
import { Plate } from "./Plate"

export interface ArgosViewProps {
  /** The line under the mark. */
  message: string
  /** What Argos's camera sees, once the live view is built. Replaces the mark and the message. */
  picture?: React.ReactNode
  /** The stored snapshot of an escalated incident, or its placeholder. Family only. */
  snapshot?: React.ReactNode
  /** Set when Argos has stopped reporting: the mark fades and this line says when it was last seen. */
  lastSeen?: string
  wrapClassName?: string
}

/** The night panel at the centre of the dashboard. */
export function ArgosView({ message, picture, snapshot, lastSeen, wrapClassName }: ArgosViewProps) {
  return (
    <Plate label="Argos's view" tone="night" primary wrapClassName={wrapClassName} className="argos-view">
      <div className="argos-view-body">
        {picture ? (
          <div className="argos-view-picture">{picture}</div>
        ) : (
          <>
            <span data-faded={lastSeen ? true : undefined} style={{ color: "var(--on-night)", display: "inline-flex" }}>
              <ArgosMark variant="mark" size="clamp(96px, 14vw, 160px)" />
            </span>
            <p className="argos-view-line">{message}</p>
            {lastSeen && <p className="argos-view-line argos-mono">{lastSeen}</p>}
          </>
        )}
        {snapshot}
      </div>
    </Plate>
  )
}
