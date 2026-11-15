import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { LiveFrame } from "@/components/argos/LiveFrame"
import { createDemoAuth } from "@/auth/demo"
import type { ChallengeSession, ReadySession } from "@/auth/types"
import { EMPTY_READER, FRAME_MAX_BYTES, offerFrame, silence, type ShownFrame } from "@/data/frames"
import { openFamilyView } from "@/data/viewChannel"

import { fakeGateway, fakeToken } from "./fake-gateway"

const AT = "2026-11-15T19:00:12.250Z"

function frame(over: Partial<ShownFrame> = {}): ShownFrame {
  return { seq: 2, at: AT, w: 320, h: 240, jpeg: "QUJD", ...over }
}

const family: ReadySession = {
  kind: "ready",
  role: "family",
  demo: false,
  secondFactor: true,
  label: "Daughter",
  deviceId: "dog-1",
}

describe("rule 4", () => {
  it("accepts a valid frame, and drops a bad one, an oversized one and an older seq", () => {
    let reader = offerFrame(EMPTY_READER, frame(), 1_000)
    expect(reader.phase).toBe("live")
    expect(reader.frame?.seq).toBe(2)
    expect(offerFrame(reader, { ...frame(), extra: true }, 1_100).frame?.seq).toBe(2)
    expect(offerFrame(reader, { ...frame(), jpeg: 12 }, 1_100)).toBe(reader)
    expect(offerFrame(reader, { ...frame(), w: "320" }, 1_100)).toBe(reader)
    expect(offerFrame(reader, { ...frame(), w: 481, h: 240 }, 1_100)).toBe(reader)
    expect(offerFrame(reader, frame({ seq: 1 }), 1_200)).toBe(reader)
    const huge = frame({ jpeg: "A".repeat(FRAME_MAX_BYTES) })
    expect(offerFrame(reader, huge, 1_300)).toBe(reader)
  })

  it("marks five seconds of silence as stopped, then accepts a low seq", () => {
    const reader = offerFrame(EMPTY_READER, frame({ at: "2020-01-01T00:00:00.000Z" }), 10_000)
    expect(silence(reader, 14_999).phase).toBe("live")
    const stopped = silence(reader, 15_000)
    expect(stopped.phase).toBe("stopped")
    expect(stopped.lastSeq).toBeNull()
    const next = offerFrame(stopped, frame({ seq: 0 }), 16_000)
    expect(next.phase).toBe("live")
    expect(next.frame?.seq).toBe(0)
  })

  it("never joins the view for a clinician, a demo, or a session that has not passed the second step", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal2")
    const demo = createDemoAuth().openDemo("family")
    const challenge: ChallengeSession = { kind: "challenge", demo: false, secondFactor: false, step: "code" }
    const clinician: ReadySession = { ...family, role: "clinician", label: "Nurse" }
    expect(openFamilyView(demo, fake.gateway, () => {})).toBeTypeOf("function")
    expect(openFamilyView(challenge, fake.gateway, () => {})).toBeTypeOf("function")
    expect(openFamilyView(clinician, fake.gateway, () => {})).toBeTypeOf("function")
    await Promise.resolve()
    expect(fake.state.channels).toHaveLength(0)

    const stop = openFamilyView(family, fake.gateway, () => {})
    await waitFor(() => expect(fake.state.channels.map((channel) => channel.topic)).toEqual(["view:dog-1"]))
    expect(fake.state.order[0]).toBe("authorize")
    expect(fake.state.order.indexOf("channel:view:dog-1")).toBeGreaterThan(fake.state.order.indexOf("authorize"))
    stop()
  })

  it("does not put the picture in storage or on the console", () => {
    const jpeg = "QUJDRA=="
    const setItem = vi.spyOn(Storage.prototype, "setItem")
    const spies = ["log", "info", "debug", "warn", "error"].map((method) =>
      vi.spyOn(console, method as "log").mockImplementation(() => {}),
    )
    render(
      <LiveFrame
        frame={{ seq: 4, at: AT, w: 8, h: 8, jpeg }}
        ink="calm"
        live
        stoppedFor={null}
      />,
    )
    expect(screen.getByText("LIVE")).toBeInTheDocument()
    const dumped = [...setItem.mock.calls, ...spies.flatMap((spy) => spy.mock.calls)]
    expect(JSON.stringify(dumped)).not.toContain(jpeg)
    expect(JSON.stringify(dumped)).not.toContain("QUJD")
  })
})
