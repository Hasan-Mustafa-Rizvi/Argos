import * as React from "react"
import { useNavigate, useSearchParams } from "react-router"

import { useAuthClient, useSession } from "@/auth/context"
import { ROLE_NAMES } from "@/auth/types"
import { ArgosMark } from "@/components/argos/ArgosMark"
import { ArgosView } from "@/components/argos/ArgosView"
import { FamilySnapshot } from "@/components/argos/FamilySnapshot"
import { LiveFrame } from "@/components/argos/LiveFrame"
import { useLiveFrames } from "@/components/argos/useLiveFrames"
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
  const familyLive = session?.kind === "ready" && session.role === "family"
  const frames = useLiveFrames(familyLive, familyLive ? session.deviceId : null, now)

  React.useEffect(() => {
    document.title = "Dashboard · Argos"
  }, [])

  if (!session || (session.kind !== "demo" && session.kind !== "ready")) return null

  const dataState = displayState(view.device, now)
  const state = override ?? dataState
  const offline = dataState === "offline"
  const person = view.device?.person_label ?? ""
  const waiting = waitingIncident(view.incidents)
  const since = offline ? null : stateSince(view.device, view.incidents, view.events)
  const stoppedFor =
    frames.phase === "stopped" && frames.receivedAt !== null ? Math.max(0, Math.round((now - frames.receivedAt) / 1000)) : null
  const lastSeen = offline
    ? !view.device || !view.device.last_seen_at
      ? "Argos has not reported yet."
      : `Last seen ${formatClock(view.device.last_seen_at)}`
    : undefined
  const viewMessage =
    session.kind === "demo"
      ? "The live view opens for signed-in family."
      : session.role === "clinician"
        ? "The live view is for family."
        : "The live view is off, or Argos is not sending."
  const openPath = view.role === "family" ? openIncident(view.incidents)?.snapshot_path : undefined
  const snapshot = openPath ? (
    view.source === "live" ? (
      <FamilySnapshot path={openPath} ink={state} surface="night" />
    ) : (
      <SnapshotPlaceholder tone="night" />
    )
  ) : undefined
  const picture = frames.frame ? (
    <LiveFrame frame={frames.frame} ink={state} live={frames.phase === "live"} stoppedFor={stoppedFor} />
  ) : undefined

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

      {view.notice && (
        <p className="argos-notice" role="status">
          {view.notice}
        </p>
      )}

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
          <ArgosView
            wrapClassName="argos-area-view"
            message={viewMessage}
            picture={picture}
            snapshot={snapshot}
            lastSeen={lastSeen}
            faded={frames.phase === "stopped"}
          />
          {waiting && <AcknowledgeBar className="argos-area-ack" incident={waiting} onAcknowledge={source.acknowledge} />}
        </div>

        <TimelinePlate wrapClassName="argos-area-timeline" events={view.events} />
        <IncidentsPlate
          wrapClassName="argos-area-incidents"
          incidents={view.incidents}
          person={person}
          renderSnapshot={
            view.role === "family" && view.source === "live"
              ? (path) => <FamilySnapshot path={path} ink={state} surface="paper" />
              : undefined
          }
        />

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
