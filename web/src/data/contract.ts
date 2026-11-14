/*
 * The records, exactly as contract/CONTRACT.md section 3 names them. Nullable columns stay
 * nullable, except `summary` and `snapshot_path`: what a role may not see is absent (no key),
 * never null, so a component cannot be handed it by mistake.
 */

export type DeviceState = "calm" | "checking" | "alert"
export type Trigger = "fall" | "help_call" | "stillness" | "manual"
export type IncidentStatus = "checking" | "stood_down" | "escalated" | "acknowledged"
export type StoodDownBy = "voice" | "pat"

export const DEVICE_STATES: readonly DeviceState[] = ["calm", "checking", "alert"]
export const INCIDENT_STATUSES: readonly IncidentStatus[] = ["checking", "stood_down", "escalated", "acknowledged"]

/** `offline` is never stored: the dashboard shows it when `last_seen_at` is older than this. */
export const OFFLINE_AFTER_MS = 15_000

/** Fixture timestamps are written against this base time (section 5). */
export const BASE_TIME = Date.parse("2026-11-15T19:00:00Z")

export interface Device {
  readonly id: string
  readonly name: string
  readonly person_label: string
  readonly state: DeviceState
  readonly last_seen_at: string
  readonly fw: string | null
  readonly caps: readonly string[]
}

interface IncidentRecord {
  readonly id: string
  readonly device_id: string
  /** A trigger from section 1; an unknown one is kept and shown as written. */
  readonly trigger: string
  readonly status: IncidentStatus
  readonly confidence: number | null
  readonly started_at: string
  readonly ended_at: string | null
  readonly stood_down_by: string | null
  readonly acknowledged_by: string | null
  readonly acknowledged_at: string | null
}

/** Family: the summary and the snapshot path, only on an escalated or acknowledged incident. */
export interface FamilyIncident extends IncidentRecord {
  readonly summary?: string
  readonly snapshot_path?: string
}

/** Clinician: the summary on an escalated or acknowledged incident. Never a snapshot. */
export interface ClinicianIncident extends IncidentRecord {
  readonly summary?: string
  readonly snapshot_path?: never
}

export type Incident = FamilyIncident | ClinicianIncident

export interface TimelineEvent {
  readonly id: string
  readonly device_id: string
  readonly incident_id: string | null
  readonly at: string
  /** A kind from section 3, or one this build does not know. Its `text` is always shown. */
  readonly kind: string
  readonly text: string
  readonly detail: Readonly<Record<string, unknown>>
}

export interface Reading {
  readonly device_id: string
  readonly at: string
  readonly temp_c: number | null
  readonly tilt_deg: number | null
  readonly person_present: boolean
  readonly still_s: number
}

/** One line of the scripted run (section 5). */
export interface ScriptLine {
  readonly offset_ms: number
  readonly table: string
  readonly op: string
  readonly row: Readonly<Record<string, unknown>>
}
