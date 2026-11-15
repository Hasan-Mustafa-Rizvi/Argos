import type { Role } from "@/auth/types"
import type { Gateway, LiveChange, LiveChannel } from "@/live/ports"

/** A JWT-shaped token with an assurance claim. Not a real credential. */
export function fakeToken(aal: "aal1" | "aal2", sub = "user-1") {
  return `head.${btoa(JSON.stringify({ aal, sub }))}.tail`
}

export interface FakeChannel extends LiveChannel {
  topic: string
  changes: { table: string; columns: readonly string[]; onRow: (change: LiveChange) => void }[]
  frames: ((payload: unknown) => void)[]
  status: ((status: "joined" | "dropped") => void) | null
  left: boolean
  emit(change: LiveChange): void
  emitStatus(status: "joined" | "dropped"): void
}

/**
 * Copies the parts of the backend this task depends on:
 * enrol creates one unverified factor, and a later enrol removes unverified factors first;
 * a channel cannot be opened until authorize has run;
 * acknowledge reports no row by returning null.
 */
export function fakeGateway() {
  const state = {
    token: null as string | null,
    members: [] as { deviceId: string; role: Role; label: string }[],
    verified: [] as string[],
    unverified: [] as string[],
    enrolls: 0,
    signOuts: 0,
    closed: 0,
    downloads: 0,
    order: [] as string[],
    channels: [] as FakeChannel[],
    deviceLoads: 0,
    incidentLoads: 0,
    eventLoads: 0,
    readingLoads: 0,
    oneLoads: 0,
    incidentColumns: [] as (readonly string[])[],
    acks: [] as { id: string; patch: { status: string; acknowledged_by: string; acknowledged_at: string } }[],
    ackRow: null as string | null,
    ackError: false,
    failLoads: false,
    deviceRow: null as Record<string, unknown> | null,
    incidentRows: [] as Record<string, unknown>[],
    eventRows: [] as Record<string, unknown>[],
    readingRows: [] as Record<string, unknown>[],
    oneRow: null as Record<string, unknown> | null,
    password: "ok" as "ok" | "credentials" | "unreachable",
    code: "123456",
  }
  const handlers: ((event: "signed-in" | "signed-out" | "token", token: string | null) => void)[] = []

  const gateway: Gateway = {
    subscribeAuth(handler) {
      handlers.push(handler)
      queueMicrotask(() => handler(state.token ? "signed-in" : "signed-out", state.token))
      return () => {
        const index = handlers.indexOf(handler)
        if (index >= 0) handlers.splice(index, 1)
      }
    },
    async signInWithPassword() {
      if (state.password !== "ok") return { ok: false, reason: state.password }
      state.token = fakeToken("aal1")
      return { ok: true, token: state.token }
    },
    async signOut() {
      state.signOuts++
      state.token = null
      handlers.forEach((handler) => handler("signed-out", null))
    },
    async currentToken() {
      return state.token
    },
    async listFactors() {
      return { verified: [...state.verified], unverified: [...state.unverified] }
    },
    async enroll() {
      state.unverified = []
      state.enrolls++
      const factorId = `factor-${state.enrolls}`
      state.unverified = [factorId]
      return { factorId, qr: "<svg xmlns='http://www.w3.org/2000/svg'/>", secret: `SETUP${state.enrolls}` }
    },
    async verify(_factorId, code) {
      if (code !== state.code) return { ok: false }
      state.token = fakeToken("aal2")
      state.verified = state.unverified.length ? [...state.unverified] : ["factor-verified"]
      state.unverified = []
      return { ok: true, token: state.token }
    },
    async loadMember() {
      const row = state.members[0]
      return row ? { ...row } : null
    },
    async authorize() {
      if (!state.token) throw new Error("No session.")
      state.order.push("authorize")
    },
    async closeChannels() {
      state.closed++
      await Promise.all(state.channels.map((channel) => channel.leave()))
    },
    openChannel(topic) {
      if (!state.order.includes("authorize")) throw new Error("Channel before the token was handed over.")
      state.order.push(`channel:${topic}`)
      const channel: FakeChannel = {
        topic,
        changes: [],
        frames: [],
        status: null,
        left: false,
        onChange(table, columns, onRow) {
          channel.changes.push({ table, columns, onRow })
        },
        onBroadcast(_event, onMessage) {
          channel.frames.push(onMessage)
        },
        subscribe(onStatus) {
          channel.status = onStatus
          queueMicrotask(() => onStatus("joined"))
        },
        async leave() {
          channel.left = true
        },
        emit(change) {
          for (const handler of channel.changes) handler.onRow(change)
        },
        emitStatus(status) {
          channel.status?.(status)
        },
      }
      state.channels.push(channel)
      return channel
    },
    async loadDevice() {
      state.deviceLoads++
      if (state.failLoads) throw new Error("down")
      return state.deviceRow
    },
    async loadIncidents(_id, columns) {
      state.incidentLoads++
      state.incidentColumns.push(columns)
      if (state.failLoads) throw new Error("down")
      return state.incidentRows
    },
    async loadEvents() {
      state.eventLoads++
      if (state.failLoads) throw new Error("down")
      return state.eventRows
    },
    async loadReadings() {
      state.readingLoads++
      if (state.failLoads) throw new Error("down")
      return state.readingRows
    },
    async loadIncident() {
      state.oneLoads++
      if (state.failLoads) throw new Error("down")
      return state.oneRow
    },
    async acknowledge(id, patch) {
      state.acks.push({ id, patch })
      if (state.ackError) throw new Error("down")
      return state.ackRow
    },
    async downloadSnapshot() {
      state.downloads++
      return null
    },
  }

  return { state, gateway }
}
