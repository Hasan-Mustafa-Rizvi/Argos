import { fireEvent, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

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
    expect(3.5 / (glass.props?.speed ?? 1)).toBeCloseTo(3, 1)
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
})
