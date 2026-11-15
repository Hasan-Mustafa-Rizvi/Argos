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
 *
 * With `stream`, each new blob is the next frame of the same picture: the choice of original
 * or engraving stays, the last print stays on screen until the next one is ready, and a frame
 * that cannot be printed is skipped. Without it, a new blob is a different picture and starts over.
 */
export function PrintedPicture({
  blob,
  ink,
  surface,
  meta,
  stream = false,
}: {
  blob: Blob
  ink: InkState
  surface: "paper" | "night"
  meta?: PictureMeta
  stream?: boolean
}) {
  const canvas = React.useRef<HTMLCanvasElement>(null)
  const img = React.useRef<HTMLImageElement>(null)
  const [original, setOriginal] = React.useState(false)
  const [drawn, setDrawn] = React.useState(false)
  const [seen, setSeen] = React.useState(blob)
  // In a stream the original moves on only to a frame that could be read, so a bad one never shows.
  const [shown, setShown] = React.useState(blob)
  if (seen !== blob) {
    setSeen(blob)
    if (!stream) {
      setDrawn(false)
      setOriginal(false)
    }
  }
  const plain = stream ? shown : blob

  React.useEffect(() => {
    const node = img.current
    if (!node) return
    const address = URL.createObjectURL(plain)
    node.src = address
    return () => URL.revokeObjectURL(address)
  }, [plain])

  React.useEffect(() => {
    let gone = false
    void paint(blob, ink, surface, canvas.current, () => !gone).then((result) => {
      if (gone) return
      if (result === "printed") setDrawn(true)
      else if (!stream) setDrawn(false)
      if (stream && result !== "failed") setShown(blob)
    })
    return () => {
      gone = true
    }
  }, [blob, ink, surface, stream])

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

/**
 * "unsupported": this browser cannot print, so the plain picture is the fallback.
 * "failed": this picture could not be read or printed. "stale": a newer one took its place.
 */
type Print = "printed" | "unsupported" | "failed" | "stale"

async function paint(
  blob: Blob,
  ink: InkState,
  surface: "paper" | "night",
  canvas: HTMLCanvasElement | null,
  current: () => boolean,
): Promise<Print> {
  if (!canvas || typeof createImageBitmap !== "function") return "unsupported"
  const scratch = document.createElement("canvas")
  const ctx = scratch.getContext("2d")
  const target = canvas.getContext("2d")
  if (!ctx || !target) return "unsupported"
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(blob)
  } catch {
    return "failed"
  }
  try {
    // Everything after this check runs without a pause, so nothing newer can arrive mid-print.
    if (!current()) return "stale"
    scratch.width = bitmap.width
    scratch.height = bitmap.height
    ctx.drawImage(bitmap, 0, 0)
    const image = ctx.getImageData(0, 0, bitmap.width, bitmap.height)
    const ramp = surface === "night" ? nightRamp(STATE_INK[ink]) : paperRamp(STATE_INK[ink])
    const printed = ditherImage(image.data, bitmap.width, bitmap.height, ramp, surface === "paper")
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const out = target.createImageData(bitmap.width, bitmap.height)
    out.data.set(printed)
    target.putImageData(out, 0, 0)
    return "printed"
  } catch {
    return "failed"
  } finally {
    bitmap.close?.()
  }
}
