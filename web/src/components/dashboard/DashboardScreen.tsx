import * as React from "react"
import { useNavigate, useSearchParams } from "react-router"

import { useAuthClient, useSession } from "@/auth/context"
import { ROLE_NAMES } from "@/auth/types"
import { ArgosMark } from "@/components/argos/ArgosMark"
import { ArgosView } from "@/components/argos/ArgosView"
import { Chip } from "@/components/argos/Chip"
import { DevControls } from "@/components/argos/DevControls"
import type { InkState } from "@/components/argos/ink"
import { Meander } from "@/components/argos/Meander"
import { Wave } from "@/components/argos/Wave"
import { SnapshotPlaceholder } from "@/components/argos/SnapshotPlaceholder"
import { Button } from "@/components/ui/button"
import { useDashboardView, useDataSource } from "@/data/context"
import { displayState, formatClock, openIncident, stateSince, waitingIncident } from "@/data/derive"
import { useBeat, useNow } from "@/lib/hooks"

import { AcknowledgeBar } from "./AcknowledgeBar"
import { ClinicianPlates } from "./ClinicianPlates"
import { FamilyPlates } from "./FamilyPlates"
import { IncidentsPlate } from "./IncidentsPlate"
import { StatePlate } from "./StatePlate"
import { TimelinePlate } from "./TimelinePlate"

const VIEW_MESSAGE = "The live view opens for signed-in family."

/** The dashboard: everything on it comes from the data source, or is derived from it. */
export function DashboardScreen() {
  const session = useSession()
  const auth = useAuthClient()
  const source = useDataSource()
  const view = useDashboardView()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const dev = params.get("dev") === "1"
  const [override, setOverride] = React.useState<InkState | null>(null)
  const now = useNow(1000)
  const beat = useBeat(view.device?.last_seen_at)

  React.useEffect(() => {
    document.title = "Dashboard · Argos"
  }, [])

  if (!session) return null

  const dataState = displayState(view.device, now)
  const state = override ?? dataState
  const offline = dataState === "offline"
  const person = view.device?.person_label ?? ""
  const waiting = waitingIncident(view.incidents)
  const since = offline ? null : stateSince(view.device, view.incidents, view.events)
  const lastSeen = offline
    ? view.device
      ? `Last seen ${formatClock(view.device.last_seen_at)}`
      : "Argos has not reported yet."
    : undefined
  const snapshot =
    view.role === "family" && openIncident(view.incidents)?.snapshot_path ? <SnapshotPlaceholder tone="night" /> : undefined

  async function signOut() {
    await auth.signOut()
    navigate("/sign-in", { replace: true })
  }

  return (
    <div className="argos-dash" data-state={state} data-testid="dashboard">
      <header className="argos-dash-header">
        <span className="argos-dash-brand">
          <ArgosMark variant="lockup" size={118} label="Argos" />
        </span>
        <h1 className="argos-dash-watching">
          {person ? (
            <>
              Watching over <em>{person}</em>
            </>
          ) : (
            "Waiting for Argos"
          )}
        </h1>
        <div className="argos-dash-chips">
          <Chip>{ROLE_NAMES[session.role]}</Chip>
          {session.demo && <Chip>Demo</Chip>}
        </div>
        <Button variant="secondary" onClick={signOut}>
          Sign out
        </Button>
      </header>

      <div className="argos-dash-meander">
        <Meander beat={beat} flat={state === "offline"} />
      </div>

      <main className="argos-grid">
        <StatePlate
          wrapClassName="argos-area-state"
          state={state}
          since={since}
          lastSeen={view.device?.last_seen_at ?? null}
          now={now}
        />

        <div className="argos-centre">
          <ArgosView wrapClassName="argos-area-view" message={VIEW_MESSAGE} snapshot={snapshot} lastSeen={lastSeen} />
          {waiting && <AcknowledgeBar className="argos-area-ack" incident={waiting} onAcknowledge={source.acknowledge} />}
        </div>

        <TimelinePlate wrapClassName="argos-area-timeline" events={view.events} />
        <IncidentsPlate wrapClassName="argos-area-incidents" incidents={view.incidents} person={person} />

        {view.role === "clinician" ? (
          <ClinicianPlates readings={view.readings} />
        ) : (
          <FamilyPlates incidents={view.incidents} person={person} now={now} />
        )}
      </main>

      {dev && (
        <DevControls
          override={override}
          onOverride={setOverride}
          replay={
            source.replay && {
              speed: source.replay.getSpeed(),
              speeds: source.replay.speeds,
              onSpeed: source.replay.setSpeed,
              onRestart: source.replay.restart,
            }
          }
        />
      )}

      <Wave />
    </div>
  )
}
