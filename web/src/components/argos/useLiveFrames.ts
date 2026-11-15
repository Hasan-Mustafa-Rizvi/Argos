import * as React from "react"

import { EMPTY_READER, offerFrame, silence, type FrameReader } from "@/data/frames"

/** Frames for a real family session. Anyone else gets the empty reader and no channel. */
export function useLiveFrames(enabled: boolean, deviceId: string | null, now: number): FrameReader {
  const key = enabled ? deviceId : null
  const [held, setHeld] = React.useState<{ key: string | null; reader: FrameReader }>({
    key,
    reader: EMPTY_READER,
  })
  if (held.key !== key) setHeld({ key, reader: EMPTY_READER })
  const readerRef = React.useRef(EMPTY_READER)

  React.useEffect(() => {
    readerRef.current = held.key === key ? held.reader : EMPTY_READER
  }, [held.reader, held.key, key])

  React.useEffect(() => {
    if (!enabled || !deviceId) return
    let stop = () => {}
    let cancel = false
    void (async () => {
      const { liveConfigured } = await import("@/live/settings")
      if (!liveConfigured() || cancel) return
      const { sharedGateway } = await import("@/live/shared")
      const gateway = await sharedGateway()
      if (cancel) return
      const { openView } = await import("@/data/viewChannel")
      stop = openView(gateway, deviceId, (message) => {
        const nowMs = Date.now()
        const next = offerFrame(silence(readerRef.current, nowMs), message, nowMs)
        if (next === readerRef.current) return
        readerRef.current = next
        setHeld({ key: deviceId, reader: next })
      })
    })()
    return () => {
      cancel = true
      stop()
    }
  }, [enabled, deviceId])

  return enabled && held.key === key ? silence(held.reader, now) : EMPTY_READER
}
