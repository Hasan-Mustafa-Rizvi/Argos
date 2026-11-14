import { fireEvent, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import tokens from "@/styles/tokens.css?raw"
import { COBALT_RAMP, NIGHT_RAMP, nightRamp, paperRamp, STATE_INK } from "@/components/argos/ink"

import { renderApp } from "./render"

/** The --ink a `[data-state="…"]` rule sets in tokens.css. */
function inkInTokens(state: string) {
  const rule = new RegExp(`\\[data-state="${state}"\\]\\s*\\{\\s*--ink:\\s*(#[0-9a-fA-F]{6})\\s*;\\s*\\}`)
  return rule.exec(tokens)?.[1]?.toLowerCase()
}

const IDENTITY_INKS = [
  ["calm", "#2238c4"],
  ["checking", "#8a5a0b"],
  ["alert", "#7a1d2b"],
] as const

describe("state to ink", () => {
  it.each(IDENTITY_INKS)("the token file maps %s to exactly %s", (state, hex) => {
    expect(inkInTokens(state)).toBe(hex)
    expect(STATE_INK[state]).toBe(hex)
  })

  it("the dashboard root carries the matching data-state for calm, checking and alert", async () => {
    renderApp("/dashboard?dev=1", { role: "family" })
    const root = await screen.findByTestId("dashboard")
    for (const [state] of IDENTITY_INKS) {
      fireEvent.click(screen.getByRole("button", { name: state[0].toUpperCase() + state.slice(1) }))
      expect(root).toHaveAttribute("data-state", state)
      expect(screen.getByText(state[0].toUpperCase() + state.slice(1), { selector: ".argos-state-word" })).toBeInTheDocument()
    }
  })

  it("the ramps are mixed the way IDENTITY.md prints them", () => {
    expect(paperRamp(STATE_INK.calm)).toEqual(COBALT_RAMP)
    expect(nightRamp(STATE_INK.calm)).toEqual(NIGHT_RAMP)
  })
})
