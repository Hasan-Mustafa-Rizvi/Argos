import { act, fireEvent, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { admit, admitIncident } from "@/data/admit"
import type { ScriptLine } from "@/data/contract"
import { createReplaySource } from "@/data/replay"
import { DEMO_SCRIPT } from "@/data/script"

import { advance, at, DEVICE_ID, deviceLine, renderDashboard } from "./dashboard-harness"

const same = (iso: string) => iso
const quiet = () => {}

/** A row that throws if anything reads it: proof that a dropped record is never looked at. */
const untouchable = new Proxy(
  {},
  {
    get() {
      throw new Error("a dropped record was read")
    },
    has() {
      throw new Error("a dropped record was read")
    },
    ownKeys() {
      throw new Error("a dropped record was read")
    },
  },
)

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date("2026-11-20T10:00:00Z"))
})

afterEach(() => {
  vi.useRealTimers()
})

describe("family never gets readings", () => {
  it("drops a reading where it enters, before reading a single field", () => {
    expect(admit("readings", untouchable, "family", same)).toBeNull()
    const reading = DEMO_SCRIPT.find((l) => l.table === "readings")
    expect(reading).toBeDefined()
    expect(admit("readings", reading!.row, "family", same)).toBeNull()
    expect(admit("readings", reading!.row, "clinician", same)?.table).toBe("readings")
  })

  it("never stores one: the replay passes every reading through untouched", () => {
    const lines: ScriptLine[] = [
      ...DEMO_SCRIPT.filter((l) => l.table !== "readings"),
      ...DEMO_SCRIPT.filter((l) => l.table === "readings").map((l) => ({ ...l, row: untouchable })),
    ]
    const source = createReplaySource({ role: "family", label: "Family (demo)", lines, log: quiet })
    expect(() => {
      source.start()
      vi.advanceTimersByTime(95_000)
    }).not.toThrow()
    source.stop()
  })

  it("leaves the readings key absent from the family view at every moment", () => {
    const source = createReplaySource({ role: "family", label: "Family (demo)", log: quiet })
    source.start()
    for (let t = 0; t < 90_000; t += 1000) {
      const view = source.getView()
      expect(Object.keys(view)).not.toContain("readings")
      expect(JSON.stringify(view)).not.toMatch(/still_s|temp_c|tilt_deg|person_present/)
      vi.advanceTimersByTime(1000)
    }
    source.stop()
  })

  it("renders nothing of stillness, temperature or history", () => {
    const { container } = renderDashboard({ role: "family" })
    for (let t = 0; t < 90_000; t += 5000) {
      advance(5000)
      const text = container.textContent ?? ""
      expect(text).not.toMatch(/Stillness|Sensor history|Temperature|Tilt|°C|without moving|in view/)
      expect(screen.queryByText("Room")).not.toBeInTheDocument()
      expect(text).not.toMatch(/\b23\.\d\b/)
    }
  })
})

describe("clinician never gets a snapshot", () => {
  it("drops the snapshot path where an incident enters", () => {
    const row = DEMO_SCRIPT.find((l) => l.table === "incidents" && l.row.snapshot_path)!.row
    const forClinician = admitIncident(row, "clinician", same)
    expect(forClinician).not.toBeNull()
    expect(Object.keys(forClinician!)).not.toContain("snapshot_path")
    expect(forClinician!.summary).toMatch(/lying on the floor/)
    expect(admitIncident(row, "family", same)?.snapshot_path).toMatch(/snapshot\.jpg$/)
  })

  it("has no snapshot path in the view at any point of the run", () => {
    const source = createReplaySource({ role: "clinician", label: "Clinician (demo)", log: quiet })
    source.start()
    for (let t = 0; t < 180_000; t += 500) {
      for (const incident of source.getView().incidents) expect(Object.keys(incident)).not.toContain("snapshot_path")
      expect(JSON.stringify(source.getView())).not.toContain("snapshot")
      vi.advanceTimersByTime(500)
    }
    source.stop()
  })

  it("shows no placeholder at any point, in the view or in an opened incident", () => {
    renderDashboard({ role: "clinician" })
    for (let t = 0; t < 90_000; t += 500) {
      advance(500)
      expect(screen.queryByTestId("snapshot-placeholder")).not.toBeInTheDocument()
      expect(screen.queryByText(/placeholder/i)).not.toBeInTheDocument()
      if (t === 60_000) {
        const [escalated, stoodDown] = screen.getAllByRole("button", { expanded: false })
        fireEvent.click(escalated)
        expect(screen.getByText(/lying on the floor/, { selector: ".argos-ledger-detail .argos-summary" })).toBeInTheDocument()
        expect(screen.queryByTestId("snapshot-placeholder")).not.toBeInTheDocument()
        fireEvent.click(stoodDown)
        expect(stoodDown).toHaveAttribute("aria-expanded", "true")
        expect(screen.queryByTestId("snapshot-placeholder")).not.toBeInTheDocument()
        fireEvent.click(escalated)
      }
    }
  })

  it("while family gets the placeholder once the snapshot exists, labelled as one", () => {
    renderDashboard({ role: "family" })
    advance(50_000)
    expect(screen.queryByTestId("snapshot-placeholder")).not.toBeInTheDocument()
    advance(600)
    const view = screen.getByRole("region", { name: "Argos's view" })
    expect(within(view).getByTestId("snapshot-placeholder")).toHaveTextContent(/placeholder/i)
    expect(within(view).getByText("The live view opens for signed-in family.")).toBeInTheDocument()
  })
})

describe("stood-down incidents show nothing extra", () => {
  const injected: ScriptLine[] = [
    deviceLine(0, "calm"),
    {
      offset_ms: 1000,
      table: "incidents",
      op: "insert",
      row: {
        id: "b0000000-0000-4000-8000-0000000000ff",
        device_id: DEVICE_ID,
        trigger: "fall",
        status: "stood_down",
        confidence: 0.5,
        started_at: at(1),
        ended_at: at(2),
        stood_down_by: "pat",
        summary: "This summary must never be shown.",
        snapshot_path: "incidents/b0000000-0000-4000-8000-0000000000ff/snapshot.jpg",
        acknowledged_by: null,
        acknowledged_at: null,
      },
    },
    deviceLine(5000, "calm"),
  ]

  it.each(["family", "clinician"] as const)("shows a %s neither summary nor snapshot", (role) => {
    const source = createReplaySource({ role, label: "x", lines: injected, log: quiet })
    source.start()
    vi.advanceTimersByTime(1500)
    const incident = source.getView().incidents[0]
    expect(incident.status).toBe("stood_down")
    expect(Object.keys(incident)).not.toContain("summary")
    expect(Object.keys(incident)).not.toContain("snapshot_path")
    source.stop()

    renderDashboard({ role, lines: injected })
    advance(1500)
    fireEvent.click(screen.getByRole("button", { name: /A fall/ }))
    expect(screen.getByText("A pat on the head", { selector: "dd" })).toBeInTheDocument()
    expect(screen.queryByText("This summary must never be shown.")).not.toBeInTheDocument()
    expect(screen.queryByTestId("snapshot-placeholder")).not.toBeInTheDocument()
  })

  it.each(["family", "clinician"] as const)("still shows a %s the summary of incident B after acknowledging", async (role) => {
    renderDashboard({ role })
    advance(51_000)
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }))
    })
    fireEvent.click(screen.getByRole("button", { name: /A fall/ }))
    const summary = "A person is lying on the floor beside the armchair and did not respond when asked."
    expect(screen.getByText(summary, { selector: ".argos-ledger-detail .argos-summary" })).toBeInTheDocument()
  })
})
