import type { SupabaseClient } from "@supabase/supabase-js"
import { describe, expect, it } from "vitest"

import { incidentColumns } from "@/data/columns"
import { createGateway } from "@/live/gateway"

interface Call {
  table: string
  calls: unknown[][]
}

function harness(sessionToken = "token-aal2") {
  const calls: Call[] = []
  const opened: { topic: string; config: { private?: boolean } }[] = []
  const order: string[] = []
  const unenrolled: string[] = []
  let factors = {
    all: [{ id: "half", factor_type: "totp", status: "unverified" }],
    totp: [] as { id: string }[],
    phone: [] as { id: string }[],
  }
  const client = {
    realtime: {
      async setAuth() {
        order.push("setAuth")
      },
      _remove(channel: { topic: string }) {
        order.push(`remove:${channel.topic}`)
      },
    },
    getChannels: () => [],
    async removeChannel() {
      return "ok"
    },
    async removeAllChannels() {
      order.push("removeAll")
    },
    channel(topic: string, params: { config: { private?: boolean } }) {
      order.push(`channel:${topic}`)
      opened.push({ topic, config: params.config })
      return {
        topic: `realtime:${topic}`,
        on() {
          return this
        },
        subscribe(cb: (status: string) => void) {
          cb("SUBSCRIBED")
          return this
        },
        teardown() {},
      }
    },
    auth: {
      async getSession() {
        return { data: { session: sessionToken ? { access_token: sessionToken } : null } }
      },
      async signOut() {},
      onAuthStateChange() {
        return { data: { subscription: { unsubscribe() {} } } }
      },
      async signInWithPassword() {
        return { data: { session: null }, error: { status: 400, message: "invalid" } }
      },
      mfa: {
        async listFactors() {
          return { data: factors, error: null }
        },
        async unenroll({ factorId }: { factorId: string }) {
          unenrolled.push(factorId)
          factors = { all: [], totp: [], phone: [] }
          return { data: { id: factorId }, error: null }
        },
        async enroll() {
          factors = { all: [{ id: "fresh", factor_type: "totp", status: "unverified" }], totp: [], phone: [] }
          return { data: { id: "fresh", type: "totp", totp: { qr_code: "<svg/>", secret: "ABC" } }, error: null }
        },
        async challengeAndVerify() {
          return { data: { access_token: "token-aal2" }, error: null }
        },
      },
    },
    from(table: string) {
      const entry: Call = { table, calls: [] }
      calls.push(entry)
      const self = {
        select(columns: string) {
          entry.calls.push(["select", columns])
          return self
        },
        update(values: unknown) {
          entry.calls.push(["update", values])
          return self
        },
        eq(column: string, value: string) {
          entry.calls.push(["eq", column, value])
          return self
        },
        order(column: string, options: unknown) {
          entry.calls.push(["order", column, options])
          return self
        },
        limit(count: number) {
          entry.calls.push(["limit", count])
          return self
        },
        maybeSingle() {
          return Promise.resolve({ data: null, error: null })
        },
        then(resolve: (value: { data: unknown[]; error: null }) => unknown, reject: (reason: unknown) => unknown) {
          return Promise.resolve({ data: [], error: null }).then(resolve, reject)
        },
      }
      return self
    },
    storage: {
      from() {
        return { async download() { return { data: new Blob(["x"]), error: null } } }
      },
    },
  }
  return { gateway: createGateway(client as unknown as SupabaseClient), calls, opened, order, unenrolled }
}

describe("the real client calls", () => {
  it("sets the token before a private channel, on the topics the caller asks for", async () => {
    const { gateway, opened, order } = harness()
    await gateway.authorize()
    gateway.openChannel("records:dog-1")
    gateway.openChannel("view:dog-1")
    expect(order.indexOf("setAuth")).toBeLessThan(order.indexOf("channel:records:dog-1"))
    expect(opened).toEqual([
      { topic: "records:dog-1", config: { private: true, postgres_changes_options: { wait: true } } },
      { topic: "view:dog-1", config: { private: true, postgres_changes_options: { wait: true } } },
    ])
  })

  it("names columns, leaves the snapshot out for a clinician, and updates only the three acknowledgement columns", async () => {
    const { gateway, calls } = harness()
    await gateway.loadIncidents("dog-1", incidentColumns("clinician"))
    await gateway.loadIncidents("dog-1", incidentColumns("family"))
    await gateway.loadReadings("dog-1")
    const selects = calls.filter((entry) => entry.calls.some((call) => call[0] === "select")).map((entry) => entry.calls[0][1])
    expect(selects.some((columns) => String(columns).includes("*"))).toBe(false)
    expect(String(selects[0])).not.toContain("snapshot_path")
    expect(String(selects[1])).toContain("snapshot_path")
    expect(String(selects[2])).not.toContain("snapshot_path")

    await gateway.acknowledge("inc-1", {
      status: "acknowledged",
      acknowledged_by: "Daughter",
      acknowledged_at: "2026-11-15T19:01:00.000Z",
    })
    const update = calls.find((entry) => entry.calls.some((call) => call[0] === "update"))
    const values = update?.calls.find((call) => call[0] === "update")?.[1] as Record<string, string>
    expect(Object.keys(values)).toEqual(["status", "acknowledged_by", "acknowledged_at"])
    expect(update?.calls).toContainEqual(["eq", "id", "inc-1"])
    expect(update?.calls).toContainEqual(["eq", "status", "escalated"])
    expect(update?.calls).toContainEqual(["select", "id"])
  })

  it("clears an unfinished factor before enrolling, so a second start does not pile them up", async () => {
    // The installed client creates an unverified factor on enrol and rejects a second
    // factor with the same name. This clears unverified factors first, then enrols one.
    const { gateway, unenrolled } = harness()
    const first = await gateway.enroll()
    expect(unenrolled).toEqual(["half"])
    expect(first.factorId).toBe("fresh")
    const second = await gateway.enroll()
    expect(second.factorId).toBe("fresh")
    expect(unenrolled).toEqual(["half", "fresh"])
  })
})
