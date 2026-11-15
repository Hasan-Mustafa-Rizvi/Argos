import { act, fireEvent, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { STILL_MS } from "@/components/argos/reveal"

import { renderApp, type RenderAppOptions } from "./render"
import { setReducedMotion } from "./setup"

const firstEntry: RenderAppOptions = { role: "family", revealSeen: false }

describe("logo reveal", () => {
  it("plays on the first dashboard entry in a session and not on the second", async () => {
    const first = renderApp("/dashboard", firstEntry)
    expect(await screen.findByTestId("logo-reveal")).toBeInTheDocument()
    expect(await screen.findByTestId("dashboard", {}, { timeout: 3000 })).toBeInTheDocument()
    first.unmount()

    renderApp("/dashboard", { role: "family", revealSeen: false })
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument()
    expect(screen.queryByTestId("logo-reveal")).not.toBeInTheDocument()
  })

  it("does not play again after signing out and back in", async () => {
    const first = renderApp("/dashboard", firstEntry)
    await screen.findByTestId("dashboard", {}, { timeout: 3000 })
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }))
    fireEvent.click(await screen.findByRole("button", { name: "Open the demo as clinician" }))
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument()
    expect(screen.queryByTestId("logo-reveal")).not.toBeInTheDocument()
    first.unmount()
  })

  it("reaches the dashboard without input when there is no WebGL2", async () => {
    expect(typeof WebGL2RenderingContext).toBe("undefined")
    renderApp("/dashboard", firstEntry)
    expect(await screen.findByTestId("logo-reveal")).toHaveAttribute("data-mode", "still")
    expect(await screen.findByTestId("dashboard", {}, { timeout: STILL_MS + 2000 })).toBeInTheDocument()
  })

  it("reaches the dashboard without input under reduced motion", async () => {
    setReducedMotion(true)
    renderApp("/dashboard", firstEntry)
    expect(await screen.findByTestId("logo-reveal")).toHaveAttribute("data-mode", "still")
    expect(await screen.findByTestId("dashboard", {}, { timeout: STILL_MS + 2000 })).toBeInTheDocument()
  })

  it("is skipped by a key press", async () => {
    renderApp("/dashboard", firstEntry)
    await screen.findByTestId("logo-reveal")
    act(() => {
      fireEvent.keyDown(window, { key: "a" })
    })
    expect(await screen.findByTestId("dashboard", {}, { timeout: STILL_MS / 2 })).toBeInTheDocument()
  })

  it("is skipped by a tap", async () => {
    renderApp("/dashboard", firstEntry)
    fireEvent.click(await screen.findByTestId("logo-reveal"))
    expect(await screen.findByTestId("dashboard", {}, { timeout: STILL_MS / 2 })).toBeInTheDocument()
  })
})
