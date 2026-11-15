import * as React from "react"

import type { InkState } from "@/components/argos/ink"
import { SnapshotPlaceholder } from "@/components/argos/SnapshotPlaceholder"

import { PrintedPicture } from "./PrintedPicture"

/**
 * The stored snapshot, fetched as bytes so the dither can read the pixels back.
 * A failure leaves the placeholder. The object address is released by PrintedPicture.
 */
export function FamilySnapshot({ path, ink, surface }: { path: string; ink: InkState; surface: "paper" | "night" }) {
  const [held, setHeld] = React.useState<{ path: string; blob: Blob | null }>({ path, blob: null })
  if (held.path !== path) setHeld({ path, blob: null })

  React.useEffect(() => {
    let gone = false
    void (async () => {
      const { liveConfigured } = await import("@/live/settings")
      if (!liveConfigured() || gone) return
      try {
        const { sharedGateway } = await import("@/live/shared")
        const gateway = await sharedGateway()
        const file = await gateway.downloadSnapshot(path)
        if (!gone) setHeld({ path, blob: file })
      } catch {
        if (!gone) setHeld({ path, blob: null })
      }
    })()
    return () => {
      gone = true
    }
  }, [path])

  if (!held.blob) return <SnapshotPlaceholder tone={surface === "night" ? "night" : "paper"} />
  return <PrintedPicture blob={held.blob} ink={ink} surface={surface} />
}
