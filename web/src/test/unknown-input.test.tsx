import { screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ScriptLine } from "@/data/contract"
import { createReplaySource } from "@/data/replay"

import { advance, at, DEVICE_ID, deviceLine, renderDashboard } from "./dashboard-harness"

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-11-20T10:00:00Z"))
})

afterEach(() => {
  vi.useRealTimers()
})

const strange: ScriptLine[] = [
  deviceLine(0, "calm", { mood: "sunny", battery: { level: 0.8 } }),
  { offset_ms: 500, table: "weather", op: "insert", row: { id: "w1", sky: "clear" } },
  { offset_ms: 600, table: "weather", op: "insert", row: { id: "w2", sky: "rain" } },
  {
    offset_ms: 1000,
    table: "events",
    op: "insert",
    row: {
      id: "c0000000-0000-4000-8000-0000000000aa",
      device_id: DEVICE_ID,
      incident_id: null,
      at: at(1),
      kind: "sniffed_the_flowers",
      text: "Argos sniffed the flowers.",
      detail: { flowers: ["rose"] },
      colour: "blue",
    },
  },
  { offset_ms: 1100, table: "events", op: "delete", row: { id: "c0000000-0000-4000-8000-0000000000aa" } },
  deviceLine(1200, "dreaming"),
  { offset_ms: 1300, table: "incidents", op: "upsert", row: { id: "half", status: "pondering" } },
  deviceLine(5000, "calm"),
]

describe("unknown input", () => {
  it("ignores an unknown table, op and field without throwing, and notes it once", () => {
    const log = vi.fn()
    const source = createReplaySource({ role: "clinician", label: "Clinician (demo)", lines: strange, log })
    expect(() => {
      source.start()
      vi.advanceTimersByTime(6000)
    }).not.toThrow()
    const view = source.getView()
    expect(view.device?.state).toBe("calm")
    expect(Object.keys(view.device!)).not.toContain("mood")
    expect(view.incidents).toHaveLength(0)
    expect(view.events.map((e) => e.kind)).toEqual(["sniffed_the_flowers"])
    expect(Object.keys(view.events[0])).not.toContain("colour")
    expect(log.mock.calls.filter(([m]) => String(m).includes('"weather"'))).toHaveLength(1)
    source.stop()
  })

  it("keeps the state it had when a device reports an unknown one", () => {
    const source = createReplaySource({ role: "family", label: "Family (demo)", lines: strange, log: () => {} })
    source.start()
    vi.advanceTimersByTime(1250)
    expect(source.getView().device?.state).toBe("calm")
    source.stop()
  })

  it("shows the text of an unknown kind", () => {
    renderDashboard({ role: "family", lines: strange })
    advance(2000)
    expect(screen.getByText("Argos sniffed the flowers.")).toBeInTheDocument()
  })
})
