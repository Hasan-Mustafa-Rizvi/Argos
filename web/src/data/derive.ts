import type { InkState } from "@/components/argos/ink"

import { OFFLINE_AFTER_MS, type Device, type Incident, type TimelineEvent } from "./contract"

/** `offline` is derived, never stored: no device yet, or no report for more than 15 s. */
export function isOffline(device: Device | null, now: number): boolean {
  if (!device) return true
  const seen = Date.parse(device.last_seen_at)
  return Number.isNaN(seen) || now - seen > OFFLINE_AFTER_MS
}

export function displayState(device: Device | null, now: number): InkState {
  return !device || isOffline(device, now) ? "offline" : device.state
}

/** The escalated incident waiting for someone to acknowledge it, if any. Incidents are newest first. */
export function waitingIncident<T extends Incident>(incidents: readonly T[]): T | undefined {
  return incidents.find((i) => i.status === "escalated")
}

/** The incident still in progress: checking or escalated. */
export function openIncident<T extends Incident>(incidents: readonly T[]): T | undefined {
  return incidents.find((i) => i.status === "checking" || i.status === "escalated")
}

/**
 * When the device entered its current state, read from the records: a check began at its
 * incident's start, an alert at its `escalated` event, and calm at the end of the last
 * incident (or when Argos came online).
 */
export function stateSince(
  device: Device | null,
  incidents: readonly Incident[],
  events: readonly TimelineEvent[],
): string | null {
  if (!device) return null
  const open = openIncident(incidents)
  if (device.state === "checking") return open?.started_at ?? null
  if (device.state === "alert") {
    if (!open) return null
    return events.find((e) => e.kind === "escalated" && e.incident_id === open.id)?.at ?? open.started_at
  }
  const ends = incidents.map((i) => i.ended_at).filter((t): t is string => !!t)
  const online = events.filter((e) => e.kind === "device_online").map((e) => e.at)
  const latest = [...ends, ...online].sort((a, b) => Date.parse(b) - Date.parse(a))[0]
  return latest ?? null
}

/** Incidents started on the local calendar day of `now`. */
export function checksToday<T extends Incident>(incidents: readonly T[], now: number): T[] {
  const today = new Date(now).toDateString()
  return incidents.filter((i) => new Date(i.started_at).toDateString() === today)
}

const TRIGGERS: Readonly<Record<string, string>> = {
  fall: "A fall",
  help_call: "A call for help",
  stillness: "A long stillness",
  manual: "A manual check",
}

export function triggerLabel(trigger: string): string {
  if (TRIGGERS[trigger]) return TRIGGERS[trigger]
  const words = trigger.replace(/[_-]+/g, " ").trim()
  return words ? words[0].toUpperCase() + words.slice(1) : "A check"
}

/** How an incident ended, in a few words. */
export function endingLabel(incident: Incident, person: string): string {
  switch (incident.status) {
    case "checking":
      return "Checking now"
    case "escalated":
      return "Waiting to be acknowledged"
    case "acknowledged":
      return incident.acknowledged_by ? `Acknowledged by ${incident.acknowledged_by}` : "Acknowledged"
    case "stood_down":
      return standDownLabel(incident.stood_down_by, person)
  }
}

export function standDownLabel(by: string | null, person: string): string {
  if (by === "voice") return person ? `${person} answered` : "An answer"
  if (by === "pat") return "A pat on the head"
  return "Stood down"
}

/** Endings for the count of today's checks. */
export const ENDINGS = ["stood_down", "escalated", "acknowledged", "checking"] as const

export const ENDING_NAMES: Readonly<Record<(typeof ENDINGS)[number], string>> = {
  stood_down: "Stood down",
  escalated: "Waiting",
  acknowledged: "Acknowledged",
  checking: "Checking now",
}

const clock = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" })

/** "7:00:38 PM", in the reader's time zone. */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return ""
  const t = Date.parse(iso)
  return Number.isNaN(t) ? "" : clock.format(t)
}

/** "just now", "12 s ago", "3 min ago". */
export function formatAgo(iso: string | null | undefined, now: number): string {
  if (!iso) return ""
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ""
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 2) return "just now"
  if (s < 60) return `${s} s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  return formatClock(iso)
}
