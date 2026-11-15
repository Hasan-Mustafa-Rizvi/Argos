import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { describe, expect, it } from "vitest"

import { AuthProvider } from "@/auth/AuthProvider"
import { createDemoAuth } from "@/auth/demo"
import type { ReadySession } from "@/auth/types"
import { DashboardScreen } from "@/components/dashboard/DashboardScreen"
import { admitDevice } from "@/data/admit"
import { SNAPSHOT_COLUMN } from "@/data/columns"
import { DataProvider } from "@/data/DataProvider"
import { createLiveSource, LIVE_NOTICE } from "@/data/live"
import { createLiveAuth } from "@/auth/liveAuth"

import { deviceLine, renderDashboard } from "./dashboard-harness"
import { fakeGateway, fakeToken } from "./fake-gateway"

const DEVICE = "a0000000-0000-4000-8000-000000000001"

function ready(role: "family" | "clinician"): ReadySession {
  return {
    kind: "ready",
    role,
    demo: false,
    secondFactor: true,
    label: role === "family" ? "Daughter" : "Nurse",
    deviceId: DEVICE,
  }
}

function arm(role: "family" | "clinician") {
  const fake = fakeGateway()
  fake.state.token = fakeToken("aal2")
  fake.state.deviceRow = {
    id: DEVICE,
    name: "Argos",
    person_label: "Eleni",
    state: "calm",
    last_seen_at: "2026-11-15T19:00:00.000Z",
    fw: null,
    caps: [],
  }
  return { fake, source: createLiveSource(ready(role), fake.gateway) }
}

describe("a dog that has never reported", () => {
  it("is offline, with the not-reported line, and not Waiting for Argos", () => {
    const row = { id: DEVICE, name: "Argos", person_label: "Eleni", state: "calm", last_seen_at: null }
    expect(admitDevice(row, (iso) => iso, null)?.last_seen_at).toBeNull()
    renderDashboard({ role: "family", lines: [deviceLine(0, "calm", { last_seen_at: null })] })
    expect(screen.getByTestId("dashboard")).toHaveAttribute("data-state", "offline")
    expect(screen.getByText("Argos has not reported yet.")).toBeInTheDocument()
    expect(screen.queryByText("Waiting for Argos")).not.toBeInTheDocument()
    expect(screen.getByText(/Watching over/)).toBeInTheDocument()
  })
})

describe("rule 2a and rule 3", () => {
  it("authorizes before joining the private records topic, and a family session never asks for readings", async () => {
    const { fake, source } = arm("family")
    source.start()
    await waitFor(() => expect(fake.state.channels).toHaveLength(1))
    const channelAt = fake.state.order.findIndex((step) => step === `channel:records:${DEVICE}`)
    expect(fake.state.order.indexOf("authorize")).toBeGreaterThanOrEqual(0)
    expect(channelAt).toBeGreaterThan(fake.state.order.indexOf("authorize"))
    expect(fake.state.readingLoads).toBe(0)
    expect(fake.state.downloads).toBe(0)
    expect(fake.state.incidentColumns[0]).toContain(SNAPSHOT_COLUMN)
    source.stop()
  })

  it("a clinician never names the snapshot column and never calls storage", async () => {
    const { fake, source } = arm("clinician")
    source.start()
    await waitFor(() => expect(fake.state.incidentColumns.length).toBeGreaterThan(0))
    expect(fake.state.incidentColumns.every((columns) => !columns.includes(SNAPSHOT_COLUMN))).toBe(true)
    expect(fake.state.readingLoads).toBeGreaterThan(0)
    expect(fake.state.downloads).toBe(0)
    const channel = fake.state.channels[0]
    channel.emit({
      table: "incidents",
      event: "INSERT",
      row: {
        id: "b1",
        device_id: DEVICE,
        trigger: "fall",
        status: "escalated",
        confidence: 0.5,
        started_at: "2026-11-15T19:00:00.000Z",
        ended_at: null,
        stood_down_by: null,
        summary: "A person is down.",
        snapshot_path: "incidents/b1/snapshot.jpg",
        extra: "nope",
        acknowledged_by: null,
        acknowledged_at: null,
      },
    })
    channel.emit({ table: "weather", event: "INSERT", row: { id: "w", sky: "clear" } })
    const view = source.getView()
    expect(view.incidents).toHaveLength(1)
    expect(Object.keys(view.incidents[0])).not.toContain("snapshot_path")
    expect(Object.keys(view.incidents[0])).not.toContain("extra")
    expect(JSON.stringify(view)).not.toContain("snapshot")
    source.stop()
  })

  it("loads again after the channel drops", async () => {
    const { fake, source } = arm("family")
    source.start()
    await waitFor(() => expect(fake.state.deviceLoads).toBe(1))
    fake.state.channels[0].emitStatus("dropped")
    await waitFor(() => expect(fake.state.deviceLoads).toBeGreaterThan(1))
    source.stop()
  })

  it("starting again while the previous channel is still leaving waits, then joins", async () => {
    const { fake, source } = arm("family")
    let release: () => void = () => {}
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    source.start()
    await waitFor(() => expect(fake.state.channels).toHaveLength(1))
    const first = fake.state.channels[0]
    first.leave = () => {
      first.left = true
      return held
    }
    source.stop()
    source.start()
    await Promise.resolve()
    expect(fake.state.channels).toHaveLength(1)
    release()
    await waitFor(() => expect(fake.state.channels).toHaveLength(2))
    expect(fake.state.channels[1].topic).toBe(`records:${DEVICE}`)
    source.stop()
  })
})

describe("a failing backend", () => {
  it("shows one line, no scripted events, and stays a live source", async () => {
    const { fake, source } = arm("family")
    fake.state.failLoads = true
    const auth = createDemoAuth(window.sessionStorage)
    const session = auth.openDemo("family")
    render(
      <MemoryRouter>
        <AuthProvider client={auth}>
          <DataProvider session={session.kind === "demo" ? session : ready("family")} source={source}>
            <DashboardScreen />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText(LIVE_NOTICE)).toBeInTheDocument()
    expect(screen.queryByText("Argos is online.")).not.toBeInTheDocument()
    expect(source.kind).toBe("live")
    expect(source.getView().events).toHaveLength(0)
    source.stop()
  })
})

describe("rule 5", () => {
  it("sends exactly three columns for an escalated incident, and treats no row and an error as not acknowledged", async () => {
    const { fake, source } = arm("family")
    fake.state.ackRow = null
    const missed = await source.acknowledge("inc-1")
    expect(missed).toEqual({ ok: false, reason: "Someone may already have acknowledged it." })
    expect(fake.state.oneLoads).toBe(0)
    expect(Object.keys(fake.state.acks[0].patch)).toEqual(["status", "acknowledged_by", "acknowledged_at"])
    expect(fake.state.acks[0].patch).toMatchObject({ status: "acknowledged", acknowledged_by: "Daughter" })

    fake.state.ackError = true
    const failed = await source.acknowledge("inc-1")
    expect(failed.ok).toBe(false)
    if (!failed.ok) expect(failed.reason).toBe("Someone may already have acknowledged it.")

    fake.state.ackError = false
    fake.state.ackRow = "inc-1"
    fake.state.oneRow = {
      id: "inc-1",
      device_id: DEVICE,
      trigger: "fall",
      status: "acknowledged",
      confidence: null,
      started_at: "2026-11-15T19:00:00.000Z",
      ended_at: null,
      stood_down_by: null,
      acknowledged_by: "Daughter",
      acknowledged_at: "2026-11-15T19:01:00.000Z",
    }
    const done = await source.acknowledge("inc-1")
    expect(done.ok).toBe(true)
    expect(fake.state.oneLoads).toBe(1)
    expect(source.getView().incidents[0]?.status).toBe("acknowledged")
  })
})

describe("sign out closes channels", () => {
  it("the auth sign-out closes what the source opened", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal2")
    const session = ready("family")
    const auth = createLiveAuth(fake.gateway)
    const source = createLiveSource(session, fake.gateway)
    source.start()
    await waitFor(() => expect(fake.state.channels).toHaveLength(1))
    await auth.signOut()
    expect(auth.getSession()).toBeNull()
    expect(fake.state.closed).toBeGreaterThan(0)
    expect(fake.state.channels[0].left).toBe(true)
    source.stop()
  })
})
