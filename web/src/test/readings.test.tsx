import { screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ScriptLine } from "@/data/contract"

import { advance, at, DEVICE_ID, deviceLine, renderDashboard } from "./dashboard-harness"

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-11-20T10:00:00Z"))
})

afterEach(() => {
  vi.useRealTimers()
})

const reading = (offsetMs: number, temp: number | null, tilt: number | null): ScriptLine => ({
  offset_ms: offsetMs,
  table: "readings",
  op: "insert",
  row: { device_id: DEVICE_ID, at: at(offsetMs / 1000), temp_c: temp, tilt_deg: tilt, person_present: false, still_s: 0 },
})

/* The loop starts again once its last line is applied, so a later line keeps both readings on screen. */
const run = (...readings: ScriptLine[]) => [deviceLine(0, "calm"), ...readings, deviceLine(10_000, "calm")]

describe("clinician readings", () => {
  it("say plainly when the dog sent no temperature or tilt, and never print a stand-in value", () => {
    renderDashboard({ role: "clinician", lines: run(reading(0, null, null), reading(5000, null, null)) })
    advance(5500)
    expect(screen.getByText("Temperature not reported")).toBeInTheDocument()
    expect(screen.getByText("Tilt not reported")).toBeInTheDocument()
    expect(screen.getAllByText("Not reported")).toHaveLength(2)
    expect(screen.getByText("No one is in view", { exact: false })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/—|NaN|undefined|null/)
  })

  it("print the numbers they were given, with their units", () => {
    renderDashboard({ role: "clinician", lines: run(reading(0, 23.4, 1.2), reading(5000, 23.5, 1.4)) })
    advance(5500)
    expect(screen.getByText("23.5")).toBeInTheDocument()
    expect(screen.getAllByText("1.4°")).toHaveLength(2)
    expect(screen.getByText("23.5 °C")).toBeInTheDocument()
    expect(screen.getByText("0 s")).toBeInTheDocument()
  })
})
