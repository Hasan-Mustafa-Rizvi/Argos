import * as React from "react"

import { Button } from "@/components/ui/button"
import { ditherImage } from "@/components/argos/dither"
import { nightRamp, paperRamp, STATE_INK, type InkState } from "@/components/argos/ink"
import { formatClock } from "@/data/derive"

export interface PictureMeta {
  /** ISO time of the frame. */
  at: string
  live: boolean
  /** Set once the view has stopped: how many seconds since the last frame arrived. */
  stoppedFor: number | null
}

/**
 * A camera picture printed in dither, with a control for the original. The bytes stay in
 * memory. The object address used for the original is released when the picture changes.
 */
export function PrintedPicture({
  blob,
  ink,
  surface,
  meta,
}: {
  blob: Blob
  ink: InkState
  surface: "paper" | "night"
  meta?: PictureMeta
}) {
  const canvas = React.useRef<HTMLCanvasElement>(null)
  const img = React.useRef<HTMLImageElement>(null)
  const [original, setOriginal] = React.useState(false)
  const [drawn, setDrawn] = React.useState(false)
  const [seen, setSeen] = React.useState(blob)
  if (seen !== blob) {
    setSeen(blob)
    setDrawn(false)
    setOriginal(false)
  }

  React.useEffect(() => {
    const node = img.current
    if (!node) return
    const address = URL.createObjectURL(blob)
    node.src = address
    return () => URL.revokeObjectURL(address)
  }, [blob])

  React.useEffect(() => {
    let gone = false
    void paint(blob, ink, surface, canvas.current).then((ok) => {
      if (!gone) setDrawn(ok)
    })
    return () => {
      gone = true
    }
  }, [blob, ink, surface])

  return (
    <figure className="argos-shot">
      {meta && (
        <figcaption className="argos-live-meta">
          {meta.live && <span className="argos-live-tag">LIVE</span>}
          <time className="argos-mono" dateTime={meta.at}>
            {formatClock(meta.at)}
          </time>
          {meta.stoppedFor !== null && <span>No picture for {meta.stoppedFor} seconds.</span>}
        </figcaption>
      )}
      <canvas ref={canvas} className="argos-shot-canvas" hidden={!drawn || original} />
      <img ref={img} className="argos-shot-original" alt="" hidden={drawn && !original} />
      <Button type="button" variant="secondary" aria-pressed={original} onClick={() => setOriginal((value) => !value)}>
        {original ? "Show the engraving" : "Show the original picture"}
      </Button>
    </figure>
  )
}

async function paint(blob: Blob, ink: InkState, surface: "paper" | "night", canvas: HTMLCanvasElement | null): Promise<boolean> {
  if (!canvas || typeof createImageBitmap !== "function") return false
  try {
    const bitmap = await createImageBitmap(blob)
    const scratch = document.createElement("canvas")
    scratch.width = bitmap.width
    scratch.height = bitmap.height
    const ctx = scratch.getContext("2d")
    if (!ctx) {
      bitmap.close?.()
      return false
    }
    ctx.drawImage(bitmap, 0, 0)
    const image = ctx.getImageData(0, 0, bitmap.width, bitmap.height)
    const ramp = surface === "night" ? nightRamp(STATE_INK[ink]) : paperRamp(STATE_INK[ink])
    const printed = ditherImage(image.data, bitmap.width, bitmap.height, ramp, surface === "paper")
    const target = canvas.getContext("2d")
    if (!target) {
      bitmap.close?.()
      return false
    }
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const out = target.createImageData(bitmap.width, bitmap.height)
    out.data.set(printed)
    target.putImageData(out, 0, 0)
    bitmap.close?.()
    return true
  } catch {
    return false
  }
}
