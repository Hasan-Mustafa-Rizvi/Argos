import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import landingSource from "@/components/ui/cobalt-toile-landing.tsx?raw"

import { AcknowledgeBar } from "@/components/dashboard/AcknowledgeBar"
import { IncidentsPlate } from "@/components/dashboard/IncidentsPlate"
import { TimelinePlate } from "@/components/dashboard/TimelinePlate"
import type { Incident, TimelineEvent } from "@/data/contract"

import { deviceLine, renderDashboard } from "./dashboard-harness"
import { renderApp } from "./render"

const DASH = /\u2014|\u2013|&#8212;|&#8211;|&#x2014;|&#x2013;|&mdash;|&ndash;/i

function expectNoDashes() {
  expect(document.body.innerHTML).not.toMatch(DASH)
}

/** The copied landing file, with its opening comment taken off. */
function landingBody() {
  const lines = landingSource.split(/\r?\n/)
  let i = 0
  if (lines[0]?.includes("use client")) {
    i = 1
    if (lines[i]?.trim() === "") i += 1
  }
  while (i < lines.length && lines[i].startsWith("//")) i += 1
  return lines.slice(i).join("\n")
}

const SENTENCE = "A person is down \u2014 no answer, still 3\u20135 seconds."
const SHOWN = "A person is down, no answer, still 3-5 seconds."

const incident: Incident = {
  id: "b1",
  device_id: "d1",
  trigger: "fall",
  status: "escalated",
  confidence: 0.9,
  started_at: "2026-11-15T19:00:38.000Z",
  ended_at: null,
  stood_down_by: null,
  acknowledged_by: null,
  acknowledged_at: null,
  summary: SENTENCE,
}

const event: TimelineEvent = {
  id: "e1",
  device_id: "d1",
  incident_id: "b1",
  at: "2026-11-15T19:00:38.000Z",
  kind: "trigger",
  text: SENTENCE,
  detail: {},
}

describe("polish", () => {
  it("prints no em dash or en dash on the landing, the sign-in page, or either dashboard", async () => {
    const landing = renderApp("/")
    await screen.findByRole("heading", { level: 1 })
    expectNoDashes()
    landing.unmount()

    const signIn = renderApp("/sign-in")
    await screen.findByRole("heading", { name: "Sign in" })
    expectNoDashes()
    signIn.unmount()

    for (const role of ["family", "clinician"] as const) {
      for (const state of ["calm", "alert"] as const) {
        const view = renderDashboard({ role, lines: [deviceLine(0, state)] })
        expect(screen.getByTestId("dashboard")).toHaveAttribute("data-state", state)
        expectNoDashes()
        view.unmount()
      }
    }
  })

  it("keeps em dashes and en dashes out of the landing template, apart from its opening comment", () => {
    expect(landingBody()).not.toMatch(DASH)
  })

  it("draws no decorative canvas on the sign-in page or the dashboard", async () => {
    renderApp("/sign-in")
    await screen.findByRole("heading", { name: "Sign in" })
    expect(document.querySelector("canvas")).toBeNull()

    renderDashboard({ role: "family", lines: [deviceLine(0, "calm")] })
    expect(screen.getByTestId("dashboard").querySelector("canvas")).toBeNull()
  })

  it("turns dashes in a timeline event, an incident summary and the acknowledge bar into a comma or a hyphen", () => {
    render(
      <>
        <TimelinePlate events={[event]} />
        <IncidentsPlate incidents={[incident]} person="Eleni" />
        <AcknowledgeBar incident={incident} onAcknowledge={() => Promise.resolve({ ok: true })} />
      </>,
    )
    fireEvent.click(screen.getByRole("button", { name: /A fall/ }))
    expect(screen.getAllByText(SHOWN)).toHaveLength(3)
    expect(document.body.innerHTML).not.toMatch(DASH)
  })

  it("shows the night-watch drawing on the sign-in plate, named Argos, and no horizon caption", async () => {
    renderApp("/sign-in")
    await screen.findByRole("heading", { name: "Sign in" })
    const plate = document.querySelector(".argos-signin-plate")
    expect(plate).not.toBeNull()
    const root = plate as HTMLElement
    expect(within(root).getByRole("img", { name: "Argos" })).toHaveClass("argos-signin-drawing")
    expect(root.querySelector(".argos-keyline")).toBeNull()
    expect(root.querySelector(".argos-signin-seal")).toBeNull()
    expect(document.body.textContent).not.toMatch(/horizon/i)
  })

  it("closes the dashboard with the wave band, inside the state, with no colour of its own", () => {
    renderDashboard({ role: "clinician", lines: [deviceLine(0, "alert")] })
    const dash = screen.getByTestId("dashboard")
    const wave = dash.querySelector(".argos-wave")
    expect(wave).not.toBeNull()
    expect(dash.lastElementChild).toBe(wave)
    expect(wave).toHaveAttribute("aria-hidden", "true")
    expect(wave?.getAttribute("style")).toBeNull()
    expect(wave?.querySelector("[style]")).toBeNull()
  })

  it("shows the three people as cards, and the navigation still has a section to reach", async () => {
    renderApp("/")
    await screen.findByRole("heading", { level: 1 })
    const section = document.querySelector('[data-sec="insights"]')
    expect(section).not.toBeNull()
    const root = section as HTMLElement
    expect(root.textContent).toContain("Hasan Mustafa Rizvi")
    expect(root.textContent).toContain("Neel")
    expect(root.textContent).toContain("Farrell")
    expect(root.textContent).toContain("Software, design, interface polish and organization")
    expect(root.textContent).toContain("Hardware and the dog's body")
    const github = within(root)
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"))
      .filter((href) => href?.startsWith("https://github.com/"))
    expect(github).toEqual([
      "https://github.com/Hasan-Mustafa-Rizvi",
      "https://github.com/NeelM1",
      "https://github.com/DummyTech",
    ])
    expect(root.querySelector(".ctl-prlogo")).toBeNull()
    expect(root.querySelector(".ctl-chip")).toBeNull()
    for (const link of screen.getAllByRole("link", { name: "Who made this" })) {
      expect(link).toHaveAttribute("href", "#insights")
    }
    expect(document.querySelector('[data-sec="insights"]')).toBe(root)
  })

  it("names the Raspberry Pi and the Reachy Mini, and not an ESP32", async () => {
    renderApp("/")
    await screen.findByRole("heading", { level: 1 })
    const text = document.body.textContent ?? ""
    expect(text).not.toContain("ESP32")
    expect(text).toContain("Raspberry Pi")
    expect(text).toContain("Reachy Mini")
  })
})
