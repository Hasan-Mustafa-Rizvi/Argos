import type { Role } from "@/auth/types"

import { admit, type MapTime } from "./admit"
import {
  BASE_TIME,
  type ClinicianIncident,
  type Device,
  type FamilyIncident,
  type Reading,
  type ScriptLine,
  type TimelineEvent,
} from "./contract"
import { DEMO_SCRIPT } from "./script"
import type { AckResult, DashboardView, DataSource } from "./source"

export const REPLAY_SPEEDS: readonly number[] = [1, 2, 4, 8]

/** A run shorter than this still waits this long before it starts again. */
const MIN_LOOP_MS = 1000

const KNOWN_TABLES = new Set(["devices", "incidents", "events", "readings"])

export interface ReplayOptions {
  role: Role
  /** How this session is named when it acknowledges. */
  label: string
  /** The scripted run. Defaults to the copy of contract/fixtures/demo_scenario.jsonl. */
  lines?: readonly ScriptLine[]
  speed?: number
  now?: () => number
  log?: (message: string) => void
}

type StoredIncident = FamilyIncident | ClinicianIncident

interface Ack {
  readonly by: string
  readonly at: string
}

function acknowledged<T extends StoredIncident>(incident: T, ack: Ack): T {
  return { ...incident, status: "acknowledged", acknowledged_by: ack.by, acknowledged_at: ack.at, ended_at: ack.at }
}

function clinicianOnly(incident: StoredIncident): ClinicianIncident {
  if (!("snapshot_path" in incident)) return incident as ClinicianIncident
  const { snapshot_path, ...rest } = incident
  void snapshot_path
  return rest
}

/**
 * Plays the scripted run (contract section 5): each line at its offset, timestamps shifted so
 * the base time lands on the start of this loop, and from the top again after the last line.
 * Every line passes through `admit` first, so what this role may not see is never stored.
 *
 * Acknowledging is the one write. Here it stays in this tab: the incident is acknowledged by
 * this session at this moment, the device returns to calm, and later lines in the same loop
 * cannot undo either. Each loop starts clean.
 */
export function createReplaySource({
  role,
  label,
  lines = DEMO_SCRIPT,
  speed: initialSpeed = 1,
  now = () => Date.now(),
  log = (message) => console.info(`[argos replay] ${message}`),
}: ReplayOptions): DataSource {
  const script = [...lines].sort((a, b) => a.offset_ms - b.offset_ms)
  const loopMs = Math.max(MIN_LOOP_MS, script.at(-1)?.offset_ms ?? 0)
  const listeners = new Set<() => void>()
  const warned = new Set<string>()

  let speed = REPLAY_SPEEDS.includes(initialSpeed) ? initialSpeed : 1
  let running = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let anchor = now()
  let next = 0
  let seq = 0

  let device: Device | null = null
  let incidents = new Map<string, StoredIncident>()
  let events = new Map<string, { event: TimelineEvent; seq: number }>()
  let readings: Reading[] | undefined
  let acks = new Map<string, Ack>()
  let holdCalm = false

  const mapTime: MapTime = (iso) => new Date(anchor + (Date.parse(iso) - BASE_TIME) / speed).toISOString()

  let view = buildView()

  function warnOnce(message: string) {
    if (warned.has(message)) return
    warned.add(message)
    log(message)
  }

  function buildView(): DashboardView {
    const incidentList = [...incidents.values()].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
    const eventList = [...events.values()]
      .sort((a, b) => Date.parse(b.event.at) - Date.parse(a.event.at) || b.seq - a.seq)
      .map((entry) => entry.event)
    if (role === "clinician") {
      return Object.freeze({
        role,
        source: "replay",
        device,
        incidents: incidentList.map(clinicianOnly),
        events: eventList,
        readings: [...(readings ?? [])],
        notice: null,
      })
    }
    return Object.freeze({
      role: "family",
      source: "replay",
      device,
      incidents: incidentList,
      events: eventList,
      notice: null,
    })
  }

  function publish() {
    view = buildView()
    listeners.forEach((listener) => listener())
  }

  function reset() {
    device = null
    incidents = new Map()
    events = new Map()
    readings = role === "clinician" ? [] : undefined
    acks = new Map()
    holdCalm = false
    next = 0
  }

  function apply(line: ScriptLine) {
    if (line.op !== "insert" && line.op !== "upsert") {
      warnOnce(`Ignoring a line with the unknown op "${line.op}".`)
      return
    }
    if (!KNOWN_TABLES.has(line.table)) {
      warnOnce(`Ignoring lines for the unknown table "${line.table}".`)
      return
    }
    const record = admit(line.table, line.row, role, mapTime, device)
    if (!record) return

    switch (record.table) {
      case "devices": {
        const row = record.row
        if (holdCalm && row.state === "alert") {
          device = { ...row, state: "calm" }
        } else {
          holdCalm = false
          device = row
        }
        break
      }
      case "incidents": {
        const ack = acks.get(record.row.id)
        incidents.set(record.row.id, ack ? acknowledged(record.row, ack) : record.row)
        break
      }
      case "events": {
        const event = record.row
        // This session acknowledged it already; nobody else's acknowledgement replaces that.
        if (event.kind === "acknowledged" && event.incident_id && acks.has(event.incident_id)) break
        if (line.op === "insert" && events.has(event.id)) break
        events.set(event.id, { event, seq: seq++ })
        break
      }
      case "readings":
        readings?.push(record.row)
        break
    }
  }

  function due(line: ScriptLine) {
    return anchor + line.offset_ms / speed
  }

  function pump(force = false) {
    timer = undefined
    if (!running) return
    const t = now()
    let changed = force
    while (next < script.length && due(script[next]) <= t) {
      apply(script[next++])
      changed = true
    }
    if (next >= script.length && t >= anchor + loopMs / speed) {
      if (changed) publish()
      begin(t)
      return
    }
    if (changed) publish()
    const target = next < script.length ? due(script[next]) : anchor + loopMs / speed
    timer = setTimeout(pump, Math.max(0, target - now()))
  }

  /** A loop starts clean, on a clock of its own. */
  function begin(at: number) {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
    reset()
    anchor = at
    pump(true)
  }

  function onVisible() {
    if (typeof document !== "undefined" && document.visibilityState === "visible" && running) {
      if (timer !== undefined) clearTimeout(timer)
      pump()
    }
  }

  return {
    role,
    kind: "replay",
    getView: () => view,
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    async acknowledge(incidentId): Promise<AckResult> {
      const incident = incidents.get(incidentId)
      if (!incident || incident.status !== "escalated") {
        return { ok: false, reason: "That incident is not waiting to be acknowledged." }
      }
      const ack: Ack = { by: label, at: new Date(now()).toISOString() }
      acks.set(incidentId, ack)
      incidents.set(incidentId, acknowledged(incident, ack))
      const id = `local-ack-${incidentId}`
      events.set(id, {
        event: {
          id,
          device_id: incident.device_id,
          incident_id: incidentId,
          at: ack.at,
          kind: "acknowledged",
          text: `${label} acknowledged.`,
          detail: { by: label },
        },
        seq: seq++,
      })
      if (device?.state === "alert") {
        holdCalm = true
        device = { ...device, state: "calm" }
      }
      publish()
      return { ok: true }
    },
    start() {
      if (running) return
      running = true
      if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisible)
      begin(now())
    },
    stop() {
      running = false
      if (timer !== undefined) clearTimeout(timer)
      timer = undefined
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisible)
    },
    replay: {
      speeds: REPLAY_SPEEDS,
      getSpeed: () => speed,
      setSpeed(value) {
        if (!REPLAY_SPEEDS.includes(value)) return
        speed = value
        if (running) begin(now())
      },
      restart() {
        if (running) begin(now())
      },
    },
  }
}
