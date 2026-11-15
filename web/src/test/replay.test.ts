import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ScriptLine } from "@/data/contract"
import { isOffline } from "@/data/derive"
import { createReplaySource } from "@/data/replay"
import { DEMO_SCRIPT, parseScript } from "@/data/script"

const quiet = () => {}

/** Every moment the scripted device changes state, read from the fixture itself. */
function stateChanges(lines: readonly ScriptLine[]) {
  const out: [number, string][] = []
  for (const line of lines) {
    if (line.table !== "devices") continue
    const state = String(line.row.state)
    if (state !== out.at(-1)?.[1]) out.push([line.offset_ms, state])
  }
  return out
}

describe("the scripted run", () => {
  it("is the copied fixture: 61 lines over 90 seconds", () => {
    expect(DEMO_SCRIPT).toHaveLength(61)
    expect(DEMO_SCRIPT.at(-1)?.offset_ms).toBe(90_000)
  })

  it("skips lines that are not record lines", () => {
    const lines = parseScript('{"offset_ms": 0, "table": "events", "op": "insert", "row": {}}\nnot json\n[]\n\n{"offset_ms": -1}')
    expect(lines).toHaveLength(1)
  })
})

describe("replay order", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-11-20T10:00:00Z"))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("the fixture changes state at 12.0, 17.3, 38.0, 48.5 and 70.0 s", () => {
    expect(stateChanges(DEMO_SCRIPT)).toEqual([
      [0, "calm"],
      [12_000, "checking"],
      [17_300, "calm"],
      [38_000, "checking"],
      [48_500, "alert"],
      [70_000, "calm"],
    ])
  })

  it("plays calm, checking, calm, checking, alert, calm at those moments", () => {
    const source = createReplaySource({ role: "family", label: "Family (demo)", log: quiet })
    source.start()
    const seen: [number, string][] = []
    const record = (elapsed: number) => {
      const state = source.getView().device?.state
      if (state && state !== seen.at(-1)?.[1]) seen.push([elapsed, state])
    }
    record(0)
    for (let elapsed = 100; elapsed < 90_000; elapsed += 100) {
      vi.advanceTimersByTime(100)
      record(elapsed)
    }
    source.stop()

    expect(seen).toEqual(stateChanges(DEMO_SCRIPT))
    expect(seen.map(([ms]) => ms / 1000)).toEqual([0, 12.0, 17.3, 38.0, 48.5, 70.0])
    expect(seen.map(([, state]) => state)).toEqual(["calm", "checking", "calm", "checking", "alert", "calm"])
  })
})

describe("loop and time shift", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("starts loop 2 clean, on its own clock, and not offline, on another date", () => {
    vi.useFakeTimers()
    const start = Date.parse("2031-03-02T08:00:00.000Z")
    vi.setSystemTime(start)
    const source = createReplaySource({ role: "clinician", label: "Clinician (demo)", log: quiet })
    source.start()

    expect(source.getView().device?.last_seen_at).toBe(new Date(start).toISOString())
    vi.advanceTimersByTime(60_000)
    expect(source.getView().incidents).toHaveLength(2)
    expect(source.getView().incidents[0].started_at).toBe(new Date(start + 38_000).toISOString())

    vi.advanceTimersByTime(30_000)
    const loop2 = start + 90_000
    const view = source.getView()
    expect(view.incidents).toHaveLength(0)
    expect(view.events.map((e) => e.kind)).toEqual(["device_online"])
    expect(view.events[0].at).toBe(new Date(loop2).toISOString())
    expect(view.device?.state).toBe("calm")
    expect(view.device?.last_seen_at).toBe(new Date(loop2).toISOString())
    expect(view.role === "clinician" && view.readings).toHaveLength(1)
    expect(isOffline(view.device, Date.now())).toBe(false)

    vi.advanceTimersByTime(12_000)
    expect(source.getView().incidents[0].started_at).toBe(new Date(loop2 + 12_000).toISOString())
    expect(isOffline(source.getView().device, Date.now())).toBe(false)
    source.stop()
  })

  it("never goes offline while the run plays", () => {
    vi.useFakeTimers()
    vi.setSystemTime(Date.parse("2027-01-05T23:59:00.000Z"))
    const source = createReplaySource({ role: "family", label: "Family (demo)", log: quiet })
    source.start()
    for (let t = 0; t < 200_000; t += 500) {
      vi.advanceTimersByTime(500)
      expect(isOffline(source.getView().device, Date.now())).toBe(false)
    }
    source.stop()
  })
})
