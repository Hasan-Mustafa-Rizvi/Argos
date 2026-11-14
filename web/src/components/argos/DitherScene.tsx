import * as React from "react"

import { cn } from "@/lib/utils"

import { BAYER, ditherIndex, sceneField, sceneMotion, type SceneField } from "./dither"
import { blendRamps, COBALT_RAMP, packRamp } from "./ink"

export interface DitherSceneProps {
  /** Seven tones from paper to ink. Defaults to the cobalt ramp. */
  tones?: readonly string[]
  /** CSS pixels per dither cell. */
  pixel?: number
  seed?: number
  /** Printed under the scene. Without it the scene is decorative and hidden from assistive tech. */
  caption?: string
  className?: string
}

const FRAME_MS = 66
const REPRINT_MS = 600

/** A ridgeline on the horizon, printed through the Bayer matrix on a pixel-scaled canvas. */
export function DitherScene({ tones = COBALT_RAMP, pixel = 2, seed = 7, caption, className }: DitherSceneProps) {
  const figRef = React.useRef<HTMLElement>(null)
  const canvasRef = React.useRef<HTMLCanvasElement>(null)
  const sceneRef = React.useRef<ReturnType<typeof startScene>>(null)
  const tonesKey = tones.join(",")
  const latestTones = React.useRef(tonesKey)

  React.useLayoutEffect(() => {
    latestTones.current = tonesKey
  })

  // A new ramp is handed to the running scene by the next effect, so the ink reprints in place.
  React.useEffect(() => {
    const fig = figRef.current
    const canvas = canvasRef.current
    if (!fig || !canvas) return
    const scene = startScene(fig, canvas, latestTones.current.split(","), pixel, seed)
    sceneRef.current = scene
    return () => {
      scene?.stop()
      sceneRef.current = null
    }
  }, [pixel, seed])

  React.useEffect(() => {
    sceneRef.current?.setTones(tonesKey.split(","))
  }, [tonesKey])

  return (
    <figure
      ref={figRef}
      className={cn("argos-scene", className)}
      style={{ ["--scene-paper" as string]: tones[0] }}
      aria-hidden={caption ? undefined : true}
    >
      <canvas ref={canvasRef} aria-hidden="true" />
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  )
}

function prefersReducedMotion() {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

function startScene(fig: HTMLElement, canvas: HTMLCanvasElement, initial: string[], pixel: number, seed: number) {
  const ctx = canvas.getContext("2d")
  if (!ctx) return null
  const still = prefersReducedMotion()

  let field: SceneField | null = null
  let image: ImageData | null = null
  let words: Uint32Array | null = null
  let ramp = initial
  let from = initial
  let to = initial
  let reprintStart = 0
  let reprinting = false
  let visible = true
  let raf = 0
  let last = -Infinity
  const born = performance.now()

  function layout() {
    const w = fig.clientWidth
    const h = fig.clientHeight
    if (w < 1 || h < 1) return false
    const cols = Math.ceil(w / pixel)
    const rows = Math.ceil(h / pixel)
    if (field && field.cols === cols && field.rows === rows) return true
    canvas.width = cols
    canvas.height = rows
    canvas.style.width = cols * pixel + "px"
    canvas.style.height = rows * pixel + "px"
    field = sceneField(cols, rows, seed)
    image = ctx!.createImageData(cols, rows)
    words = new Uint32Array(image.data.buffer)
    return true
  }

  function draw(now: number) {
    if (!field || !image || !words) return
    const pal = packRamp(ramp)
    const n = pal.length
    const t = still ? 0 : (now - born) / 1000
    const { cols, rows, base } = field
    for (let y = 0; y < rows; y++) {
      const row = y * cols
      const brow = (y & 7) * 8
      for (let x = 0; x < cols; x++) {
        const tone = base[row + x] + sceneMotion(field, x, y, t, seed)
        words[row + x] = pal[ditherIndex(tone, n, BAYER[brow + (x & 7)])]
      }
    }
    ctx!.putImageData(image, 0, 0)
  }

  function frame(now: number) {
    raf = 0
    if (!visible) return
    if (reprinting) {
      const k = Math.min(1, (now - reprintStart) / REPRINT_MS)
      ramp = blendRamps(from, to, k)
      if (k >= 1) reprinting = false
    }
    if (reprinting || now - last >= FRAME_MS) {
      draw(now)
      last = now
    }
    if (reprinting || !still) raf = requestAnimationFrame(frame)
  }

  function kick() {
    if (!raf && visible) raf = requestAnimationFrame(frame)
  }

  const ro =
    typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
          if (layout()) {
            last = -Infinity
            draw(performance.now())
            kick()
          }
        })
  ro?.observe(fig)

  const io =
    typeof IntersectionObserver === "undefined"
      ? null
      : new IntersectionObserver(([entry]) => {
          visible = entry.isIntersecting
          if (visible) kick()
          else if (raf) {
            cancelAnimationFrame(raf)
            raf = 0
          }
        })
  io?.observe(fig)

  if (layout()) draw(performance.now())
  kick()

  return {
    setTones(next: string[]) {
      if (next.join(",") === to.join(",")) return
      if (still) {
        ramp = from = to = next
        draw(performance.now())
        return
      }
      from = ramp
      to = next
      reprintStart = performance.now()
      reprinting = true
      kick()
    },
    stop() {
      if (raf) cancelAnimationFrame(raf)
      raf = 0
      ro?.disconnect()
      io?.disconnect()
    },
  }
}
