import type { Session } from "@/auth/types"
import type { Gateway } from "@/live/ports"

import { frameMessage } from "./frames"

/**
 * The live view channel. Only a real family session that has passed its second factor
 * reaches `openChannel`. Everyone else returns a stop function that does nothing.
 */
export function openFamilyView(session: Session, gateway: Gateway, onFrame: (message: unknown) => void): () => void {
  if (session.kind !== "ready" || session.role !== "family") return () => {}
  return openView(gateway, session.deviceId, onFrame)
}

export function openView(gateway: Gateway, deviceId: string, onFrame: (message: unknown) => void): () => void {
  let stopped = false
  let channel: ReturnType<Gateway["openChannel"]> | null = null
  void (async () => {
    try {
      await gateway.authorize()
      if (stopped) return
      channel = gateway.openChannel(`view:${deviceId}`)
      channel.onBroadcast("frame", (payload) => onFrame(frameMessage(payload)))
      channel.subscribe(() => {})
    } catch {
      // No picture. The panel keeps its line.
    }
  })()
  return () => {
    stopped = true
    void channel?.leave()
  }
}
