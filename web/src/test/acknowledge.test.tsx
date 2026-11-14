import { act, fireEvent, screen, within } from "@testing-library/react"
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

const root = () => screen.getByTestId("dashboard")
const ackButton = () => screen.queryByRole("button", { name: "Acknowledge" })

describe("acknowledge", () => {
  it("appears only while the escalated incident waits", () => {
    renderDashboard({ role: "family" })
    for (let t = 0; t < 48_500; t += 500) {
      expect(ackButton()).not.toBeInTheDocument()
      advance(500)
    }
    expect(root()).toHaveAttribute("data-state", "alert")
    expect(ackButton()).toBeInTheDocument()
    advance(21_000)
    expect(ackButton()).toBeInTheDocument()
    advance(500)
    expect(root()).toHaveAttribute("data-state", "calm")
    expect(ackButton()).not.toBeInTheDocument()
  })

  it("is the only primary button", () => {
    renderDashboard({ role: "clinician", path: "/dashboard?dev=1" })
    advance(50_000)
    const primaries = screen.getAllByRole("button").filter((b) => b.getAttribute("data-variant") === "default")
    expect(primaries).toEqual([ackButton()])
  })

  it.each(["family", "clinician"] as const)(
    "ends the alert at once for %s, with this session's label and the current time, for good",
    async (role) => {
      const { source, session } = renderDashboard({ role })
      advance(55_000)
      expect(root()).toHaveAttribute("data-state", "alert")

      const pressedAt = Date.now()
      await act(async () => {
        fireEvent.click(ackButton()!)
      })

      expect(root()).toHaveAttribute("data-state", "calm")
      expect(ackButton()).not.toBeInTheDocument()

      const timeline = screen.getByRole("list", { name: "Timeline, newest first" })
      const newest = within(timeline).getAllByRole("listitem")[0]
      expect(newest).toHaveTextContent(`${session.label} acknowledged.`)
      const stamp = Date.parse(newest.querySelector("time")!.getAttribute("dateTime")!)
      expect(stamp).toBe(pressedAt)
      expect(stamp).toBeLessThanOrEqual(Date.now())

      for (let t = 55_000; t < 89_500; t += 500) {
        advance(500)
        expect(root()).not.toHaveAttribute("data-state", "alert")
        expect(ackButton()).not.toBeInTheDocument()
        const incident = source.getView().incidents.find((i) => i.id.endsWith("b"))!
        expect(incident.status).toBe("acknowledged")
        expect(incident.acknowledged_by).toBe(session.label)
        expect(Date.parse(incident.acknowledged_at!)).toBe(pressedAt)
      }
      expect(screen.queryByText(/Daughter acknowledged/)).not.toBeInTheDocument()
      expect(screen.getByRole("button", { name: /A fall/ })).toHaveTextContent(`Acknowledged by ${session.label}`)
    },
  )

  it("lets a later loop start clean", async () => {
    renderDashboard({ role: "family" })
    advance(50_000)
    await act(async () => {
      fireEvent.click(ackButton()!)
    })
    advance(40_500)
    expect(screen.queryByText(/acknowledged\./)).not.toBeInTheDocument()
    expect(screen.getByText("No checks yet.", { selector: ".argos-area-incidents *" })).toBeInTheDocument()
  })
})

describe("offline", () => {
  const silent: ScriptLine[] = [
    deviceLine(0, "calm"),
    {
      offset_ms: 60_000,
      table: "events",
      op: "insert",
      row: {
        id: "c0000000-0000-4000-8000-0000000000ff",
        device_id: DEVICE_ID,
        incident_id: null,
        at: at(60),
        kind: "device_online",
        text: "Argos is online.",
        detail: {},
      },
    },
  ]

  it("shows after more than 15 s without a report", () => {
    renderDashboard({ role: "family", lines: silent })
    advance(15_000)
    expect(root()).toHaveAttribute("data-state", "calm")
    advance(1_100)
    expect(root()).toHaveAttribute("data-state", "offline")
    expect(screen.getByText("Offline", { selector: ".argos-state-word" })).toBeInTheDocument()
    expect(screen.getByText(/^Last seen /)).toBeInTheDocument()
    expect(document.querySelector(".argos-meander")).toHaveAttribute("data-flat")
  })
})
