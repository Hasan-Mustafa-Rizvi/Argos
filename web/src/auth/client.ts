import { liveConfigured } from "@/live/settings"

import { createDemoAuth } from "./demo"
import { createLiveAuth } from "./liveAuth"
import type { AuthClient } from "./types"

/** Demo auth, unless the site is in live mode with both settings set. */
export function createAuthClient(): AuthClient {
  if (!liveConfigured()) return createDemoAuth()
  return createLiveAuth()
}
