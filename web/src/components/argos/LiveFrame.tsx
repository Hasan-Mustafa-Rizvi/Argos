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

/** One frame, held only as this blob. A bad encoding draws nothing. */
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
  const blob = React.useMemo(() => jpegBlob(frame.jpeg), [frame])
  if (!blob) return null
  return (
    <PrintedPicture
      blob={blob}
      ink={ink}
      surface="night"
      meta={{ at: frame.at, live, stoppedFor }}
    />
  )
}
