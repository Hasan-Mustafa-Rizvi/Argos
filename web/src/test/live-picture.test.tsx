import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { LiveFrame } from "@/components/argos/LiveFrame"
import { PrintedPicture } from "@/components/argos/PrintedPicture"
import type { ShownFrame } from "@/data/frames"

/*
 * jsdom has no canvas and cannot decode a JPEG, so nothing is ever printed here unless a test
 * stands in for it. The stand-in: each decode waits on a promise the test settles, and the
 * canvas gets a context that records what is put on it. A decoded frame `n` is `n` pixels wide,
 * so the width of the canvas on the page says which frame it is showing.
 */
interface Decode {
  resolve(width: number): void
  reject(): void
}

let decodes: Decode[]
let puts: { canvas: HTMLCanvasElement; width: number }[]
let live: Set<string>
let mostLive: number

function standInForPrinting() {
  decodes = []
  puts = []
  vi.stubGlobal(
    "createImageBitmap",
    () =>
      new Promise((resolve, reject) => {
        decodes.push({
          resolve: (width) => resolve({ width, height: 2, close() {} }),
          reject: () => reject(new Error("not a JPEG")),
        })
      }),
  )
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(function (this: HTMLCanvasElement) {
    return fakeContext(this)
  } as unknown as typeof HTMLCanvasElement.prototype.getContext)
}

function fakeContext(canvas: HTMLCanvasElement) {
  return {
    drawImage() {},
    getImageData: (_x: number, _y: number, w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) }),
    createImageData: (w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) }),
    putImageData() {
      puts.push({ canvas, width: canvas.width })
    },
  }
}

function watchAddresses() {
  live = new Set()
  mostLive = 0
  let made = 0
  vi.spyOn(URL, "createObjectURL").mockImplementation(() => {
    const address = `blob:argos-test/${++made}`
    live.add(address)
    mostLive = Math.max(mostLive, live.size)
    return address
  })
  vi.spyOn(URL, "revokeObjectURL").mockImplementation((address: string) => {
    live.delete(address)
  })
}

/** Lets the decode, the print and React's update all run. */
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function printed(index: number, width: number) {
  decodes[index].resolve(width)
  await settle()
}

async function failed(index: number) {
  decodes[index].reject()
  await settle()
}

const AT = "2026-11-15T19:00:12.250Z"

function frame(seq: number, jpeg = btoa(`frame ${seq}`)): ShownFrame {
  return { seq, at: AT, w: 320, h: 240, jpeg }
}

function stream(f: ShownFrame, live = true, stoppedFor: number | null = null) {
  return <LiveFrame frame={f} ink="calm" live={live} stoppedFor={stoppedFor} />
}

function shown(container: HTMLElement) {
  const canvas = container.querySelector<HTMLCanvasElement>("canvas.argos-shot-canvas")!
  const img = container.querySelector<HTMLImageElement>("img.argos-shot-original")!
  return { canvas, img, onCanvas: puts.filter((put) => put.canvas === canvas).map((put) => put.width) }
}

function toggle() {
  return screen.getByRole("button", { name: /Show the (original picture|engraving)/ })
}

beforeEach(() => {
  standInForPrinting()
  watchAddresses()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("the live picture, as frames arrive", () => {
  it("keeps the original once chosen, through frames and a silence, and the original follows the frames", async () => {
    const { container, rerender } = render(stream(frame(1)))
    await printed(0, 1)
    fireEvent.click(toggle())
    expect(toggle()).toHaveAttribute("aria-pressed", "true")

    const sources = new Set([shown(container).img.getAttribute("src")])
    let last = frame(1)
    for (let seq = 2; seq <= 6; seq++) {
      last = frame(seq)
      rerender(stream(last))
      expect(toggle()).toHaveAttribute("aria-pressed", "true")
      await printed(seq - 1, seq)
      expect(toggle()).toHaveAttribute("aria-pressed", "true")
      expect(toggle()).toHaveTextContent("Show the engraving")
      expect(shown(container).img).not.toHaveAttribute("hidden")
      expect(shown(container).canvas).toHaveAttribute("hidden")
      sources.add(shown(container).img.getAttribute("src"))
    }
    expect(sources.size).toBe(6)

    // The reader keeps the same frame through a silence; only the caption changes.
    rerender(stream(last, false, 5))
    expect(screen.getByText("No picture for 5 seconds.")).toBeInTheDocument()
    expect(toggle()).toHaveAttribute("aria-pressed", "true")
    rerender(stream(frame(0)))
    await printed(6, 7)
    expect(toggle()).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByText("LIVE")).toBeInTheDocument()

    fireEvent.click(toggle())
    expect(toggle()).toHaveAttribute("aria-pressed", "false")
    expect(shown(container).canvas).not.toHaveAttribute("hidden")
  })

  it("keeps the engraving once chosen, and the last print on screen while the next is printed", async () => {
    const { container, rerender } = render(stream(frame(1)))
    expect(shown(container).img).not.toHaveAttribute("hidden")
    await printed(0, 1)
    fireEvent.click(toggle())
    fireEvent.click(toggle())
    expect(toggle()).toHaveAttribute("aria-pressed", "false")

    for (let seq = 2; seq <= 6; seq++) {
      rerender(stream(frame(seq)))
      expect(shown(container).canvas).not.toHaveAttribute("hidden")
      expect(shown(container).img).toHaveAttribute("hidden")
      expect(shown(container).canvas.width).toBe(seq - 1)
      await printed(seq - 1, seq)
      expect(shown(container).canvas).not.toHaveAttribute("hidden")
      expect(shown(container).img).toHaveAttribute("hidden")
      expect(shown(container).canvas.width).toBe(seq)
      expect(toggle()).toHaveAttribute("aria-pressed", "false")
    }
  })

  it("does not let a print that finishes late replace a newer frame", async () => {
    const { container, rerender } = render(stream(frame(1)))
    await printed(0, 1)
    rerender(stream(frame(2)))
    rerender(stream(frame(3)))
    await printed(1, 2)
    expect(shown(container).onCanvas).toEqual([1])
    await printed(2, 3)
    expect(shown(container).onCanvas).toEqual([1, 3])

    rerender(stream(frame(4)))
    rerender(stream(frame(5)))
    await printed(4, 5)
    await printed(3, 4)
    expect(shown(container).onCanvas).toEqual([1, 3, 5])
    expect(shown(container).canvas.width).toBe(5)
    expect(shown(container).canvas).not.toHaveAttribute("hidden")
  })

  it("skips a frame that cannot be printed, keeping the last picture and the choice", async () => {
    const { container, rerender } = render(stream(frame(1)))
    await printed(0, 1)
    rerender(stream(frame(2)))
    await failed(1)
    expect(shown(container).canvas).not.toHaveAttribute("hidden")
    expect(shown(container).img).toHaveAttribute("hidden")
    expect(shown(container).canvas.width).toBe(1)

    fireEvent.click(toggle())
    const before = shown(container).img.getAttribute("src")
    rerender(stream(frame(3)))
    await failed(2)
    expect(toggle()).toHaveAttribute("aria-pressed", "true")
    expect(shown(container).img.getAttribute("src")).toBe(before)
    rerender(stream(frame(4)))
    await printed(3, 4)
    expect(toggle()).toHaveAttribute("aria-pressed", "true")
    expect(shown(container).img.getAttribute("src")).not.toBe(before)
  })

  it("skips a frame that cannot be read, keeping the last picture and the choice", async () => {
    const { container, rerender } = render(stream(frame(1)))
    await printed(0, 1)
    fireEvent.click(toggle())
    const before = shown(container).img.getAttribute("src")
    rerender(stream(frame(2, "%%% not base64 %%%")))
    await settle()
    expect(toggle()).toHaveAttribute("aria-pressed", "true")
    expect(shown(container).img.getAttribute("src")).toBe(before)
    fireEvent.click(toggle())
    expect(shown(container).canvas).not.toHaveAttribute("hidden")
    expect(shown(container).canvas.width).toBe(1)
  })

  it("never holds more than one object address, and none once the picture leaves", async () => {
    const { rerender, unmount } = render(stream(frame(1)))
    await printed(0, 1)
    fireEvent.click(toggle())
    for (let seq = 2; seq <= 8; seq++) {
      rerender(stream(frame(seq)))
      if (seq % 3 === 0) await failed(seq - 1)
      else await printed(seq - 1, seq)
      expect(live.size).toBeLessThanOrEqual(1)
    }
    rerender(stream(frame(9, "%%%")))
    await settle()
    expect(mostLive).toBe(1)
    unmount()
    expect(live.size).toBe(0)
  })
})

describe("a picture that is not a stream", () => {
  it("resets the choice for a new picture and hides the canvas until it is printed", async () => {
    const first = new Blob(["one"], { type: "image/jpeg" })
    const second = new Blob(["two"], { type: "image/jpeg" })
    const { container, rerender, unmount } = render(<PrintedPicture blob={first} ink="calm" surface="paper" />)
    await printed(0, 1)
    fireEvent.click(toggle())
    expect(toggle()).toHaveAttribute("aria-pressed", "true")

    rerender(<PrintedPicture blob={second} ink="calm" surface="paper" />)
    expect(toggle()).toHaveAttribute("aria-pressed", "false")
    expect(shown(container).canvas).toHaveAttribute("hidden")
    expect(shown(container).img).not.toHaveAttribute("hidden")
    await printed(1, 2)
    expect(shown(container).canvas).not.toHaveAttribute("hidden")
    expect(shown(container).img).toHaveAttribute("hidden")
    expect(shown(container).canvas.width).toBe(2)
    expect(mostLive).toBe(1)
    unmount()
    expect(live.size).toBe(0)
  })

  it("shows the plain picture when printing is not possible, and the control still works", async () => {
    vi.unstubAllGlobals()
    const { container } = render(<PrintedPicture blob={new Blob(["one"])} ink="calm" surface="paper" />)
    await settle()
    expect(shown(container).img).not.toHaveAttribute("hidden")
    expect(shown(container).canvas).toHaveAttribute("hidden")
    fireEvent.click(toggle())
    expect(toggle()).toHaveAttribute("aria-pressed", "true")
    expect(shown(container).img).not.toHaveAttribute("hidden")
  })
})
