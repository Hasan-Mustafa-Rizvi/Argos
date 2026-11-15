import type { ReadySession } from "@/auth/types"
import type { Gateway, LiveChange } from "@/live/ports"

import { admit, type MapTime } from "./admit"
import { DEVICE_COLUMNS, EVENT_COLUMNS, EVENT_LIMIT, incidentColumns, INCIDENT_LIMIT, READING_COLUMNS, READING_LIMIT } from "./columns"
import type { ClinicianIncident, Device, FamilyIncident, Reading, TimelineEvent } from "./contract"
import type { AckResult, DashboardView, DataSource } from "./source"

const SAME: MapTime = (iso) => iso
const RETRY_MS = 2_000

export const LIVE_NOTICE = "Argos cannot be reached just now. Still trying."
const NOT_ACKNOWLEDGED = "Someone may already have acknowledged it."

type StoredIncident = FamilyIncident | ClinicianIncident

function withoutSnapshot(incident: StoredIncident): ClinicianIncident {
  const { snapshot_path, ...rest } = incident as FamilyIncident
  void snapshot_path
  return rest
}

function emptyView(role: ReadySession["role"], notice: string | null): DashboardView {
  if (role === "clinician") {
    return Object.freeze({ role, source: "live", device: null, incidents: [], events: [], readings: [], notice })
  }
  return Object.freeze({ role: "family", source: "live", device: null, incidents: [], events: [], notice })
}

/**
 * Live records for one dog. Listen, then load, and merge by id. A family session never asks
 * for readings. A clinician session never asks for the snapshot column. Nothing here plays
 * the scripted run.
 */
export function createLiveSource(session: ReadySession, injected?: Gateway): DataSource {
  const { role, label, deviceId } = session
  const listeners = new Set<() => void>()
  let device: Device | null = null
  let incidents = new Map<string, StoredIncident>()
  let events = new Map<string, { event: TimelineEvent; seq: number }>()
  let readings = new Map<string, Reading>()
  let seq = 0
  let notice: string | null = null
  let view = emptyView(role, null)

  let running = false
  let epoch = 0
  let leaving: Promise<void> = Promise.resolve()
  let channel: ReturnType<Gateway["openChannel"]> | null = null
  let retry: ReturnType<typeof setTimeout> | undefined
  let buffering = false
  let buffer: LiveChange[] = []
  let gateway: Gateway | null = injected ?? null

  function publish() {
    view = build()
    listeners.forEach((listener) => listener())
  }

  function build(): DashboardView {
    const incidentList = [...incidents.values()]
      .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
      .slice(0, INCIDENT_LIMIT)
    const eventList = [...events.values()]
      .sort((a, b) => Date.parse(b.event.at) - Date.parse(a.event.at) || b.seq - a.seq)
      .slice(0, EVENT_LIMIT)
      .map((entry) => entry.event)
    const readingList = [...readings.values()]
      .sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
      .slice(-READING_LIMIT)
    if (role === "clinician") {
      return Object.freeze({
        role,
        source: "live",
        device,
        incidents: incidentList.map(withoutSnapshot),
        events: eventList,
        readings: readingList,
        notice,
      })
    }
    return Object.freeze({ role: "family", source: "live", device, incidents: incidentList, events: eventList, notice })
  }

  function cap() {
    if (incidents.size > INCIDENT_LIMIT) {
      const keep = [...incidents.values()]
        .sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
        .slice(0, INCIDENT_LIMIT)
      incidents = new Map(keep.map((row) => [row.id, row]))
    }
    if (events.size > EVENT_LIMIT) {
      const keep = [...events.values()]
        .sort((a, b) => Date.parse(b.event.at) - Date.parse(a.event.at) || b.seq - a.seq)
        .slice(0, EVENT_LIMIT)
      events = new Map(keep.map((entry) => [entry.event.id, entry]))
    }
    if (readings.size > READING_LIMIT) {
      const keep = [...readings.values()]
        .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
        .slice(0, READING_LIMIT)
      readings = new Map(keep.map((row) => [`${row.device_id}\n${row.at}`, row]))
    }
  }

  function ours(table: string, row: Readonly<Record<string, unknown>>): boolean {
    if (table === "devices") return row.id === undefined || row.id === deviceId
    if (typeof row.device_id === "string") return row.device_id === deviceId
    return true
  }

  function remove(table: string, row: Readonly<Record<string, unknown>>) {
    if (table === "incidents" && typeof row.id === "string") incidents.delete(row.id)
    else if (table === "events" && typeof row.id === "string") events.delete(row.id)
    else if (table === "readings" && typeof row.device_id === "string" && typeof row.at === "string") {
      readings.delete(`${row.device_id}\n${row.at}`)
    }
  }

  function apply(change: LiveChange) {
    if (!ours(change.table, change.row)) return
    if (change.event === "DELETE") {
      remove(change.table, change.row)
      return
    }
    const admitted = admit(change.table, change.row, role, SAME, device)
    if (!admitted) return
    switch (admitted.table) {
      case "devices":
        device = admitted.row
        break
      case "incidents":
        incidents.set(admitted.row.id, admitted.row)
        break
      case "events":
        events.set(admitted.row.id, { event: admitted.row, seq: seq++ })
        break
      case "readings":
        readings.set(`${admitted.row.device_id}\n${admitted.row.at}`, admitted.row)
        break
    }
    cap()
  }

  function ingest(change: LiveChange) {
    if (buffering) {
      buffer.push(change)
      return
    }
    apply(change)
    publish()
  }

  async function resolveGateway(): Promise<Gateway> {
    if (gateway) return gateway
    const { liveConfigured } = await import("@/live/settings")
    if (!liveConfigured()) throw new Error("Live settings are not set.")
    const { sharedGateway } = await import("@/live/shared")
    gateway = await sharedGateway()
    return gateway
  }

  function replaceFrom(rows: readonly Record<string, unknown>[], table: string) {
    for (const row of rows) apply({ table, event: "INSERT", row })
  }

  async function load(gw: Gateway, my: number) {
    buffering = true
    const incidentCols = incidentColumns(role)
    try {
      const [deviceRow, incidentRows, eventRows, readingRows] = await Promise.all([
        gw.loadDevice(deviceId),
        gw.loadIncidents(deviceId, incidentCols),
        gw.loadEvents(deviceId),
        role === "clinician" ? gw.loadReadings(deviceId) : Promise.resolve([]),
      ])
      if (my !== epoch) return
      device = null
      incidents = new Map()
      events = new Map()
      readings = new Map()
      if (deviceRow) apply({ table: "devices", event: "INSERT", row: deviceRow })
      replaceFrom(incidentRows, "incidents")
      replaceFrom(eventRows, "events")
      replaceFrom(readingRows, "readings")
      const pending = buffer
      buffer = []
      buffering = false
      for (const change of pending) apply(change)
      notice = null
      publish()
    } catch (error) {
      buffering = false
      buffer = []
      if (my !== epoch) return
      notice = LIVE_NOTICE
      publish()
      throw error
    }
  }

  function fail(my: number) {
    if (my !== epoch) return
    notice = LIVE_NOTICE
    publish()
    schedule(my)
  }

  function schedule(my: number) {
    if (retry) clearTimeout(retry)
    retry = setTimeout(() => {
      retry = undefined
      if (my === epoch && running) void connect(my)
    }, RETRY_MS)
  }

  function drop(gw: Gateway, my: number) {
    if (my !== epoch) return
    notice = LIVE_NOTICE
    publish()
    const current = channel
    channel = null
    if (current) leaving = leaving.then(() => current.leave()).catch(() => undefined)
    void load(gw, my).catch(() => undefined)
    schedule(my)
  }

  async function connect(my: number) {
    const previous = channel
    channel = null
    if (previous) leaving = leaving.then(() => previous.leave()).catch(() => undefined)
    await leaving
    if (my !== epoch || !running) return
    let gw: Gateway
    try {
      gw = await resolveGateway()
      await gw.authorize()
    } catch {
      fail(my)
      return
    }
    if (my !== epoch || !running) return
    const next = gw.openChannel(`records:${deviceId}`)
    channel = next
    const cols = incidentColumns(role)
    next.onChange("devices", DEVICE_COLUMNS, ingest)
    next.onChange("incidents", cols, ingest)
    next.onChange("events", EVENT_COLUMNS, ingest)
    if (role === "clinician") next.onChange("readings", READING_COLUMNS, ingest)
    next.subscribe((status) => {
      if (my !== epoch) return
      if (status === "joined") {
        void load(gw, my).catch(() => {
          if (my === epoch) schedule(my)
        })
      } else drop(gw, my)
    })
  }

  function onVisible() {
    if (typeof document === "undefined" || document.visibilityState !== "visible" || !running) return
    const my = epoch
    void resolveGateway()
      .then((gw) => load(gw, my))
      .catch(() => undefined)
  }

  return {
    role,
    kind: "live",
    getView: () => view,
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    async acknowledge(incidentId): Promise<AckResult> {
      let gw: Gateway
      try {
        gw = await resolveGateway()
      } catch {
        return { ok: false, reason: NOT_ACKNOWLEDGED }
      }
      const patch = {
        status: "acknowledged" as const,
        acknowledged_by: label,
        acknowledged_at: new Date().toISOString(),
      }
      let returned: string | null
      try {
        returned = await gw.acknowledge(incidentId, patch)
      } catch {
        return { ok: false, reason: NOT_ACKNOWLEDGED }
      }
      if (!returned) return { ok: false, reason: NOT_ACKNOWLEDGED }
      try {
        const row = await gw.loadIncident(returned, incidentColumns(role))
        if (row) ingest({ table: "incidents", event: "UPDATE", row })
      } catch {
        notice = LIVE_NOTICE
        publish()
      }
      return { ok: true }
    },
    start() {
      if (running) return
      running = true
      if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisible)
      void connect(++epoch)
    },
    stop() {
      running = false
      epoch++
      if (retry) clearTimeout(retry)
      retry = undefined
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisible)
      const current = channel
      channel = null
      if (current) leaving = leaving.then(() => current.leave()).catch(() => undefined)
    },
  }
}
