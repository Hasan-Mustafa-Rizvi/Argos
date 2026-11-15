import * as React from "react"

import type { InkState } from "@/components/argos/ink"
import type { ShownFrame } from "@/data/frames"

import { PrintedPicture } from "./PrintedPicture"

function jpegBlob(jpeg: string): Blob | null {
  try {
    const binary = atob(jpeg)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    return new Blob([bytes], { type: "image/jpeg" })
  } catch {
    return null
  }
}

/**
 * One frame, held only as this blob. A frame with a bad encoding is skipped: the last good one
 * stays, replaced by the next good one. With no good frame yet, nothing is drawn.
 */
export function LiveFrame({
  frame,
  ink,
  live,
  stoppedFor,
}: {
  frame: ShownFrame
  ink: InkState
  live: boolean
  stoppedFor: number | null
}) {
  const [held, setHeld] = React.useState(() => ({ frame, good: readable(frame) }))
  if (held.frame !== frame) setHeld({ frame, good: readable(frame) ?? held.good })
  if (!held.good) return null
  return (
    <PrintedPicture
      blob={held.good.blob}
      ink={ink}
      surface="night"
      meta={{ at: held.good.at, live, stoppedFor }}
      stream
    />
  )
}

function readable(frame: ShownFrame): { at: string; blob: Blob } | null {
  const blob = jpegBlob(frame.jpeg)
  return blob ? { at: frame.at, blob } : null
}
