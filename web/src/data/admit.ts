import type { Role } from "@/auth/types"

import {
  DEVICE_STATES,
  INCIDENT_STATUSES,
  type ClinicianIncident,
  type Device,
  type DeviceState,
  type FamilyIncident,
  type IncidentStatus,
  type Reading,
  type TimelineEvent,
} from "./contract"

/*
 * Where every record enters the dashboard. Each row is rebuilt here from the columns this
 * build knows, and what the role may not see is dropped before anything is stored:
 *
 * - a family session never receives a reading;
 * - a clinician session never receives a snapshot path, not even an empty one;
 * - nobody receives a summary or a snapshot path unless the incident is escalated or
 *   acknowledged.
 *
 * Unknown tables and unknown columns are ignored. Unknown event kinds are kept, because their
 * text can always be shown.
 */

export type Admitted =
  | { readonly table: "devices"; readonly row: Device }
  | { readonly table: "incidents"; readonly row: FamilyIncident | ClinicianIncident }
  | { readonly table: "events"; readonly row: TimelineEvent }
  | { readonly table: "readings"; readonly row: Reading }

/** Moves a fixture timestamp onto the replay clock. Live records pass through unchanged. */
export type MapTime = (iso: string) => string

type Row = Readonly<Record<string, unknown>>

const SHOWS_REPORT: ReadonlySet<IncidentStatus> = new Set(["escalated", "acknowledged"])

const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined)
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null)
const strOrNull = (v: unknown): string | null => (typeof v === "string" ? v : null)
const nonEmpty = (v: unknown): string | undefined => (typeof v === "string" && v.trim() !== "" ? v : undefined)

function time(v: unknown, mapTime: MapTime): string | undefined {
  return typeof v === "string" && !Number.isNaN(Date.parse(v)) ? mapTime(v) : undefined
}

function timeOrNull(v: unknown, mapTime: MapTime): string | null {
  return time(v, mapTime) ?? null
}

function isDeviceState(v: unknown): v is DeviceState {
  return DEVICE_STATES.includes(v as DeviceState)
}

function isStatus(v: unknown): v is IncidentStatus {
  return INCIDENT_STATUSES.includes(v as IncidentStatus)
}

/**
 * A device row. An unknown state keeps the state the dashboard already had.
 * `last_seen_at` may be null: the contract allows it, and the seeded dog is null until
 * the brain first reports. A missing timestamp keeps the previous one when we have it.
 */
export function admitDevice(row: Row, mapTime: MapTime, previous: Device | null): Device | null {
  const id = str(row.id)
  const state = isDeviceState(row.state) ? row.state : previous?.state
  if (!id || !state) return null
  let lastSeen: string | null
  if (!("last_seen_at" in row)) {
    lastSeen = previous?.id === id ? previous.last_seen_at : null
  } else if (row.last_seen_at === null) {
    lastSeen = null
  } else {
    const mapped = time(row.last_seen_at, mapTime)
    if (!mapped) return null
    lastSeen = mapped
  }
  return {
    id,
    name: str(row.name) ?? previous?.name ?? "Argos",
    person_label: str(row.person_label) ?? previous?.person_label ?? "",
    state,
    last_seen_at: lastSeen,
    fw: strOrNull(row.fw),
    caps: Array.isArray(row.caps) ? row.caps.filter((c): c is string => typeof c === "string") : [],
  }
}

export function admitIncident(row: Row, role: "family", mapTime: MapTime): FamilyIncident | null
export function admitIncident(row: Row, role: "clinician", mapTime: MapTime): ClinicianIncident | null
export function admitIncident(row: Row, role: Role, mapTime: MapTime): FamilyIncident | ClinicianIncident | null
export function admitIncident(row: Row, role: Role, mapTime: MapTime): FamilyIncident | ClinicianIncident | null {
  const id = str(row.id)
  const deviceId = str(row.device_id)
  const trigger = str(row.trigger)
  const startedAt = time(row.started_at, mapTime)
  if (!id || !deviceId || !trigger || !startedAt || !isStatus(row.status)) return null
  const status = row.status

  const incident: ClinicianIncident = {
    id,
    device_id: deviceId,
    trigger,
    status,
    confidence: num(row.confidence),
    started_at: startedAt,
    ended_at: timeOrNull(row.ended_at, mapTime),
    stood_down_by: strOrNull(row.stood_down_by),
    acknowledged_by: strOrNull(row.acknowledged_by),
    acknowledged_at: timeOrNull(row.acknowledged_at, mapTime),
  }
  if (!SHOWS_REPORT.has(status)) return incident

  const summary = nonEmpty(row.summary)
  const withSummary: ClinicianIncident = summary ? { ...incident, summary } : incident
  if (role !== "family") return withSummary

  const snapshotPath = nonEmpty(row.snapshot_path)
  return snapshotPath ? ({ ...withSummary, snapshot_path: snapshotPath } satisfies FamilyIncident) : withSummary
}

export function admitEvent(row: Row, mapTime: MapTime): TimelineEvent | null {
  const id = str(row.id)
  const deviceId = str(row.device_id)
  const at = time(row.at, mapTime)
  const kind = str(row.kind)
  const text = str(row.text)
  if (!id || !deviceId || !at || !kind || text === undefined) return null
  const detail = row.detail && typeof row.detail === "object" && !Array.isArray(row.detail) ? (row.detail as Row) : {}
  return { id, device_id: deviceId, incident_id: strOrNull(row.incident_id), at, kind, text, detail }
}

/** Readings are for clinicians. For anyone else the row is dropped before it is read. */
export function admitReading(row: Row, role: Role, mapTime: MapTime): Reading | null {
  if (role !== "clinician") return null
  const deviceId = str(row.device_id)
  const at = time(row.at, mapTime)
  if (!deviceId || !at || typeof row.person_present !== "boolean") return null
  return {
    device_id: deviceId,
    at,
    temp_c: num(row.temp_c),
    tilt_deg: num(row.tilt_deg),
    person_present: row.person_present,
    still_s: num(row.still_s) ?? 0,
  }
}

/** One record, as the role may see it, or null when it is ignored or not for this role. */
export function admit(
  table: string,
  row: Row,
  role: Role,
  mapTime: MapTime,
  previousDevice: Device | null = null,
): Admitted | null {
  switch (table) {
    case "devices": {
      const device = admitDevice(row, mapTime, previousDevice)
      return device && { table, row: device }
    }
    case "incidents": {
      const incident = admitIncident(row, role, mapTime)
      return incident && { table, row: incident }
    }
    case "events": {
      const event = admitEvent(row, mapTime)
      return event && { table, row: event }
    }
    case "readings": {
      const reading = admitReading(row, role, mapTime)
      return reading && { table, row: reading }
    }
    default:
      return null
  }
}
