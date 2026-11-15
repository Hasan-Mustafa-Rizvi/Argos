import { act, fireEvent, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { SAFETY_MS } from "@/components/argos/reveal"
import type { GlassIconRevealProps } from "@/components/ui/liquid-glass-logo-reveal"

import { renderApp } from "./render"

/*
 * jsdom has no WebGL2, so this file stands the glass in for a stub: it records the props the
 * reveal passes, replays on click like the real one, and ends when told to.
 */
const glass = vi.hoisted(() => ({
  replays: 0,
  props: null as Omit<GlassIconRevealProps, "logo"> | null,
}))

vi.mock("@/components/argos/reveal", async (original) => ({
  ...(await original<typeof import("@/components/argos/reveal")>()),
  supportsWebGL2: () => true,
}))

vi.mock("@/components/argos/GlassMark", () => ({
  default: (props: Omit<GlassIconRevealProps, "logo">) => {
    glass.props = props
    return <div data-testid="glass" onClick={() => glass.replays++} />
  },
}))

describe("logo reveal with WebGL2", () => {
  it("plays the glass once, without looping, and hands over when it ends", async () => {
    renderApp("/dashboard", { role: "family", revealSeen: false })
    await screen.findByTestId("glass")
    expect(glass.props).toMatchObject({
      look: "light",
      background: "#f7f4ec",
      logoColor: "#2238c4",
      loop: false,
      iconPlate: false,
      label: "Argos",
    })
    const present = glass.props?.tuning?.present ?? 2.4
    const speed = glass.props?.speed ?? 1
    expect((present + 1.1) / speed).toBeLessThanOrEqual(1.6)
    expect((present + 1.1) / speed).toBeCloseTo(1.5, 1)
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument()

    glass.props?.onEnd?.()
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument()
  })

  it("skips on a tap and never lets the glass replay", async () => {
    glass.replays = 0
    renderApp("/dashboard", { role: "family", revealSeen: false })
    fireEvent.click(await screen.findByTestId("glass"))
    expect(glass.replays).toBe(0)
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument()
  })

  it("reaches the dashboard after the safety timer if the glass never ends", async () => {
    vi.useFakeTimers()
    try {
      renderApp("/dashboard", { role: "family", revealSeen: false })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1)
      })
      expect(screen.getByTestId("glass")).toBeInTheDocument()
      expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(SAFETY_MS)
      })
      expect(screen.getByTestId("dashboard")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
