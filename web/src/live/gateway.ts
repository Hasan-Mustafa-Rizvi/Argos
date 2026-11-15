import type { RealtimeChannel, SupabaseClient } from "@supabase/supabase-js"

import { isRole } from "@/auth/types"
import { DEVICE_COLUMNS, EVENT_COLUMNS, EVENT_LIMIT, INCIDENT_LIMIT, READING_COLUMNS, READING_LIMIT } from "@/data/columns"
import { frameMessage } from "@/data/frames"

import type { Gateway, LiveChange, LiveChannel, PasswordResult } from "./ports"

/**
 * The real calls, for the version installed here (@supabase/supabase-js 2.119.0).
 *
 * Realtime is given the session token with `setAuth` and that call is awaited before a
 * channel is joined. This build does not pass the token on the second-factor event, so a
 * join straight after verification would still be carrying the previous one. The client
 * does install an access-token callback, so a later refresh is picked up on
 * TOKEN_REFRESHED and on the heartbeat. `setAuth(token)` does not turn that off.
 *
 * Enrolment creates an unverified factor and will not create a second one with the same
 * name. Starting again removes unverified factors first, then enrols one.
 */

const SNAPSHOT_BUCKET = "snapshots"

interface ChangePayload {
  eventType?: string
  new?: Record<string, unknown>
  old?: Record<string, unknown>
}

function passwordReason(error: { status?: number; name?: string } | null): PasswordResult {
  if (!error || error.name === "AuthRetryableFetchError" || !error.status || error.status >= 500) {
    return { ok: false, reason: "unreachable" }
  }
  return { ok: false, reason: "credentials" }
}

async function release(client: SupabaseClient, channel: RealtimeChannel) {
  try {
    await client.removeChannel(channel)
  } catch {
    // Already gone.
  }
  // removeChannel leaves the channel in the client's list until the leave is acknowledged.
  // channel() would then hand that leaving channel back. Drop it so the next join is new.
  const stuck = client.getChannels().find((item) => item.topic === channel.topic)
  if (!stuck) return
  stuck.teardown()
  const realtime = client.realtime as { _remove?: (item: RealtimeChannel) => void }
  realtime._remove?.(stuck)
}

function asRow(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return []
  return value.filter((row): row is Record<string, unknown> => !!row && typeof row === "object" && !Array.isArray(row))
}

function rowFilter(topic: string, table: string): string | undefined {
  if (!topic.startsWith("records:")) return undefined
  const id = topic.slice("records:".length)
  if (!id) return undefined
  return table === "devices" ? `id=eq.${id}` : `device_id=eq.${id}`
}

export function createGateway(client: SupabaseClient): Gateway {
  return {
    subscribeAuth(handler) {
      const { data } = client.auth.onAuthStateChange((event, session) => {
        const token = session?.access_token ?? null
        const mapped = !token ? "signed-out" : event === "TOKEN_REFRESHED" ? "token" : "signed-in"
        // Deferred so this returns before any further auth work. A slow handler would
        // hold up later events, and a refresh started inside TOKEN_REFRESHED can deadlock.
        setTimeout(() => handler(mapped, token), 0)
      })
      return () => data.subscription.unsubscribe()
    },

    async signInWithPassword(email, password) {
      const { data, error } = await client.auth.signInWithPassword({ email, password })
      if (error || !data.session) return passwordReason(error)
      return { ok: true, token: data.session.access_token }
    },

    async signOut() {
      await client.auth.signOut()
    },

    async currentToken() {
      const { data } = await client.auth.getSession()
      return data.session?.access_token ?? null
    },

    async listFactors() {
      const { data, error } = await client.auth.mfa.listFactors()
      if (error || !data) throw new Error("Factors could not be listed.")
      return {
        verified: data.totp.map((factor) => factor.id),
        unverified: data.all
          .filter((factor) => factor.factor_type === "totp" && factor.status === "unverified")
          .map((factor) => factor.id),
      }
    },

    async enroll() {
      const listed = await client.auth.mfa.listFactors()
      if (listed.error || !listed.data) throw new Error("Factors could not be listed.")
      const stale = listed.data.all.filter((factor) => factor.factor_type === "totp" && factor.status === "unverified")
      for (const factor of stale) {
        const removed = await client.auth.mfa.unenroll({ factorId: factor.id })
        if (removed.error) throw new Error("An unfinished authenticator could not be cleared.")
      }
      const enrolled = await client.auth.mfa.enroll({ factorType: "totp", friendlyName: "Argos", issuer: "Argos" })
      if (enrolled.error || !enrolled.data || enrolled.data.type !== "totp") {
        throw new Error("The authenticator could not be started.")
      }
      return { factorId: enrolled.data.id, qr: enrolled.data.totp.qr_code, secret: enrolled.data.totp.secret }
    },

    async verify(factorId, code) {
      const { data, error } = await client.auth.mfa.challengeAndVerify({ factorId, code })
      if (error || !data.access_token) return { ok: false }
      return { ok: true, token: data.access_token }
    },

    async loadMember() {
      const { data, error } = await client
        .from("members")
        .select("device_id, role, label")
        .order("device_id", { ascending: true })
        .limit(1)
      if (error) throw new Error("Membership could not be read.")
      const row = data?.[0]
      if (!row || !isRole(row.role) || typeof row.device_id !== "string" || typeof row.label !== "string") return null
      return { deviceId: row.device_id, role: row.role, label: row.label }
    },

    async authorize() {
      const { data } = await client.auth.getSession()
      const token = data.session?.access_token
      if (!token) throw new Error("No session.")
      await client.realtime.setAuth(token)
    },

    async closeChannels() {
      await client.removeAllChannels()
    },

    openChannel(topic): LiveChannel {
      const channel = client.channel(topic, {
        config: { private: true, postgres_changes_options: { wait: true } },
      })
      return {
        onChange(table, columns, onRow) {
          const filter = rowFilter(topic, table)
          channel.on(
            "postgres_changes",
            {
              event: "*",
              schema: "public",
              table,
              ...(filter ? { filter } : {}),
              select: [...columns],
            },
            (payload) => {
              const body = payload as ChangePayload
              const event = body.eventType === "DELETE" ? "DELETE" : body.eventType === "UPDATE" ? "UPDATE" : "INSERT"
              const row = event === "DELETE" ? (body.old ?? {}) : (body.new ?? {})
              const change: LiveChange = { table: payload.table || table, event, row }
              onRow(change)
            },
          )
        },
        onBroadcast(event, onMessage) {
          channel.on("broadcast", { event }, (message) => {
            onMessage(frameMessage(message))
          })
        },
        subscribe(onStatus) {
          channel.subscribe((status) => {
            if (status === "SUBSCRIBED") onStatus("joined")
            else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") onStatus("dropped")
          })
        },
        leave: () => release(client, channel),
      }
    },

    async loadDevice(deviceId) {
      const { data, error } = await client.from("devices").select(DEVICE_COLUMNS.join(",")).eq("id", deviceId).maybeSingle()
      if (error) throw new Error("The device could not be read.")
      return asRow(data)
    },

    async loadIncidents(deviceId, columns) {
      const { data, error } = await client
        .from("incidents")
        .select(columns.join(","))
        .eq("device_id", deviceId)
        .order("started_at", { ascending: false })
        .limit(INCIDENT_LIMIT)
      if (error) throw new Error("Incidents could not be read.")
      return asRows(data)
    },

    async loadEvents(deviceId) {
      const { data, error } = await client
        .from("events")
        .select(EVENT_COLUMNS.join(","))
        .eq("device_id", deviceId)
        .order("at", { ascending: false })
        .limit(EVENT_LIMIT)
      if (error) throw new Error("The timeline could not be read.")
      return asRows(data)
    },

    async loadReadings(deviceId) {
      const { data, error } = await client
        .from("readings")
        .select(READING_COLUMNS.join(","))
        .eq("device_id", deviceId)
        .order("at", { ascending: false })
        .limit(READING_LIMIT)
      if (error) throw new Error("Readings could not be read.")
      return asRows(data)
    },

    async loadIncident(id, columns) {
      const { data, error } = await client.from("incidents").select(columns.join(",")).eq("id", id).maybeSingle()
      if (error) throw new Error("The incident could not be read.")
      return asRow(data)
    },

    async acknowledge(id, patch) {
      const { data, error } = await client
        .from("incidents")
        .update(patch)
        .eq("id", id)
        .eq("status", "escalated")
        .select("id")
      if (error) throw new Error("The acknowledgement was not accepted.")
      const row = asRows(data)[0]
      return row && typeof row.id === "string" ? row.id : null
    },

    async downloadSnapshot(path) {
      const { data, error } = await client.storage.from(SNAPSHOT_BUCKET).download(path)
      if (error || !data) return null
      return data
    },
  }
}
