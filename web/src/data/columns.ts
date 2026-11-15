import type { Role } from "@/auth/types"

export const DEVICE_COLUMNS = ["id", "name", "person_label", "state", "last_seen_at", "fw", "caps"] as const

export const INCIDENT_COLUMNS = [
  "id",
  "device_id",
  "trigger",
  "status",
  "confidence",
  "started_at",
  "ended_at",
  "stood_down_by",
  "summary",
  "acknowledged_by",
  "acknowledged_at",
] as const

export const SNAPSHOT_COLUMN = "snapshot_path"

export const EVENT_COLUMNS = ["id", "device_id", "incident_id", "at", "kind", "text", "detail"] as const

export const READING_COLUMNS = ["device_id", "at", "temp_c", "tilt_deg", "person_present", "still_s"] as const

/** Newest incidents held in memory. */
export const INCIDENT_LIMIT = 40
/** Newest timeline rows held in memory. */
export const EVENT_LIMIT = 80
/** Newest readings held, then shown oldest first. Ten minutes at one row per 5 seconds. */
export const READING_LIMIT = 120

/** Clinicians never ask for the snapshot column. Family does. */
export function incidentColumns(role: Role): readonly string[] {
  return role === "family" ? [...INCIDENT_COLUMNS, SNAPSHOT_COLUMN] : INCIDENT_COLUMNS
}
