import type { Session } from "@/auth/types"

import { createReplaySource } from "./replay"
import type { DataSource } from "./source"

/**
 * The data source for a session. A demo session always plays the scripted run. This build has
 * no live source yet, so any other mode notes that and plays the run.
 */
export function createDataSource(session: Session): DataSource {
  const mode = import.meta.env.VITE_DATA_MODE ?? "replay"
  if (mode !== "replay" && !session.demo) {
    console.info(`[argos data] VITE_DATA_MODE "${mode}" is not built yet; playing the scripted run.`)
  }
  return createReplaySource({ role: session.role, label: session.label })
}
