import { createDemoAuth } from "./demo"
import type { AuthClient } from "./types"

/** The auth client for this build. Real accounts arrive with a Supabase implementation here. */
export function createAuthClient(): AuthClient {
  return createDemoAuth()
}
