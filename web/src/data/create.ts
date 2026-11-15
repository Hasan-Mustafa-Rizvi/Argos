import type { DashboardSession } from "@/auth/types"

import { createLiveSource } from "./live"
import { createReplaySource } from "./replay"
import type { DataSource } from "./source"

/**
 * A demo session always plays the scripted run, in every mode. A real session in live mode
 * reads the backend. A real session never falls back to the script.
 */
export function createDataSource(session: DashboardSession): DataSource {
  if (session.kind === "demo") return createReplaySource({ role: session.role, label: session.label })
  return createLiveSource(session)
}
