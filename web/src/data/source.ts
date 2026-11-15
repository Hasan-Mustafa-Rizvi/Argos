import type { Role } from "@/auth/types"

import type { ClinicianIncident, Device, FamilyIncident, Reading, TimelineEvent } from "./contract"

export type SourceKind = "replay" | "live"

interface ViewBase {
  readonly source: SourceKind
  /** Null until the first device record arrives. */
  readonly device: Device | null
  /** Newest first. */
  readonly events: readonly TimelineEvent[]
  /** One plain line when the live backend cannot be reached. Replay is always null. */
  readonly notice: string | null
}

/** What a family session receives. There is no `readings` key at all. */
export interface FamilyView extends ViewBase {
  readonly role: "family"
  /** Newest first. */
  readonly incidents: readonly FamilyIncident[]
}

/** What a clinician session receives. Incidents never carry a snapshot path. */
export interface ClinicianView extends ViewBase {
  readonly role: "clinician"
  /** Newest first. */
  readonly incidents: readonly ClinicianIncident[]
  /** Oldest first. */
  readonly readings: readonly Reading[]
}

export type DashboardView = FamilyView | ClinicianView

export type AckResult = { readonly ok: true } | { readonly ok: false; readonly reason: string }

export interface ReplayControls {
  readonly speeds: readonly number[]
  getSpeed(): number
  /** Changes the speed and starts the run again from the top. */
  setSpeed(speed: number): void
  restart(): void
}

/**
 * The one data interface components read. The replay implementation is in replay.ts; a live
 * implementation can replace it in createDataSource without touching a component.
 */
export interface DataSource {
  readonly role: Role
  readonly kind: SourceKind
  getView(): DashboardView
  subscribe(listener: () => void): () => void
  /** The one write: acknowledge an escalated incident as this session. */
  acknowledge(incidentId: string): Promise<AckResult>
  start(): void
  stop(): void
  /** Present only on the replay. */
  readonly replay?: ReplayControls
}
